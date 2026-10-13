"""Ingestão em lote da E2: PostgreSQL (versão vigente) -> tabelas Delta em Parquet.

Uso:
    python -m blackspot.ingestao_lote

Lê as views *_vigente (ocorrência, veículo, pessoa e as causas e tipos de cada ocorrência)
e grava uma tabela Delta para cada uma em /app/lake/lote/, particionada pelo ano do
acidente, com Parquet comprimido em zstd. As tabelas que não têm data própria herdam o ano
da ocorrência.

Idempotência: cada linha guarda o `id_lote` de onde veio. Uma partição (ano) só é
reescrita quando o lote vigente daquele ano mudou; rodar de novo sem mudança na origem
não grava nada.

Dado atrasado e reprocessamento de janela: quando a PRF republica um ano já fechado
(como fez com 2024 em 23/09/2026), a carga cria um lote novo, ele vira o vigente e esta
ingestão reescreve só a partição daquele ano. A versão anterior continua no histórico da
tabela Delta (viagem no tempo), sem apagar nada.

Mudança de esquema: se a origem ganhar uma coluna, a escrita acrescenta a coluna na tabela
Delta (`schema_mode="merge"`); as partições antigas ficam com ela vazia até serem
reescritas.

A leitura inteira acontece numa única transação REPEATABLE READ: todas as tabelas e todos os
anos saem do mesmo retrato do banco, mesmo que uma carga termine no meio da ingestão.

A conexão vem das variáveis padrão do PostgreSQL (PGHOST, PGPORT, PGDATABASE, PGUSER,
PGPASSWORD). A pasta das tabelas vem de BLACKSPOT_LAKE_DIR (padrão: lake/lote).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pyarrow as pa
from deltalake import DeltaTable, WriterProperties, write_deltalake

REPO_ROOT = Path(__file__).resolve().parent.parent
LAKE_DIR = REPO_ROOT / os.environ.get("BLACKSPOT_LAKE_DIR", "lake/lote")

# Parquet com zstd: a leitura da pergunta de gestão agrega poucas colunas sobre o recorte
# inteiro, e o zstd costuma comprimir mais que o snappy (padrão) com descompressão rápida.
# A comparação medida fica no ADR 0004.
ESCRITA = WriterProperties(compression="ZSTD", compression_level=3)

# Tabela Delta -> view de origem. Só a ocorrência tem data; as outras recebem o ano pelo
# join com a ocorrência vigente (id_lote, id).
TABELAS = {
    "ocorrencia": "ocorrencia_vigente",
    "veiculo": "veiculo_vigente",
    "pessoa": "pessoa_vigente",
    "ocorrencia_causa": "ocorrencia_causa_vigente",
    "ocorrencia_tipo": "ocorrencia_tipo_vigente",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- esquema: tipos do PostgreSQL -> tipos do Arrow -------------------------------


def tipo_arrow(data_type: str, udt: str, precisao: int | None, escala: int | None) -> pa.DataType:
    if data_type == "ARRAY":
        return pa.list_(tipo_arrow(udt.lstrip("_"), udt.lstrip("_"), None, None))
    if data_type == "USER-DEFINED" and udt == "geometry":
        # PostGIS: lida como WKB (ST_AsBinary), o formato de geometria do GeoParquet.
        return pa.binary()
    mapa = {
        "bigint": pa.int64(), "int8": pa.int64(),
        "integer": pa.int32(), "int4": pa.int32(),
        "smallint": pa.int16(), "int2": pa.int16(),
        "boolean": pa.bool_(), "bool": pa.bool_(),
        "text": pa.string(), "character": pa.string(), "character varying": pa.string(),
        "bpchar": pa.string(), "varchar": pa.string(),
        "timestamp without time zone": pa.timestamp("us"),
        "timestamp with time zone": pa.timestamp("us", tz="UTC"),
    }
    if data_type == "numeric":
        return pa.decimal128(precisao, escala)
    if data_type not in mapa:
        raise RuntimeError(f"tipo do PostgreSQL sem mapeamento para Arrow: {data_type} ({udt})")
    return mapa[data_type]


def colunas_da_view(conn: psycopg.Connection, view: str) -> list[tuple]:
    return conn.execute(
        """SELECT column_name, data_type, udt_name, numeric_precision, numeric_scale
           FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""",
        (view,),
    ).fetchall()


def montar_leitura(conn: psycopg.Connection, view: str) -> tuple[str, pa.Schema]:
    """O SQL que traz um ano da view e o esquema Arrow correspondente."""
    colunas = colunas_da_view(conn, view)
    nomes = {c[0] for c in colunas}
    exprs, campos = [], []
    for nome, dt, udt, p, s in colunas:
        geom = dt == "USER-DEFINED" and udt == "geometry"
        exprs.append(f"ST_AsBinary(t.{nome}) AS {nome}" if geom else f"t.{nome}")
        campos.append(pa.field(nome, tipo_arrow(dt, udt, p, s)))
    if "ano" in nomes:
        sql = f"SELECT {', '.join(exprs)} FROM {view} t WHERE t.ano = %s"
    else:
        exprs.append("o.ano")
        campos.append(pa.field("ano", pa.int16()))
        sql = (f"SELECT {', '.join(exprs)} FROM {view} t "
               f"JOIN ocorrencia_vigente o USING (id_lote, id) WHERE o.ano = %s")
    # Hora de processamento: quando esta ingestão gravou a linha (não existia na E1).
    campos.append(pa.field("processado_em", pa.timestamp("us", tz="UTC")))
    return sql, pa.schema(campos)


def ler_ano(conn: psycopg.Connection, sql: str, ano: int, schema: pa.Schema,
            processado_em: datetime) -> pa.Table:
    nomes = [f.name for f in schema if f.name != "processado_em"]
    colunas: dict[str, list] = {n: [] for n in nomes}
    with conn.cursor(name=f"ingestao_{ano}") as cur:
        cur.itersize = 50_000
        cur.execute(sql, (ano,))
        for linha in cur:
            for nome, valor in zip(nomes, linha):
                colunas[nome].append(valor)
    n = len(colunas[nomes[0]])
    colunas["processado_em"] = [processado_em] * n
    return pa.Table.from_pydict(colunas, schema=schema)


# --- Delta ------------------------------------------------------------------------


def lotes_na_particao(caminho: Path, ano: int) -> set[int]:
    """Os id_lote gravados na partição do ano (vazio se a tabela ou a partição não existe)."""
    if not (caminho / "_delta_log").exists():
        return set()
    t = DeltaTable(str(caminho)).to_pyarrow_table(filters=[("ano", "=", ano)], columns=["id_lote"])
    return set(t.column("id_lote").unique().to_pylist())


def gravar_particao(caminho: Path, tabela: pa.Table, ano: int) -> None:
    """Grava a partição do ano, substituindo o que houver nela. Uma escrita por partição."""
    if not (caminho / "_delta_log").exists():
        write_deltalake(str(caminho), tabela, partition_by=["ano"], mode="append",
                        writer_properties=ESCRITA)
    else:
        write_deltalake(str(caminho), tabela, mode="overwrite", predicate=f"ano = {ano}",
                        schema_mode="merge", writer_properties=ESCRITA)


def precisa_reescrever(no_delta: set[int], vigente: int) -> bool:
    """A partição só é reescrita se não tiver exatamente o lote vigente do ano."""
    return no_delta != {vigente}


# --- execução ---------------------------------------------------------------------


def main() -> int:
    inicio = time.monotonic()
    processado_em = datetime.now(timezone.utc)
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    gravadas = puladas = vazias = 0
    with psycopg.connect() as conn:
        # Um único retrato do banco para todas as tabelas e anos.
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        vigentes = dict(conn.execute("SELECT ano, id_lote FROM lote_vigente ORDER BY ano").fetchall())
        if not vigentes:
            log("nenhum lote vigente no banco; rode a carga (serviço load) antes")
            return 1
        for nome, view in TABELAS.items():
            sql, schema = montar_leitura(conn, view)
            caminho = LAKE_DIR / nome
            for ano, id_lote in vigentes.items():
                if not precisa_reescrever(lotes_na_particao(caminho, ano), id_lote):
                    puladas += 1
                    continue
                t0 = time.monotonic()
                tabela = ler_ano(conn, sql, ano, schema, processado_em)
                if tabela.num_rows == 0:
                    # Ano sem linhas nesta tabela (ex.: causas e tipos do BR-Brasil). Nada a
                    # gravar; se uma versão anterior tinha linhas, a partição sai da tabela.
                    if (caminho / "_delta_log").exists() and lotes_na_particao(caminho, ano):
                        DeltaTable(str(caminho)).delete(f"ano = {ano}")
                    vazias += 1
                    continue
                gravar_particao(caminho, tabela, ano)
                gravadas += 1
                log(f"  {nome:<16} {ano}: lote {id_lote:>3}, {tabela.num_rows:>7} linhas gravadas "
                    f"({time.monotonic() - t0:.1f} s)")
    log(f"\ningestão em lote terminada em {time.monotonic() - inicio:.0f} s: "
        f"{gravadas} partição(ões) gravada(s), {puladas} sem mudança, "
        f"{vazias} ano(s) sem linhas na origem")
    return 0


if __name__ == "__main__":
    sys.exit(main())
