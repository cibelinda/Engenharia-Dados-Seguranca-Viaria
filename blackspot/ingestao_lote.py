"""Ingestão em lote da E2: PostgreSQL (versão vigente) -> tabelas Delta em Parquet.

Uso:
    python -m blackspot.ingestao_lote

Lê as views `ocorrencia_vigente`, `veiculo_vigente` e `pessoa_vigente` e grava três
tabelas Delta em /app/lake/lote/, particionadas pelo ano do acidente, com Parquet
comprimido em zstd. Veículo e pessoa herdam o ano da ocorrência.

Idempotência: cada linha guarda o `id_lote` de onde veio. Uma partição (ano) só é
reescrita quando o lote vigente daquele ano mudou; rodar de novo sem mudança na origem
não grava nada.

Dado atrasado e reprocessamento de janela: quando a PRF republica um ano já fechado
(como fez com 2024 em 23/09/2026), a carga da E1 cria um lote novo, ele vira o vigente
e esta ingestão reescreve só a partição daquele ano. A versão anterior continua no
histórico da tabela Delta (viagem no tempo), sem apagar nada.

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

# Parquet com zstd: a leitura é por agregação de poucas colunas sobre o recorte inteiro, e o
# zstd comprime mais que o snappy (padrão) com descompressão rápida. A comparação medida
# está no ADR 0002.
ESCRITA = WriterProperties(compression="ZSTD", compression_level=3)

# Para cada tabela: a view de origem e o SQL que traz um ano. Veículo e pessoa não têm
# data própria; o ano vem da ocorrência.
TABELAS = {
    "ocorrencia": (
        "ocorrencia_vigente",
        "SELECT o.* FROM ocorrencia_vigente o WHERE o.ano = %s",
    ),
    "veiculo": (
        "veiculo_vigente",
        """SELECT v.*, o.ano FROM veiculo_vigente v
           JOIN ocorrencia_vigente o USING (id_lote, id) WHERE o.ano = %s""",
    ),
    "pessoa": (
        "pessoa_vigente",
        """SELECT p.*, o.ano FROM pessoa_vigente p
           JOIN ocorrencia_vigente o USING (id_lote, id) WHERE o.ano = %s""",
    ),
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- esquema: tipos do PostgreSQL -> tipos do Arrow -------------------------------


def tipo_arrow(data_type: str, udt: str, precisao: int | None, escala: int | None) -> pa.DataType:
    if data_type == "ARRAY":
        return pa.list_(tipo_arrow(udt.lstrip("_"), udt.lstrip("_"), None, None))
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
        raise RuntimeError(f"tipo do PostgreSQL sem mapeamento para Arrow: {data_type}")
    return mapa[data_type]


def esquema(conn: psycopg.Connection, view: str, com_ano: bool) -> pa.Schema:
    colunas = conn.execute(
        """SELECT column_name, data_type, udt_name, numeric_precision, numeric_scale
           FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""",
        (view,),
    ).fetchall()
    campos = [pa.field(nome, tipo_arrow(dt, udt, p, s)) for nome, dt, udt, p, s in colunas]
    if com_ano:
        campos.append(pa.field("ano", pa.int16()))
    # Hora de processamento: quando esta ingestão gravou a linha (não existia na E1).
    campos.append(pa.field("processado_em", pa.timestamp("us", tz="UTC")))
    return pa.schema(campos)


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
    t = DeltaTable(str(caminho)).to_pyarrow_table(
        filters=[("ano", "=", ano)], columns=["id_lote"])
    return set(t.column("id_lote").unique().to_pylist())


def gravar_particao(caminho: Path, tabela: pa.Table, ano: int) -> None:
    """Grava a partição do ano, substituindo o que houver nela. Uma escrita por partição."""
    if not (caminho / "_delta_log").exists():
        write_deltalake(str(caminho), tabela, partition_by=["ano"], mode="append",
                        writer_properties=ESCRITA)
    else:
        write_deltalake(str(caminho), tabela, mode="overwrite", predicate=f"ano = {ano}",
                        writer_properties=ESCRITA)


def precisa_reescrever(no_delta: set[int], vigente: int) -> bool:
    """A partição só é reescrita se não tiver exatamente o lote vigente do ano."""
    return no_delta != {vigente}


# --- execução ---------------------------------------------------------------------


def main() -> int:
    inicio = time.monotonic()
    processado_em = datetime.now(timezone.utc)
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    gravadas = puladas = 0
    with psycopg.connect() as conn:
        vigentes = dict(conn.execute("SELECT ano, id_lote FROM lote_vigente ORDER BY ano").fetchall())
        if not vigentes:
            log("nenhum lote vigente no banco; rode a carga (serviço load) antes")
            return 1
        for nome, (view, sql) in TABELAS.items():
            schema = esquema(conn, view, com_ano=(nome != "ocorrencia"))
            caminho = LAKE_DIR / nome
            for ano, id_lote in vigentes.items():
                if not precisa_reescrever(lotes_na_particao(caminho, ano), id_lote):
                    puladas += 1
                    log(f"  {nome:<10} {ano}: lote {id_lote} já está no Delta; nada a fazer")
                    continue
                t0 = time.monotonic()
                tabela = ler_ano(conn, sql, ano, schema, processado_em)
                gravar_particao(caminho, tabela, ano)
                gravadas += 1
                log(f"  {nome:<10} {ano}: lote {id_lote}, {tabela.num_rows:>7} linhas gravadas "
                    f"({time.monotonic() - t0:.1f} s)")
    log(f"\ningestão em lote terminada em {time.monotonic() - inicio:.0f} s: "
        f"{gravadas} partição(ões) gravada(s), {puladas} sem mudança")
    return 0


if __name__ == "__main__":
    sys.exit(main())
