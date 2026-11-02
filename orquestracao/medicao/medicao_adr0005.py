"""Medição do ADR 0005: o que o dbt custa a mais que o SQL puro (a opção nula, `cron` + SQL).

Uso, dentro do container da orquestração, com o banco carregado:
    docker compose exec orquestracao python orquestracao/medicao/medicao_adr0005.py

Para cada uma de N rodadas de `dbt build`:
- o tempo total, do comando inteiro;
- o tempo do SQL, somando o que o próprio dbt registra por nó no run_results.json, separado
  em modelos/seeds/snapshots (o que um script SQL também faria) e testes;
- o resto é o custo do dbt: ler o projeto, compilar, consultar o catálogo do banco.

Mede também o `dbt parse` sozinho (ler e validar o projeto). Grava o resultado em JSON ao lado
deste script.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DBT_DIR = Path("/app/dbt")
TARGET = Path(os.environ.get("DBT_TARGET_PATH", "/tmp/dbt/target"))
SAIDA = Path(__file__).with_name("medicao_adr0005.json")
RODADAS = int(os.environ.get("RODADAS", "3"))


def dbt(*args: str) -> float:
    t0 = time.monotonic()
    subprocess.run(["dbt", *args, "--no-use-colors", "--quiet"], cwd=DBT_DIR, check=True)
    return time.monotonic() - t0


def rodada_build() -> dict:
    total = dbt("build")
    resultados = json.loads((TARGET / "run_results.json").read_text())["results"]
    por_tipo: dict[str, float] = {}
    for r in resultados:
        tipo = r["unique_id"].split(".")[0]  # model, seed, snapshot, test
        por_tipo[tipo] = por_tipo.get(tipo, 0.0) + r["execution_time"]
    sql_transformacao = sum(v for k, v in por_tipo.items() if k != "test")
    return {
        "total_s": round(total, 2),
        "nos": len(resultados),
        "por_tipo_s": {k: round(v, 2) for k, v in sorted(por_tipo.items())},
        "sql_transformacao_s": round(sql_transformacao, 2),
        "testes_s": round(por_tipo.get("test", 0.0), 2),
    }


def main() -> int:
    parse = [round(dbt("parse", "--no-partial-parse"), 2) for _ in range(RODADAS)]
    builds = [rodada_build() for _ in range(RODADAS)]
    mediana = lambda chave: round(statistics.median(b[chave] for b in builds), 2)  # noqa: E731
    resultado = {
        "medido_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dbt": subprocess.run(["dbt", "--version"], capture_output=True, text=True).stdout.split("\n")[1:3],
        "rodadas": RODADAS,
        "parse_s": parse,
        "build": builds,
        "mediana": {
            "total_s": mediana("total_s"),
            "sql_transformacao_s": mediana("sql_transformacao_s"),
            "testes_s": mediana("testes_s"),
        },
    }
    m = resultado["mediana"]
    # Os nós rodam em 4 threads: a soma do SQL pode passar do tempo total. O custo do dbt é
    # medido pelo parse, que é o que o dbt faz antes de mandar qualquer SQL.
    print(json.dumps(resultado, indent=1, ensure_ascii=False))
    print(f"\nbuild total {m['total_s']} s (mediana); SQL de transformação {m['sql_transformacao_s']} s, "
          f"testes {m['testes_s']} s (somados, 4 threads); parse {statistics.median(parse):.1f} s",
          file=sys.stderr)
    SAIDA.write_text(json.dumps(resultado, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
