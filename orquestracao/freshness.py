"""Freshness e SLA das tabelas de consumo (E3, issue #44).

As tabelas de consumo são as que o painel lê (docs/e3/README.md). A métrica é a **idade**
de cada uma: quantas horas se passaram desde o último `dbt build` que terminou sem erro. O
SLA é a idade máxima prometida.

Junto com a idade, a verificação registra o que explica um atraso:
- `carga_pendente_h`: há quanto tempo existe uma carga concluída no banco que ainda não
  chegou à tabela (a carga terminou depois do último build). 0 quando não há;
- `ultima_verificacao_prf_h`: há quanto tempo a esteira conferiu os arquivos da PRF;
- `dado_mais_recente`: a data do acidente mais recente, que depende de quando a PRF
  publica, e não da esteira. É informativo, fora do SLA.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

SCHEMA = "analitico_marts"
TABELAS_CONSUMO = ("mart_risco_trecho_ano", "mart_risco_municipio_ano")

# A PRF publica uma vez por mês, e a esteira roda uma vez por dia (03:00). 24 h entre duas
# execuções, mais 2 h de folga para as novas tentativas de uma etapa que falhou.
SLA_HORAS = float(os.environ.get("ORQUESTRACAO_SLA_HORAS", "26"))


@dataclass
class Medida:
    agora: datetime
    ultimo_build: datetime | None
    ultima_carga: datetime | None
    ultima_verificacao_prf: datetime | None
    dado_mais_recente: datetime | None
    tabelas: dict[str, int | None]  # tabela -> linhas (None = não existe)

    @staticmethod
    def horas(desde: datetime | None, ate: datetime) -> float | None:
        return None if desde is None else round((ate - desde).total_seconds() / 3600, 2)

    @property
    def idade_h(self) -> float | None:
        return self.horas(self.ultimo_build, self.agora)

    @property
    def carga_pendente_h(self) -> float:
        if self.ultima_carga is None or (self.ultimo_build and self.ultima_carga <= self.ultimo_build):
            return 0.0
        return self.horas(self.ultima_carga, self.agora)

    @property
    def faltando(self) -> list[str]:
        return [t for t, n in self.tabelas.items() if n is None]

    @property
    def dentro_do_sla(self) -> bool:
        return self.idade_h is not None and self.idade_h <= SLA_HORAS


def medir(ultimo_build: datetime | None, ultima_verificacao_prf: datetime | None) -> Medida:
    """Lê do banco o que falta para a medida. Os dois horários vêm do histórico do Dagster."""
    with psycopg.connect() as conn:
        agora, ultima_carga, dado = conn.execute(
            """SELECT now(),
                      (SELECT max(finalizado_em) FROM lote_carga WHERE status = 'concluido'),
                      (SELECT max(ocorrido_em) FROM ocorrencia_vigente)""").fetchone()
        tabelas: dict[str, int | None] = {}
        for t in TABELAS_CONSUMO:
            existe = conn.execute("SELECT to_regclass(%s)", (f"{SCHEMA}.{t}",)).fetchone()[0]
            tabelas[t] = (conn.execute(f"SELECT count(*) FROM {SCHEMA}.{t}").fetchone()[0]
                          if existe else None)
    return Medida(agora, ultimo_build, ultima_carga, ultima_verificacao_prf, dado, tabelas)


def de_timestamp(ts: float | None) -> datetime | None:
    return None if ts is None else datetime.fromtimestamp(ts, tz=timezone.utc)
