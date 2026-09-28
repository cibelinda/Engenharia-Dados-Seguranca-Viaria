"""Carga PROVISÓRIA: confere o esquema e conta os registros de cada CSV baixado.

Existe só para provar que a esteira do docker-compose funciona de ponta a ponta
(issue #5). Não grava nada: o esquema real (issue #3, db/migrations/) só aceita
linhas vinculadas a um lote de carga, e a carga real é a issue #4.

Uso:
    python -m blackspot.load

A conexão vem das variáveis padrão do PostgreSQL (PGHOST, PGPORT, PGDATABASE,
PGUSER, PGPASSWORD). A pasta dos arquivos vem de BLACKSPOT_RAW_DIR, como no
downloader.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / os.environ.get("BLACKSPOT_RAW_DIR", "data/raw")
ENCODING = "cp1252"  # todos os arquivos da PRF, sem BOM (docs/fontes/README.md)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def count_records(zip_path: Path) -> tuple[str, int]:
    """Devolve o nome do CSV dentro do ZIP e o número de registros, sem o cabeçalho."""
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"{zip_path.name}: esperado 1 CSV, encontrado(s) {len(members)}")
        with zf.open(members[0]) as raw:
            text = io.TextIOWrapper(raw, encoding=ENCODING, newline="")
            header = text.readline()
            delimiter = ";" if header.count(";") > header.count(",") else ","
            return members[0], sum(1 for _ in csv.reader(text, delimiter=delimiter))


def main() -> int:
    zips = sorted(RAW_DIR.glob("*.zip"))
    if not zips:
        log(f"nenhum ZIP em {RAW_DIR}; rode o download antes")
        return 1

    with psycopg.connect() as conn:
        # Confere que as migrações rodaram antes de dizer que a esteira está ok.
        if conn.execute("SELECT to_regclass('ocorrencia')").fetchone()[0] is None:
            log("tabela ocorrencia não existe; as migrações (serviço migrate) rodaram?")
            return 1

    for path in zips:
        _, n = count_records(path)
        log(f"  {path.name:<24} {n:>9} registros")
    log(f"\n{len(zips)} arquivo(s) contados; nada gravado (carga real: issue #4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
