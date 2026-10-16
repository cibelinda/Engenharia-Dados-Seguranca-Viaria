"""Registra o conector do Debezium no Kafka Connect e espera ele ficar RUNNING.

Uso:
    python -m blackspot.cdc.conector

Idempotente: `PUT /connectors/<nome>/config` cria o conector ou atualiza a configuração, e
rodar de novo com a mesma configuração não muda nada. O conector guarda nos tópicos do
Redpanda até onde leu o WAL, e o PostgreSQL guarda o mesmo no slot de replicação.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from blackspot.cdc import CONNECT, PREFIXO, TABELAS

NOME = "blackspot-postgres"


def configuracao() -> dict:
    return {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": os.environ.get("PGHOST", "db"),
        "database.port": os.environ.get("PGPORT", "5432"),
        "database.dbname": os.environ.get("PGDATABASE", "blackspot"),
        "database.user": os.environ.get("PGUSER", "blackspot"),
        "database.password": os.environ.get("PGPASSWORD", "blackspot"),
        "topic.prefix": PREFIXO,
        # pgoutput é o plugin de decodificação lógica nativo do PostgreSQL (sem extensão).
        "plugin.name": "pgoutput",
        "slot.name": "blackspot_cdc",
        "publication.name": "blackspot_cdc",
        # A publicação só inclui as tabelas capturadas: o WAL de lote_arquivo e
        # linha_rejeitada não vira evento.
        "publication.autocreate.mode": "filtered",
        "table.include.list": ",".join(f"public.{t}" for t in TABELAS),
        # Retrato inicial só de lote_carga (algumas dezenas de linhas), para o consumidor
        # saber o ano de cada lote. O histórico das outras tabelas (milhões de linhas) chega
        # pelo lote (#31); o CDC leva as mudanças a partir do registro do conector.
        "snapshot.mode": "initial",
        "snapshot.include.collection.list": "public.lote_carga",
        # numeric como texto, para não perder casas decimais (km, latitude, longitude).
        "decimal.handling.mode": "string",
        # Sem esquema em cada mensagem: o consumidor tira os tipos do próprio banco.
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": "false",
        # O evento de DELETE já diz tudo; o tombstone só serviria à compactação de tópico.
        "tombstones.on.delete": "false",
        # Heartbeat: confirma a posição no slot mesmo quando só tabelas fora da publicação
        # mudam, para o PostgreSQL não reter WAL à toa.
        "heartbeat.interval.ms": "10000",
        # Tópicos com uma partição (ordem total por tabela) e sem expiração, para o
        # consumidor poder reprocessar do início.
        "topic.creation.default.replication.factor": "1",
        "topic.creation.default.partitions": "1",
        "topic.creation.default.retention.ms": "-1",
    }


def requisicao(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"{CONNECT}{caminho}", data=dados, method=metodo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def main() -> int:
    requisicao("PUT", f"/connectors/{NOME}/config", configuracao())
    print(f"conector {NOME} registrado em {CONNECT}", file=sys.stderr, flush=True)
    for _ in range(60):
        try:
            status = requisicao("GET", f"/connectors/{NOME}/status")
        except urllib.error.HTTPError:
            status = {}
        estados = [status.get("connector", {}).get("state")]
        estados += [t.get("state") for t in status.get("tasks", [])]
        if "FAILED" in estados:
            print(json.dumps(status, indent=2), file=sys.stderr)
            return 1
        if len(estados) > 1 and set(estados) == {"RUNNING"}:
            print(f"conector {NOME}: RUNNING", file=sys.stderr, flush=True)
            return 0
        time.sleep(2)
    print(f"conector {NOME} não ficou RUNNING em 2 min: {status}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
