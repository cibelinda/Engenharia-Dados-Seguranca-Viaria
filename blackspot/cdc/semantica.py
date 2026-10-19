"""Demonstra a semântica de entrega do CDC: pelo menos uma vez + gravação idempotente.

Uso (com o serviço cdc-consumidor PARADO, porque este script faz o papel dele):
    docker compose stop cdc-consumidor
    docker compose run --rm cdc-demo python -m blackspot.cdc.semantica
    docker compose start cdc-consumidor

Passos:
1. Conta as linhas das tabelas Delta do CDC.
2. Faz duas mudanças no banco (INSERT e DELETE de um lote com status 'falhou', que não muda
   a versão vigente) e espera os eventos chegarem no Redpanda.
3. Derruba o consumidor no meio: ele grava os eventos no Delta e cai ANTES de confirmar o
   offset. O Redpanda continua achando que os eventos não foram lidos.
4. Sobe o consumidor de novo: ele relê os mesmos eventos (pelo menos uma vez), e o MERGE não
   insere nada (idempotente).
5. Reprocessa os tópicos do início: relê todos os eventos e não insere nada.
6. Confere: as tabelas cresceram só os 2 eventos novos, e nenhuma tem evento repetido.
"""

from __future__ import annotations

import sys
import time

import psycopg
from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient
from deltalake import DeltaTable

from blackspot.cdc import BROKER, GRUPO, LAKE_DIR, TABELAS, topico
from blackspot.cdc import eventos
from blackspot.cdc.consumidor import QuedaSimulada, consumir


def log(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


def contagens(chaves: dict[str, list[str]]) -> dict[str, tuple[int, int]]:
    """{tabela: (linhas, eventos distintos pela chave do evento)}."""
    r = {}
    for tabela, chave in chaves.items():
        caminho = LAKE_DIR / tabela
        if not (caminho / "_delta_log").exists():
            continue
        t = DeltaTable(str(caminho)).to_pyarrow_table(columns=chave)
        r[tabela] = (t.num_rows, t.group_by(chave).aggregate([]).num_rows)
    return r


def atraso() -> dict[str, int]:
    """Eventos no tópico que o grupo ainda não confirmou, por tabela."""
    c = Consumer({"bootstrap.servers": BROKER, "group.id": GRUPO, "enable.auto.commit": False})
    try:
        existentes = set(c.list_topics(timeout=10).topics)
        tps = [TopicPartition(topico(t), 0) for t in TABELAS if topico(t) in existentes]
        r = {}
        for tp in c.committed(tps, timeout=10):
            baixo, alto = c.get_watermark_offsets(tp, timeout=10)
            r[tp.topic.rsplit(".", 1)[1]] = alto - (tp.offset if tp.offset >= 0 else baixo)
        return r
    finally:
        c.close()


def fim_do_topico(tabela: str) -> int:
    c = Consumer({"bootstrap.servers": BROKER, "group.id": f"{GRUPO}-espia"})
    try:
        return c.get_watermark_offsets(TopicPartition(topico(tabela), 0), timeout=10)[1]
    finally:
        c.close()


def resumo(nome: str, total: dict[str, list[int]]) -> None:
    lidos = sum(v[0] for v in total.values())
    inseridos = sum(v[1] for v in total.values())
    log(f"  => {nome}: {lidos} evento(s) lido(s), {inseridos} inserido(s) no Delta")


def main() -> int:
    # O AdminClient precisa continuar referenciado até a resposta chegar.
    admin = AdminClient({"bootstrap.servers": BROKER})
    grupo = admin.describe_consumer_groups([GRUPO], request_timeout=10)[GRUPO].result(timeout=15)
    if grupo.members:
        log(f"o grupo {GRUPO} tem consumidor ativo; pare o serviço antes:\n"
            "  docker compose stop cdc-consumidor")
        return 1

    with psycopg.connect(autocommit=True) as conn:
        chaves = {t: eventos.esquema(conn, t).chave_do_evento for t in TABELAS}
        antes = contagens(chaves)
        log("1. tabelas Delta do CDC antes: "
            + ", ".join(f"{t} {n}" for t, (n, _) in antes.items()))

        log("\n2. duas mudanças no banco (INSERT e DELETE em lote_carga)")
        fim = fim_do_topico("lote_carga")
        id_lote = conn.execute(
            "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (2026, 'falhou', now()) RETURNING id_lote"
        ).fetchone()[0]
        conn.execute("DELETE FROM lote_carga WHERE id_lote = %s", (id_lote,))
        for _ in range(120):
            if fim_do_topico("lote_carga") >= fim + 2:
                break
            time.sleep(0.5)
        log(f"  lote {id_lote}: 2 eventos no tópico; não confirmados pelo grupo: {atraso()}")

    log("\n3. consumidor cai depois de gravar no Delta e antes de confirmar o offset")
    try:
        consumir(falhar_apos_gravar=True)
    except QuedaSimulada:
        pass
    log(f"  não confirmados pelo grupo depois da queda: {atraso()}")

    log("\n4. consumidor volta: relê o que não foi confirmado")
    retomada = consumir(ate_em_dia=True)
    resumo("retomada", retomada)

    log("\n5. reprocessamento dos tópicos desde o primeiro evento")
    reprocessado = consumir(do_inicio=True, ate_em_dia=True)
    resumo("reprocessamento", reprocessado)

    depois = contagens(chaves)
    log("\n6. conferência")
    ok = True
    for tabela, (n, distintos) in depois.items():
        n_antes = antes.get(tabela, (0, 0))[0]
        esperado = n_antes + (2 if tabela == "lote_carga" else 0)
        certo = n == esperado == distintos
        ok &= certo
        log(f"  {tabela:<10} antes {n_antes:>7}, depois {n:>7} (esperado {esperado}), "
            f"eventos distintos {distintos:>7} {'ok' if certo else 'ERRO'}")
    relidos = sum(v[0] - v[1] for t in (retomada, reprocessado) for v in t.values())
    log(f"\nsem a gravação idempotente, a retomada e o reprocessamento teriam duplicado "
        f"{relidos} linha(s)." if ok else "\nFALHOU: há eventos repetidos ou faltando")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
