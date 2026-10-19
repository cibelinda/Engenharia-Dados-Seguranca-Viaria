"""Captura de mudanças (CDC) da E2: PostgreSQL -> Debezium -> Redpanda -> Delta.

- `conector`: registra o conector do Debezium no Kafka Connect.
- `eventos`: converte um evento do Debezium numa linha da tabela Delta.
- `consumidor`: lê os tópicos e grava as mudanças em /app/lake/cdc/<tabela>.
- `mudanca`: altera linhas no banco e mostra o efeito chegando no Delta (e mede a latência).
- `semantica`: derruba o consumidor no meio e reprocessa o tópico do início.

Detalhes em docs/e2/cdc.md.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAKE_DIR = REPO_ROOT / os.environ.get("BLACKSPOT_CDC_LAKE_DIR", "lake/cdc")
BROKER = os.environ.get("BLACKSPOT_CDC_BROKER", "localhost:9092")
CONNECT = os.environ.get("BLACKSPOT_CDC_CONNECT", "http://localhost:8083")

# Tabelas capturadas (contrato da E2). lote_carga vem primeiro: é dela que as outras tiram o
# ano da partição.
TABELAS = ("lote_carga", "ocorrencia", "veiculo", "pessoa")

# Os tópicos do Debezium se chamam <prefixo>.<esquema>.<tabela>.
PREFIXO = "blackspot"
GRUPO = "blackspot-cdc"


def topico(tabela: str) -> str:
    return f"{PREFIXO}.public.{tabela}"


def tabela_do_topico(nome: str) -> str:
    return nome.rsplit(".", 1)[1]
