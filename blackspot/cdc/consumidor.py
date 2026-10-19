"""Consumidor do CDC: tópicos do Debezium no Redpanda -> tabelas Delta em /app/lake/cdc/.

Uso:
    python -m blackspot.cdc.consumidor               # fica rodando (serviço cdc-consumidor)
    python -m blackspot.cdc.consumidor --ate-em-dia  # para quando não houver mais o que ler
    python -m blackspot.cdc.consumidor --do-inicio   # relê os tópicos desde o primeiro evento

Uma tabela Delta por tabela capturada, particionada pelo ano do lote, com Parquet em zstd
(as mesmas propriedades de escrita da ingestão em lote). Cada linha é um evento; a
descrição das colunas está em blackspot/cdc/eventos.py.

Semântica de entrega: pelo menos uma vez na leitura, sem duplicata na gravação.
- O offset só é confirmado no Redpanda DEPOIS que o lote de mensagens foi gravado no
  Delta. Se o consumidor cair entre as duas coisas, as mesmas mensagens são relidas.
- A gravação é idempotente: um MERGE pela chave do evento (LSN + chave primária) só
  insere o que ainda não está na tabela. Mensagem relida, por queda do consumidor ou
  por reenvio do Debezium depois de reiniciar, não vira linha nova.

Arquivos pequenos: cada lote de mensagens grava um arquivo por partição tocada. Quando o
consumidor fica ocioso, as partições com ARQUIVOS_PARA_COMPACTAR arquivos ou mais são
compactadas num arquivo só (OPTIMIZE do Delta). A compactação não muda nenhuma linha, e
os arquivos antigos continuam no histórico da tabela (viagem no tempo).
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pyarrow as pa
from confluent_kafka import OFFSET_BEGINNING, Consumer, KafkaError, TopicPartition
from deltalake import DeltaTable, write_deltalake

from blackspot.cdc import BROKER, GRUPO, LAKE_DIR, PREFIXO, TABELAS, tabela_do_topico, topico
from blackspot.cdc import eventos
from blackspot.ingestao_lote import ESCRITA

ASSINATURA = [rf"^{PREFIXO}\.public\.({'|'.join(TABELAS)})$"]
MENSAGENS_POR_LOTE = 20_000
# Uma mudança de uma linha vira um arquivo Parquet. Abaixo deste número de arquivos numa
# partição, compactar não compensa a versão nova que cria na tabela.
ARQUIVOS_PARA_COMPACTAR = 10


class QuedaSimulada(Exception):
    """Queda depois de gravar no Delta e antes de confirmar o offset (semantica.py)."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- Delta ------------------------------------------------------------------------


def sem_repetidos(tabela: pa.Table, chave: list[str]) -> pa.Table:
    """Mantém a primeira ocorrência de cada evento dentro do próprio lote de mensagens."""
    com_indice = tabela.append_column("_i", pa.array(range(tabela.num_rows), pa.int64()))
    primeiras = com_indice.group_by(chave).aggregate([("_i", "min")]).column("_i_min")
    return tabela.take(sorted(primeiras.to_pylist()))


def gravar_eventos(caminho: Path, tabela: pa.Table, chave: list[str]) -> int:
    """Grava os eventos que ainda não estão na tabela. Devolve quantos foram inseridos."""
    tabela = sem_repetidos(tabela, chave)
    if not (caminho / "_delta_log").exists():
        write_deltalake(str(caminho), tabela, partition_by=["ano"], mode="append",
                        writer_properties=ESCRITA)
        return tabela.num_rows
    anos = ", ".join(str(a) for a in sorted(set(tabela.column("ano").to_pylist())))
    # O filtro por ano limita o MERGE às partições tocadas por este lote de mensagens.
    predicado = " AND ".join([f"t.ano IN ({anos})", "t.ano = s.ano",
                              *(f"t.{c} = s.{c}" for c in chave)])
    metricas = (DeltaTable(str(caminho))
                .merge(tabela, predicado, source_alias="s", target_alias="t",
                       writer_properties=ESCRITA)
                .when_not_matched_insert_all()
                .execute())
    return metricas["num_target_rows_inserted"]


def compactar(caminho: Path, minimo: int = ARQUIVOS_PARA_COMPACTAR) -> tuple[int, int]:
    """Junta os arquivos das partições com `minimo` arquivos ou mais, um arquivo por partição.

    Devolve (arquivos removidos, arquivos adicionados). Não muda nenhuma linha.
    """
    if not (caminho / "_delta_log").exists():
        return 0, 0
    dt = DeltaTable(str(caminho))
    por_ano = Counter(f.split("ano=")[1].split("/")[0] for f in dt.file_uris())
    anos = sorted(a for a, n in por_ano.items() if n >= minimo)
    if not anos:
        return 0, 0
    m = dt.optimize.compact(partition_filters=[("ano", "in", anos)], writer_properties=ESCRITA)
    return m["numFilesRemoved"], m["numFilesAdded"]


# --- gravador ---------------------------------------------------------------------


def anos_no_topico() -> dict[int, int]:
    """id_lote -> ano, lido do tópico de lote_carga inteiro (algumas dezenas de eventos)."""
    c = Consumer({"bootstrap.servers": BROKER, "group.id": f"{GRUPO}-anos", "enable.auto.commit": False})
    try:
        baixo, alto = c.get_watermark_offsets(TopicPartition(topico("lote_carga"), 0), timeout=10)
        c.assign([TopicPartition(topico("lote_carga"), 0, baixo)])
        anos: dict[int, int] = {}
        lido, tentativas = baixo, 0
        while lido < alto and tentativas < 20:
            tentativas += 1
            for m in c.consume(1000, timeout=1):
                if m.error() is not None:
                    continue
                lido = m.offset() + 1
                ev = json.loads(m.value()) if m.value() else {}
                if ev.get("op") in ("c", "u", "r"):
                    anos[ev["after"]["id_lote"]] = ev["after"]["ano"]
        return anos
    finally:
        c.close()


class Gravador:
    """Converte as mensagens e grava cada tabela. Sabe o ano de cada lote."""

    def __init__(self, conn: psycopg.Connection, lake: Path = LAKE_DIR):
        self.conn = conn
        self.lake = lake
        self.esquemas = {t: eventos.esquema(conn, t) for t in TABELAS}
        # Tabelas gravadas desde a última compactação. Começa com todas, para compactar o que
        # uma execução anterior deixou.
        self.tocadas: set[str] = set(TABELAS)
        # id_lote -> ano. Vem do banco, da tabela Delta de lote_carga (que guarda também os
        # lotes já apagados do banco), dos próprios eventos de lote_carga e, em último caso,
        # do tópico de lote_carga (reprocessamento com a tabela Delta apagada).
        self.anos: dict[int, int] = dict(conn.execute("SELECT id_lote, ano FROM lote_carga").fetchall())
        delta = lake / "lote_carga"
        if (delta / "_delta_log").exists():
            t = DeltaTable(str(delta)).to_pyarrow_table(columns=["id_lote", "ano", "_op"])
            self.anos.update((r["id_lote"], r["ano"]) for r in t.to_pylist() if r["_op"] != "d")

    def ano_do_lote(self, id_lote: int) -> int:
        if id_lote not in self.anos:
            r = self.conn.execute("SELECT ano FROM lote_carga WHERE id_lote = %s", (id_lote,)).fetchone()
            if r is not None:
                self.anos[id_lote] = r[0]
            else:
                self.anos.update(anos_no_topico())
            if id_lote not in self.anos:
                raise RuntimeError(f"ano do lote {id_lote} desconhecido (nem no banco, nem nos eventos)")
        return self.anos[id_lote]

    def gravar(self, mensagens: list) -> dict[str, list[int]]:
        """Grava um lote de mensagens. Devolve {tabela: [lidos, inseridos]}."""
        por_tabela: dict[str, list] = defaultdict(list)
        for m in mensagens:
            if m.value() is not None:
                por_tabela[tabela_do_topico(m.topic())].append(m)
        gravado_em = datetime.now(timezone.utc)
        resumo: dict[str, list[int]] = {}
        # lote_carga primeiro: um lote novo chega no mesmo lote de mensagens que as linhas dele.
        for tabela in sorted(por_tabela, key=TABELAS.index):
            esq = self.esquemas[tabela]
            linhas = []
            for m in por_tabela[tabela]:
                ev = json.loads(m.value())
                ln = eventos.linha(ev, esq, self.ano_do_lote, (m.topic(), m.partition(), m.offset()),
                                   gravado_em)
                if ln is None:
                    continue
                if tabela == "lote_carga" and ln["_op"] != "d":
                    self.anos[ln["id_lote"]] = ln["ano"]
                linhas.append(ln)
            inseridos = 0
            if linhas:
                inseridos = gravar_eventos(self.lake / tabela, eventos.tabela_arrow(linhas, esq),
                                           esq.chave_do_evento)
                self.tocadas.add(tabela)
            resumo[tabela] = [len(linhas), inseridos]
            latencias = [(ln["_gravado_em"] - ln["_confirmado_em"]).total_seconds()
                         for ln in linhas if ln["_op"] != "r"]
            lat = f", latência até {max(latencias):.2f} s" if latencias else ""
            log(f"  {tabela:<10} {len(linhas):>6} evento(s), {inseridos:>6} inserido(s){lat}")
        return resumo

    def compactar_tocadas(self) -> None:
        """Compacta as tabelas gravadas desde a última vez (chamado com o consumidor ocioso)."""
        for tabela in sorted(self.tocadas, key=TABELAS.index):
            t0 = time.monotonic()
            removidos, adicionados = compactar(self.lake / tabela)
            if removidos:
                log(f"  {tabela:<10} compactada: {removidos} arquivo(s) -> {adicionados} "
                    f"({time.monotonic() - t0:.1f} s)")
        self.tocadas.clear()


# --- consumo ----------------------------------------------------------------------


def em_dia(consumer: Consumer) -> bool:
    """Todas as partições atribuídas já foram lidas até o fim?"""
    atribuidas = consumer.assignment()
    if not atribuidas:
        return False
    posicoes = consumer.position(atribuidas)
    confirmados = consumer.committed(atribuidas, timeout=10)
    for tp, pos, conf in zip(atribuidas, posicoes, confirmados):
        baixo, alto = consumer.get_watermark_offsets(tp, timeout=10, cached=False)
        # Sem mensagem lida nesta sessão, a posição ainda não existe: vale o offset confirmado.
        lido = pos.offset if pos.offset >= 0 else conf.offset if conf.offset >= 0 else baixo
        if lido < alto:
            return False
    return True


def consumir(do_inicio: bool = False, ate_em_dia: bool = False, falhar_apos_gravar: bool = False,
             lake: Path = LAKE_DIR, grupo: str = GRUPO) -> dict[str, list[int]]:
    """Lê os tópicos e grava no Delta. Devolve o total {tabela: [lidos, inseridos]}."""
    parar = False

    def ao_receber_sinal(*_):
        nonlocal parar
        parar = True

    signal.signal(signal.SIGTERM, ao_receber_sinal)
    consumer = Consumer({
        "bootstrap.servers": BROKER,
        "group.id": grupo,
        "auto.offset.reset": "earliest",
        # Offset confirmado à mão, só depois da gravação no Delta.
        "enable.auto.commit": False,
        # Os tópicos de veiculo e pessoa só existem depois da primeira mudança neles.
        "topic.metadata.refresh.interval.ms": 5000,
    })

    def ao_atribuir(c, particoes):
        if do_inicio:
            for p in particoes:
                p.offset = OFFSET_BEGINNING
            log(f"reprocessando do início: {', '.join(p.topic for p in particoes)}")
        c.assign(particoes)

    consumer.subscribe(ASSINATURA, on_assign=ao_atribuir)
    total: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    try:
        with psycopg.connect(autocommit=True) as conn:
            gravador = Gravador(conn, lake)
            log(f"consumindo {ASSINATURA[0]} de {BROKER} (grupo {grupo}) para {lake}")
            while not parar:
                mensagens = consumer.consume(MENSAGENS_POR_LOTE, timeout=0.5)
                validas = []
                for m in mensagens:
                    if m.error() is None:
                        validas.append(m)
                    elif m.error().code() != KafkaError._PARTITION_EOF:
                        log(f"erro do broker: {m.error()}")
                if not validas:
                    # Ocioso: hora de juntar os arquivos pequenos das últimas gravações.
                    gravador.compactar_tocadas()
                    if ate_em_dia and em_dia(consumer):
                        break
                    continue
                for tabela, (lidos, inseridos) in gravador.gravar(validas).items():
                    total[tabela][0] += lidos
                    total[tabela][1] += inseridos
                if falhar_apos_gravar:
                    raise QuedaSimulada()
                consumer.commit(asynchronous=False)
    finally:
        # Sem commit automático, fechar não confirma nada: o que não foi confirmado é relido.
        consumer.close()
    return dict(total)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--do-inicio", action="store_true", help="relê os tópicos desde o primeiro evento")
    p.add_argument("--ate-em-dia", action="store_true", help="para quando não houver mais o que ler")
    args = p.parse_args()
    inicio = time.monotonic()
    total = consumir(do_inicio=args.do_inicio, ate_em_dia=args.ate_em_dia)
    lidos = sum(v[0] for v in total.values())
    inseridos = sum(v[1] for v in total.values())
    log(f"consumidor terminou em {time.monotonic() - inicio:.0f} s: "
        f"{lidos} evento(s) lido(s), {inseridos} inserido(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
