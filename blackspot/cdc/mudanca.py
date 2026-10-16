"""Altera linhas no banco e mostra o efeito chegando nas tabelas Delta do CDC.

Uso (com o serviço cdc-consumidor rodando):
    python -m blackspot.cdc.mudanca republicar [--ano 2026] [--alterar 5] [--manter]
    python -m blackspot.cdc.mudanca latencia [--amostras 20]

republicar: simula a PRF republicando um ano, como a carga faria. Numa transação, cria um
    lote novo do ano com uma cópia do lote vigente, com `--alterar` ocorrências com o km
    corrigido (+0,1) e uma ocorrência a menos (com os veículos, pessoas, causas e tipos
    dela). Espera todos os eventos chegarem no Delta e mostra as linhas alteradas lá.
    Depois desfaz: apaga o lote inventado, para não deixar dado falso como versão vigente
    (os DELETEs também atravessam o fluxo). Com --manter, o lote fica.

latencia: mede o tempo entre o commit de uma mudança pequena (uma linha em lote_carga) e a
    chegada dela no Delta. Cada amostra insere um lote com status 'falhou' (não muda a
    versão vigente) e o apaga em seguida; as duas mudanças são medidas.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

import psycopg
import pyarrow.compute as pc
from deltalake import DeltaTable

from blackspot.cdc import LAKE_DIR, TABELAS

# Tabelas copiadas na republicação, na ordem das FKs. ocorrencia_causa e ocorrencia_tipo
# não são capturadas pelo CDC, mas fazem parte do lote: sem elas, as views vigentes de
# causas e tipos ficariam vazias para o ano.
COPIADAS = ("ocorrencia", "veiculo", "pessoa", "ocorrencia_causa", "ocorrencia_tipo")
ESPERA_MAXIMA = 600  # segundos


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def eventos_no_delta(tabela: str, ano: int, id_lote: int, op: str) -> int:
    caminho = LAKE_DIR / tabela
    if not (caminho / "_delta_log").exists():
        return 0
    ds = DeltaTable(str(caminho)).to_pyarrow_dataset()
    filtro = (pc.field("ano") == ano) & (pc.field("id_lote") == id_lote) & (pc.field("_op") == op)
    return ds.count_rows(filter=filtro)


def esperar(esperado: dict[str, int], ano: int, id_lote: int, op: str, t0: float,
            intervalo: float = 0.5) -> dict[str, float]:
    """Espera cada tabela ter `esperado[tabela]` eventos `op` do lote. Devolve o tempo de cada uma."""
    chegou: dict[str, float] = {}
    while len(chegou) < len(esperado):
        if time.monotonic() - t0 > ESPERA_MAXIMA:
            faltam = {t: eventos_no_delta(t, ano, id_lote, op) for t in esperado if t not in chegou}
            raise TimeoutError(f"eventos não chegaram em {ESPERA_MAXIMA} s: {faltam} de {esperado}")
        for tabela, n in esperado.items():
            if tabela not in chegou and eventos_no_delta(tabela, ano, id_lote, op) >= n:
                chegou[tabela] = time.monotonic() - t0
        time.sleep(intervalo)
    return chegou


def colunas(conn: psycopg.Connection, tabela: str) -> list[str]:
    return [r[0] for r in conn.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s AND is_generated = 'NEVER'
           ORDER BY ordinal_position""", (tabela,)).fetchall()]


# --- republicar -------------------------------------------------------------------


def republicar(ano: int, alterar: int, manter: bool) -> int:
    # autocommit: cada `conn.transaction()` abaixo é uma transação de verdade, confirmada no
    # fim do bloco (sem autocommit, o primeiro SELECT abriria uma transação, e o bloco
    # viraria só um savepoint dentro dela).
    with psycopg.connect(autocommit=True) as conn:
        r = conn.execute("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ano,)).fetchone()
        if r is None:
            log(f"{ano} não tem lote vigente; rode a carga antes")
            return 1
        antigo = r[0]
        ids = [i for (i,) in conn.execute(
            "SELECT id FROM ocorrencia WHERE id_lote = %s AND km IS NOT NULL ORDER BY id LIMIT %s",
            (antigo, alterar + 1)).fetchall()]
        alterados, removido = ids[:alterar], ids[alterar]
        km_antes = dict(conn.execute(
            "SELECT id, km FROM ocorrencia WHERE id_lote = %s AND id = ANY(%s)", (antigo, alterados)).fetchall())

        log(f"republicação simulada de {ano} (lote vigente: {antigo})")
        t_tx = time.monotonic()
        with conn.transaction():
            novo = conn.execute("INSERT INTO lote_carga (ano) VALUES (%s) RETURNING id_lote", (ano,)).fetchone()[0]
            conn.execute(
                """INSERT INTO lote_arquivo (id_lote, dataset, chave_manifesto, arquivo, sha256,
                                             tamanho_bytes, drive_last_modified, linhas_lidas, linhas_rejeitadas)
                   SELECT %s, dataset, chave_manifesto, arquivo, sha256, tamanho_bytes,
                          drive_last_modified, linhas_lidas, linhas_rejeitadas
                   FROM lote_arquivo WHERE id_lote = %s""", (novo, antigo))
            esperado = {"lote_carga": 1}
            for tabela in COPIADAS:
                cols = [c for c in colunas(conn, tabela) if c != "id_lote"]
                origem = ["CASE WHEN id = ANY(%(alterados)s) THEN km + 0.1 ELSE km END" if c == "km" else c
                          for c in cols]
                n = conn.execute(
                    f"""INSERT INTO {tabela} (id_lote, {', '.join(cols)})
                        SELECT %(novo)s, {', '.join(origem)} FROM {tabela}
                        WHERE id_lote = %(antigo)s AND id <> %(removido)s""",
                    {"novo": novo, "antigo": antigo, "removido": removido, "alterados": alterados}).rowcount
                if tabela in TABELAS:
                    esperado[tabela] = n
            conn.execute("UPDATE lote_carga SET status = 'concluido', finalizado_em = now() WHERE id_lote = %s",
                         (novo,))
        t0 = time.monotonic()
        total = sum(esperado.values()) + 1  # + o UPDATE de lote_carga
        log(f"  lote {novo} gravado em {t0 - t_tx:.1f} s: {total} mudanças nas tabelas capturadas "
            f"({', '.join(f'{t} {n}' for t, n in esperado.items())}, e o UPDATE de lote_carga)")
        log(f"  alterado: km de {len(alterados)} ocorrência(s); removida: ocorrência {removido}")

        log("\nesperando os eventos chegarem no Delta...")
        chegou = esperar(esperado, ano, novo, "c", t0)
        chegou["lote_carga (UPDATE)"] = esperar({"lote_carga": 1}, ano, novo, "u", t0)["lote_carga"]
        for tabela, s in chegou.items():
            log(f"  {tabela:<20} completa no Delta {s:6.1f} s depois do commit")
        log(f"  vazão: {total / max(chegou.values()):.0f} eventos/s")

        dt = DeltaTable(str(LAKE_DIR / "ocorrencia")).to_pyarrow_table(
            filters=[("ano", "=", ano), ("id_lote", "=", novo)], columns=["id", "km", "_op", "_lsn"])
        no_delta = {r["id"]: r["km"] for r in dt.to_pylist()}
        log(f"\nno Delta (/app/lake/cdc/ocorrencia, ano={ano}, id_lote={novo}):")
        for i in alterados:
            log(f"  ocorrência {i}: km {km_antes[i]} no lote {antigo} -> {no_delta.get(i)} no lote {novo}")
        log(f"  ocorrência {removido}: {'AUSENTE' if removido not in no_delta else 'presente'} no lote {novo}")

        if manter:
            log(f"\nlote {novo} mantido como vigente de {ano} (--manter)")
            return 0
        log(f"\ndesfazendo: apagando o lote {novo}")
        with conn.transaction():
            for tabela in (*reversed(COPIADAS), "lote_arquivo", "lote_carga"):
                conn.execute(f"DELETE FROM {tabela} WHERE id_lote = %s", (novo,))
        t0 = time.monotonic()
        chegou = esperar(esperado, ano, novo, "d", t0)
        log(f"  {sum(esperado.values())} DELETEs no Delta {max(chegou.values()):.1f} s depois do commit; "
            f"o lote vigente de {ano} voltou a ser o {antigo}")
    return 0


# --- latência ---------------------------------------------------------------------


def percentil(valores: list[float], p: float) -> float:
    v = sorted(valores)
    return v[min(len(v) - 1, round(p / 100 * (len(v) - 1)))]


def latencia(amostras: int, ano: int) -> int:
    fim_a_fim: list[float] = []
    lotes = []
    with psycopg.connect(autocommit=True) as conn:
        for _ in range(amostras):
            id_lote = conn.execute(
                "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (%s, 'falhou', now()) RETURNING id_lote",
                (ano,)).fetchone()[0]
            t0 = time.monotonic()
            fim_a_fim.append(esperar({"lote_carga": 1}, ano, id_lote, "c", t0, 0.02)["lote_carga"])
            conn.execute("DELETE FROM lote_carga WHERE id_lote = %s", (id_lote,))
            t0 = time.monotonic()
            fim_a_fim.append(esperar({"lote_carga": 1}, ano, id_lote, "d", t0, 0.02)["lote_carga"])
            lotes.append(id_lote)
    # A mesma medida vista de dentro do fluxo: commit no banco (_confirmado_em) -> gravação
    # no Delta (_gravado_em), pelos carimbos das próprias linhas.
    t = DeltaTable(str(LAKE_DIR / "lote_carga")).to_pyarrow_table(
        filters=[("ano", "=", ano)], columns=["id_lote", "_confirmado_em", "_gravado_em"])
    internos = [(r["_gravado_em"] - r["_confirmado_em"]).total_seconds()
                for r in t.to_pylist() if r["id_lote"] in set(lotes)]
    log(f"{len(fim_a_fim)} mudanças de uma linha (INSERT e DELETE em lote_carga):")
    for nome, v in (("commit -> visível no Delta (medido por fora)", fim_a_fim),
                    ("commit -> gravação (carimbos do evento)", internos)):
        log(f"  {nome:<46} mediana {statistics.median(v):.2f} s, p95 {percentil(v, 95):.2f} s, "
            f"mín {min(v):.2f} s, máx {max(v):.2f} s")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="comando", required=True)
    r = sub.add_parser("republicar", help="republicação simulada de um ano")
    r.add_argument("--ano", type=int, default=2026, help="ano republicado (padrão: 2026, o menor)")
    r.add_argument("--alterar", type=int, default=5, help="ocorrências com o km corrigido")
    r.add_argument("--manter", action="store_true", help="não desfaz a republicação no fim")
    lat = sub.add_parser("latencia", help="latência de mudanças de uma linha")
    lat.add_argument("--amostras", type=int, default=20)
    lat.add_argument("--ano", type=int, default=2026)
    args = p.parse_args()
    if args.comando == "republicar":
        return republicar(args.ano, args.alterar, args.manter)
    return latencia(args.amostras, args.ano)


if __name__ == "__main__":
    sys.exit(main())
