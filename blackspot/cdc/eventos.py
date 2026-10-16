"""Evento do Debezium -> linha da tabela Delta do CDC.

Cada linha da tabela Delta é um evento (a tabela é a trilha de mudanças, não o estado
atual). Além das colunas da tabela de origem, a linha guarda:

    _op            c (insert), u (update), d (delete) ou r (linha do retrato inicial)
    _lsn           posição do evento no WAL; com a chave primária, identifica o evento
    _tx_id         transação do PostgreSQL
    _confirmado_em hora do commit no banco
    _capturado_em  hora em que o Debezium leu o evento
    _gravado_em    hora em que o consumidor gravou o evento no Delta (hora de processamento)
    _topico, _particao, _offset   de onde o consumidor leu

No DELETE, só a chave primária vem preenchida (o PostgreSQL só manda a chave no WAL); as
outras colunas ficam nulas.

As colunas e os tipos vêm do próprio banco (information_schema), com o mesmo mapeamento
de tipos da ingestão em lote. Colunas geradas (ocorrencia.ano, ocorrencia.geom,
lote_carga.sistema) não passam pelo WAL e ficam de fora; `ano`, a partição, é o ano do
lote da linha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
import pyarrow as pa

from blackspot.ingestao_lote import tipo_arrow

UTC = pa.timestamp("us", tz="UTC")

METADADOS = [
    pa.field("_op", pa.string()),
    pa.field("_lsn", pa.int64()),
    pa.field("_tx_id", pa.int64()),
    pa.field("_confirmado_em", UTC),
    pa.field("_capturado_em", UTC),
    pa.field("_gravado_em", UTC),
    pa.field("_topico", pa.string()),
    pa.field("_particao", pa.int32()),
    pa.field("_offset", pa.int64()),
]

EPOCA = datetime(1970, 1, 1)


@dataclass
class Esquema:
    tabela: str
    schema: pa.Schema       # metadados + colunas da origem + ano
    colunas: list[pa.Field]  # só as colunas da origem que passam pelo WAL
    chave: list[str]         # chave primária na origem

    @property
    def chave_do_evento(self) -> list[str]:
        """Identifica um evento: a mesma mudança relida tem o mesmo LSN e a mesma chave."""
        return ["_lsn", *self.chave]


def esquema(conn: psycopg.Connection, tabela: str) -> Esquema:
    colunas = conn.execute(
        """SELECT column_name, data_type, udt_name, numeric_precision, numeric_scale
           FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s AND is_generated = 'NEVER'
           ORDER BY ordinal_position""",
        (tabela,),
    ).fetchall()
    if not colunas:
        raise RuntimeError(f"tabela {tabela} não encontrada no banco")
    chave = [r[0] for r in conn.execute(
        """SELECT a.attname FROM pg_index i
           JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
           WHERE i.indrelid = %s::regclass AND i.indisprimary
           ORDER BY array_position(i.indkey, a.attnum)""",
        (tabela,),
    ).fetchall()]
    campos = [pa.field(n, tipo_arrow(dt, udt, p, s)) for n, dt, udt, p, s in colunas]
    nomes = {c.name for c in campos}
    particao = [] if "ano" in nomes else [pa.field("ano", pa.int16())]
    return Esquema(tabela, pa.schema(METADADOS + campos + particao), campos, chave)


# --- valores ----------------------------------------------------------------------


def _micros(v: int | None) -> datetime | None:
    return None if v is None else datetime.fromtimestamp(v / 1_000_000, tz=timezone.utc)


def valor(v, tipo: pa.DataType):
    """Valor do JSON do Debezium -> valor Python do tipo Arrow da coluna."""
    if v is None:
        return None
    if pa.types.is_timestamp(tipo):
        if tipo.tz is None:
            # timestamp sem fuso (ocorrido_em): MicroTimestamp, microssegundos desde a época,
            # na hora local do evento. Fica sem fuso, como no banco.
            return EPOCA + timedelta(microseconds=v)
        # timestamptz: ZonedTimestamp, texto ISO 8601 em UTC.
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    if pa.types.is_decimal(tipo):
        return Decimal(v)  # decimal.handling.mode=string
    return v


def ano_da_linha(tabela: str, dados: dict, ano_do_lote) -> int:
    if tabela == "lote_carga" and dados.get("ano") is not None:
        return dados["ano"]
    return ano_do_lote(dados["id_lote"])


def linha(evento: dict, esq: Esquema, ano_do_lote, origem: tuple[str, int, int],
          gravado_em: datetime) -> dict | None:
    """O evento do Debezium como linha da tabela Delta. None para mensagens sem mudança."""
    op = evento.get("op")
    if op not in ("c", "u", "d", "r"):
        return None
    dados = evento["before"] if op == "d" else evento["after"]
    fonte = evento["source"]
    linha = {
        "_op": op,
        "_lsn": fonte["lsn"],
        "_tx_id": fonte.get("txId"),
        "_confirmado_em": _micros(fonte.get("ts_us") or fonte["ts_ms"] * 1000),
        "_capturado_em": _micros(evento.get("ts_us") or evento["ts_ms"] * 1000),
        "_gravado_em": gravado_em,
        "_topico": origem[0],
        "_particao": origem[1],
        "_offset": origem[2],
    }
    for campo in esq.colunas:
        # No DELETE, o Debezium preenche as colunas NOT NULL fora da chave com o valor
        # padrão do tipo (0, ''), e não com NULL: só a chave é dado de verdade.
        v = dados.get(campo.name) if op != "d" or campo.name in esq.chave else None
        linha[campo.name] = valor(v, campo.type)
    linha["ano"] = ano_da_linha(esq.tabela, linha, ano_do_lote)
    return linha


def tabela_arrow(linhas: list[dict], esq: Esquema) -> pa.Table:
    return pa.Table.from_pylist(linhas, schema=esq.schema)
