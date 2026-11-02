"""Recarrega um ano da PRF mesmo que os arquivos não tenham mudado (backfill da E3).

Uso:
    python -m orquestracao.recarregar ANO

A carga normal (`python -m blackspot.load`) só carrega de novo um ano quando o SHA-256 de
algum arquivo muda. Para reprocessar um ano antigo com os mesmos arquivos, por exemplo
depois de mudar uma regra de conversão da carga, este script chama a mesma função da carga
(`carregar_ano`) sem essa verificação. O resultado é um lote novo do ano, que vira o
vigente; o lote anterior continua no banco (insert-only, ADR 0001).

Se a carga falhar, o ano inteiro é desfeito e a tentativa fica registrada como 'falhou',
como na carga normal.
"""

from __future__ import annotations

import sys
import time

import psycopg

from blackspot import load


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    ano = int(argv[1])
    por_ano = load.arquivos_por_ano()
    if ano not in por_ano:
        load.log(f"{ano} não está no sources.yaml (anos: {min(por_ano)}–{max(por_ano)})")
        return 2

    t0 = time.monotonic()
    with psycopg.connect() as conn:
        anterior = conn.execute("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ano,)).fetchone()
        try:
            with conn.transaction():
                r = load.carregar_ano(conn, ano, por_ano[ano])
        except Exception as e:
            load.log(f"  {ano}: FALHOU ({e.__class__.__name__}: {e})")
            conn.execute(
                "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (%s, 'falhou', now())", (ano,))
            conn.commit()
            return 1
        conn.commit()
        novo = conn.execute("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ano,)).fetchone()[0]

    load.log(f"  {ano}: lote vigente {anterior[0] if anterior else '—'} -> {novo}; "
             f"{r.ocorrencias} ocorrências, {r.veiculos} veículos, {r.pessoas} pessoas, "
             f"{r.causas} causas, {r.tipos} tipos ({time.monotonic() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
