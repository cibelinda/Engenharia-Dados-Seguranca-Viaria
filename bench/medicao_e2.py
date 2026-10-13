"""Medição do ADR 0004: mecanismo de ingestão, compressão e formato de tabela.

Roda contra o banco já carregado (os 20 anos da PRF), sem depender das tabelas que o
serviço `ingestao-lote` grava nem do CDC: tudo o que escreve fica numa pasta temporária do
container e num schema `medicao_e2`, apagados no fim.

    docker compose up --build -d && docker compose wait load
    docker compose run --rm --no-deps -v ./bench:/app/bench ingestao-lote sh -c \
      "pip install --user -q 'pyiceberg[sql-sqlite]==0.12.0' && python bench/medicao_e2.py"

O pyiceberg é instalado só para a medição (Iceberg é a alternativa não adotada); sem ele, a
parte do Iceberg é pulada e o resto roda.

O que mede:
1. Opção nula dentro do banco: `CREATE TABLE ... AS SELECT` das cinco views vigentes, que é a
   recarga periódica com `INSERT ... SELECT`. Tempo e tamanho.
2. Opção nula em formato aberto: recarga completa das cinco tabelas para Delta (todas as
   partições reescritas a cada execução). Tempo e tamanho.
3. Lote incremental (o mecanismo do serviço `ingestao-lote`): segunda execução sem mudança e
   reescrita de um ano republicado (2024), com o código de blackspot/ingestao_lote.py.
4. Volume de eventos que um CDC teria de levar numa republicação (linhas de um ano).
5. Compressão: sem compressão × snappy × zstd, em Parquet particionado por ano. Tamanho,
   tempo de escrita e tempo de leitura com DuckDB (Q1 da pergunta de gestão e um ano inteiro).
6. Delta × Iceberg: escrita da ocorrência, evolução de esquema (adicionar, renomear, remover
   coluna, alargar tipo) e leitura pelo DuckDB.

Grava o resultado em bench/resultados/medicao_e2.json.
"""

from __future__ import annotations

import json
import resource
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.dataset as ds
from deltalake import DeltaTable, write_deltalake

# Rodando `python bench/medicao_e2.py`, só bench/ entra no caminho de importação.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blackspot import ingestao_lote as lote  # noqa: E402

OUT = Path(__file__).resolve().parent / "resultados" / "medicao_e2.json"
RODADAS = 5
ANO_REPUBLICADO = 2024
ULTIMO_ANO = 2025  # anos completos da pergunta de gestão (2026 é parcial)

# A Q1 de bench/medicao_adr.py, escrita para o DuckDB ler o Parquet.
Q1 = """
SELECT br, uf, floor(km / 10) * 10 AS km_inicio, ano,
       count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
FROM {fonte}
WHERE br <> 0 AND km IS NOT NULL AND ano <= {ultimo}
GROUP BY br, uf, km_inicio, ano
"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def tamanho_mb(pasta: Path) -> float:
    return round(sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file()) / 2**20, 1)


def arquivos_parquet(pasta: Path) -> int:
    return sum(1 for _ in pasta.rglob("*.parquet"))


def mediana_ms(funcao, rodadas: int = RODADAS) -> dict:
    funcao()  # aquecimento
    tempos = []
    for _ in range(rodadas):
        t0 = time.perf_counter()
        funcao()
        tempos.append((time.perf_counter() - t0) * 1000)
    return {"mediana_ms": round(statistics.median(tempos), 1),
            "min_ms": round(min(tempos), 1), "max_ms": round(max(tempos), 1)}


# --- 1. opção nula dentro do banco --------------------------------------------------


def recarga_no_banco(conn: psycopg.Connection) -> dict:
    """CREATE TABLE AS das views vigentes: a recarga periódica com INSERT ... SELECT."""
    rodadas = []
    for _ in range(3):
        conn.execute("DROP SCHEMA IF EXISTS medicao_e2 CASCADE")
        conn.execute("CREATE SCHEMA medicao_e2")
        t0 = time.perf_counter()
        for nome, view in lote.TABELAS.items():
            conn.execute(f"CREATE TABLE medicao_e2.{nome} AS SELECT * FROM {view}")
        rodadas.append(time.perf_counter() - t0)
    tamanho = conn.execute(
        """SELECT sum(pg_total_relation_size(c.oid)) FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'medicao_e2' AND c.relkind = 'r'""").fetchone()[0]
    conn.execute("DROP SCHEMA medicao_e2 CASCADE")
    return {"tempo_s_mediana": round(statistics.median(rodadas), 1),
            "tempos_s": [round(t, 1) for t in rodadas],
            "tamanho_mb": round(float(tamanho) / 2**20, 1),
            "formato": "tabelas do PostgreSQL (não é formato aberto)"}


# --- 2 e 3. recarga completa e lote incremental em Delta ----------------------------


def gravar_tudo(conn: psycopg.Connection, lake: Path, vigentes: dict, so_anos=None) -> dict:
    """Lê as views e grava as partições em Delta, com as funções do serviço ingestao-lote.

    Sem `so_anos`, segue a regra do serviço: pula a partição que já tem o lote vigente.
    Com `so_anos`, reescreve só esses anos (simula a republicação deles)."""
    processado_em = datetime.now(timezone.utc)
    gravadas = puladas = linhas = 0
    t0 = time.perf_counter()
    for nome, view in lote.TABELAS.items():
        sql, schema = lote.montar_leitura(conn, view)
        caminho = lake / nome
        for ano, id_lote in vigentes.items():
            if so_anos is not None:
                if ano not in so_anos:
                    continue
            elif not lote.precisa_reescrever(lote.lotes_na_particao(caminho, ano), id_lote):
                puladas += 1
                continue
            tabela = lote.ler_ano(conn, sql, ano, schema, processado_em)
            if tabela.num_rows == 0:
                continue
            lote.gravar_particao(caminho, tabela, ano)
            gravadas += 1
            linhas += tabela.num_rows
    return {"tempo_s": round(time.perf_counter() - t0, 1), "particoes_gravadas": gravadas,
            "particoes_puladas": puladas, "linhas_gravadas": linhas}


def caminhos_delta(conn: psycopg.Connection, base: Path) -> dict:
    vigentes = dict(conn.execute("SELECT ano, id_lote FROM lote_vigente ORDER BY ano").fetchall())

    # Opção nula em formato aberto: cada execução reescreve tudo do zero.
    completas = []
    for i in range(2):
        lake = base / f"completa_{i}"
        r = gravar_tudo(conn, lake, vigentes)
        completas.append(r["tempo_s"])
        log(f"  recarga completa {i + 1}: {r['tempo_s']} s, {r['particoes_gravadas']} partições")
    lake = base / "completa_1"
    completa = {"tempo_s_por_execucao": completas, "tamanho_mb": tamanho_mb(lake),
                "arquivos_parquet": arquivos_parquet(lake),
                "linhas": {n: DeltaTable(str(lake / n)).to_pyarrow_dataset().count_rows()
                           for n in lote.TABELAS}}

    # Lote incremental sobre a mesma tabela: nada mudou, e depois uma republicação de 2024.
    sem_mudanca = gravar_tudo(conn, lake, vigentes)
    log(f"  incremental sem mudança: {sem_mudanca['tempo_s']} s")
    republicacao = gravar_tudo(conn, lake, vigentes, so_anos={ANO_REPUBLICADO})
    log(f"  incremental, republicação de {ANO_REPUBLICADO}: {republicacao['tempo_s']} s")
    versoes = {n: DeltaTable(str(lake / n)).version() for n in lote.TABELAS}
    return {"recarga_completa": completa,
            "incremental_sem_mudanca": sem_mudanca,
            "incremental_republicacao": {**republicacao, "ano": ANO_REPUBLICADO,
                                         "tamanho_mb_depois": tamanho_mb(lake),
                                         "versoes_delta": versoes},
            "lake": str(lake)}


# --- 4. eventos de CDC numa republicação --------------------------------------------


def eventos_cdc(conn: psycopg.Connection) -> dict:
    """Uma republicação insere o ano inteiro num lote novo (ADR 0001): cada linha é um evento
    de INSERT no WAL que um CDC teria de levar até a camada analítica."""
    por_tabela = {}
    for nome, view in lote.TABELAS.items():
        if nome == "ocorrencia":
            sql = f"SELECT count(*) FROM {view} WHERE ano = %s"
        else:
            sql = (f"SELECT count(*) FROM {view} t JOIN ocorrencia_vigente o "
                   f"USING (id_lote, id) WHERE o.ano = %s")
        por_tabela[nome] = conn.execute(sql, (ANO_REPUBLICADO,)).fetchone()[0]
    corrente = conn.execute("SELECT max(ano) FROM lote_vigente").fetchone()[0]
    lotes_corrente = conn.execute(
        "SELECT count(*) FROM lote_carga WHERE ano = %s AND status = 'concluido'",
        (corrente,)).fetchone()[0]
    return {"ano": ANO_REPUBLICADO, "eventos_por_tabela": por_tabela,
            "eventos_total": sum(por_tabela.values()),
            "eventos_lote_carga": 1,
            "nota": "insert-only: a republicação não gera UPDATE nem DELETE, só INSERT do ano "
                    "inteiro no lote novo, numa única transação",
            "ano_corrente": corrente, "lotes_concluidos_do_ano_corrente": lotes_corrente}


# --- 5. compressão ---------------------------------------------------------------------


def compressao(origem: Path, base: Path) -> dict:
    """Reescreve ocorrência e pessoa em Parquet particionado por ano com cada codec."""
    resultado = {}
    for nome in ("ocorrencia", "pessoa"):
        tabela = DeltaTable(str(origem / nome)).to_pyarrow_table()
        resultado[nome] = {}
        for codec in ("none", "snappy", "zstd"):
            pasta = base / f"{nome}_{codec}"
            formato = ds.ParquetFileFormat()
            opcoes = formato.make_write_options(compression=codec)
            t0 = time.perf_counter()
            ds.write_dataset(tabela, pasta, format=formato, file_options=opcoes,
                             partitioning=["ano"], partitioning_flavor="hive",
                             existing_data_behavior="overwrite_or_ignore")
            escrita = time.perf_counter() - t0
            r = {"tamanho_mb": tamanho_mb(pasta), "escrita_s": round(escrita, 1),
                 "arquivos": arquivos_parquet(pasta)}
            if nome == "ocorrencia":
                fonte = f"read_parquet('{pasta}/**/*.parquet', hive_partitioning = true)"
                con = duckdb.connect()
                r["q1_duckdb"] = mediana_ms(
                    lambda: con.execute(Q1.format(fonte=fonte, ultimo=ULTIMO_ANO)).fetchall())
                r["ano_inteiro_duckdb"] = mediana_ms(
                    lambda: con.execute(
                        f"SELECT * FROM {fonte} WHERE ano = {ANO_REPUBLICADO}").to_arrow_table())
                con.close()
            resultado[nome][codec] = r
            log(f"  {nome:<10} {codec:<6} {r['tamanho_mb']:>7} MB, escrita {r['escrita_s']} s")
        del tabela
    return resultado


# --- 6. Delta × Iceberg ---------------------------------------------------------------


def _pequena() -> pa.Table:
    return pa.table({"id": pa.array([1, 2, 3], pa.int64()),
                     "ano": pa.array([2024, 2024, 2025], pa.int32()),
                     "mortos": pa.array([0, 1, 0], pa.int32()),
                     "municipio": pa.array(["A", "B", "C"])})


def _tentar(funcao) -> dict:
    try:
        detalhe = funcao()
        return {"ok": True, **({"detalhe": detalhe} if detalhe else {})}
    except Exception as e:  # noqa: BLE001 - o erro é o resultado da medição
        return {"ok": False, "erro": f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"}


def evolucao_delta(base: Path) -> dict:
    caminho = base / "evolucao_delta"
    write_deltalake(str(caminho), _pequena(), partition_by=["ano"])
    dt = lambda: DeltaTable(str(caminho))  # noqa: E731

    def adicionar():
        nova = _pequena().append_column("uf", pa.array(["DF", "GO", "SP"]))
        write_deltalake(str(caminho), nova, mode="append", schema_mode="merge")
        return f"colunas: {dt().schema().to_arrow().names}"

    def renomear():
        alter = dt().alter
        if not hasattr(alter, "rename_column"):
            raise NotImplementedError("o deltalake (Python) não tem operação de renomear coluna")
        alter.rename_column("municipio", "nome_municipio")

    def remover():
        alter = dt().alter
        if not hasattr(alter, "drop_columns"):
            raise NotImplementedError("o deltalake (Python) não tem operação de remover coluna")
        alter.drop_columns(["municipio"])

    def alargar():
        nova = _pequena().set_column(2, "mortos", pa.array([0, 1, 0], pa.int64()))
        write_deltalake(str(caminho), nova, mode="append", schema_mode="merge")
        tipo = pa.schema(dt().schema().to_arrow()).field("mortos").type
        if tipo != pa.int64():
            raise TypeError(f"a escrita passou, mas a coluna continuou {tipo}: os valores int64 "
                            "foram convertidos para o tipo antigo")
        return f"tipo de mortos: {tipo}"

    return {"adicionar_coluna": _tentar(adicionar), "renomear_coluna": _tentar(renomear),
            "remover_coluna": _tentar(remover), "alargar_int32_para_int64": _tentar(alargar)}


def iceberg(origem: Path, base: Path, lake_delta: Path) -> dict:
    try:
        import pyiceberg
        from pyiceberg.catalog.sql import SqlCatalog
        from pyiceberg.partitioning import PartitionField, PartitionSpec
        from pyiceberg.transforms import IdentityTransform
        from pyiceberg.types import LongType, StringType
    except ImportError:
        return {"pulado": "pyiceberg não instalado (ver o comando no topo do script)"}

    armazem = base / "iceberg"
    armazem.mkdir()
    catalogo = SqlCatalog("medicao", uri=f"sqlite:///{armazem}/catalogo.db",
                          warehouse=f"file://{armazem}")
    catalogo.create_namespace("prf")
    resultado = {"pyiceberg": pyiceberg.__version__}

    # Ocorrência inteira, particionada por ano, em zstd.
    tabela = DeltaTable(str(origem / "ocorrencia")).to_pyarrow_table()
    escrita = _tentar(lambda: _escrever_iceberg(catalogo, tabela, PartitionSpec, PartitionField,
                                                IdentityTransform))
    resultado["escrita_ocorrencia"] = escrita
    if escrita["ok"]:
        t = catalogo.load_table("prf.ocorrencia")
        pasta = Path(t.location().removeprefix("file://"))
        resultado["escrita_ocorrencia"].update(
            {"tamanho_mb": tamanho_mb(pasta), "arquivos_parquet": arquivos_parquet(pasta)})
        resultado["leitura_duckdb"] = _leitura_duckdb(lake_delta, t.metadata_location)

    # Evolução de esquema numa tabela pequena.
    pequena = catalogo.create_table("prf.evolucao", schema=_pequena().schema)
    pequena.append(_pequena())

    def adicionar():
        with pequena.update_schema() as u:
            u.add_column("uf", StringType())

    def renomear():
        with pequena.update_schema() as u:
            u.rename_column("municipio", "nome_municipio")
        return f"linhas lidas depois: {pequena.scan().to_arrow().num_rows}"

    def remover():
        with pequena.update_schema() as u:
            u.delete_column("nome_municipio")

    def alargar():
        with pequena.update_schema() as u:
            u.update_column("mortos", LongType())
        return f"tipo de mortos: {pequena.scan().to_arrow().schema.field('mortos').type}"

    resultado["evolucao"] = {"adicionar_coluna": _tentar(adicionar),
                             "renomear_coluna": _tentar(renomear),
                             "remover_coluna": _tentar(remover),
                             "alargar_int32_para_int64": _tentar(alargar)}
    return resultado


def _escrever_iceberg(catalogo, tabela, PartitionSpec, PartitionField, IdentityTransform):
    t0 = time.perf_counter()
    t = catalogo.create_table(
        "prf.ocorrencia", schema=tabela.schema,
        properties={"write.parquet.compression-codec": "zstd"})
    with t.update_spec() as spec:
        spec.add_field("ano", IdentityTransform(), "ano")
    t.append(tabela)
    return f"{round(time.perf_counter() - t0, 1)} s"


def _leitura_duckdb(lake_delta: Path, metadados_iceberg: str) -> dict:
    """Quem lê: o DuckDB lendo cada formato direto da pasta, sem o motor que escreveu."""
    resultado = {}
    con = duckdb.connect()
    for formato, extensao, fonte in (
        ("delta", "delta", f"delta_scan('{lake_delta / 'ocorrencia'}')"),
        ("iceberg", "iceberg", f"iceberg_scan('{metadados_iceberg.removeprefix('file://')}')"),
    ):
        def ler():
            con.execute(f"INSTALL {extensao}; LOAD {extensao};")
            return mediana_ms(lambda: con.execute(
                Q1.format(fonte=fonte, ultimo=ULTIMO_ANO)).fetchall())
        resultado[formato] = _tentar(ler)
    con.close()
    return resultado


# --- execução -------------------------------------------------------------------------


def main() -> int:
    inicio = time.monotonic()
    base = Path(tempfile.mkdtemp(prefix="medicao_e2_"))
    resultado: dict = {"medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "rodadas": RODADAS}
    try:
        with psycopg.connect(autocommit=True) as conn:
            resultado["postgres"] = conn.execute("SELECT version()").fetchone()[0].split(",")[0]
            resultado["tamanho_banco_mb"] = round(int(conn.execute(
                "SELECT pg_database_size(current_database())").fetchone()[0]) / 2**20)
            log("1. opção nula no banco (CREATE TABLE AS das views vigentes)")
            resultado["opcao_nula_no_banco"] = recarga_no_banco(conn)
        with psycopg.connect() as conn:
            conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            log("2 e 3. recarga completa e lote incremental em Delta")
            resultado["delta"] = caminhos_delta(conn, base)
            log("4. eventos de CDC numa republicação")
            resultado["cdc_eventos"] = eventos_cdc(conn)
        lake = Path(resultado["delta"].pop("lake"))
        log("5. compressão")
        resultado["compressao"] = compressao(lake, base / "compressao")
        log("6. Delta × Iceberg")
        resultado["delta_x_iceberg"] = {"delta_evolucao": evolucao_delta(base),
                                        "iceberg": iceberg(lake, base, lake)}
        resultado["versoes"] = {"duckdb": duckdb.__version__, "pyarrow": pa.__version__,
                                "deltalake": __import__("deltalake").__version__}
    finally:
        shutil.rmtree(base, ignore_errors=True)
    resultado["memoria_pico_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    resultado["duracao_s"] = round(time.monotonic() - inicio)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n")
    log(f"\nmedição terminada em {resultado['duracao_s']} s; resultado em {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
