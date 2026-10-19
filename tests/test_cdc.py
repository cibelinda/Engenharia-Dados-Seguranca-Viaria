"""Testes da captura de mudanças da E2 (issue #32).

- Conversão dos eventos e gravação idempotente: rodam com tabelas Delta temporárias, sem
  banco nem Redpanda.
- Tabelas do lake e fluxo: conferem as tabelas Delta gravadas pelo serviço `cdc-consumidor`
  e fazem uma mudança no banco que tem de atravessar o fluxo. Precisam de `docker compose up`
  antes; sem as tabelas do CDC, são pulados com o motivo. O teste do fluxo confirma (commit)
  uma linha em lote_carga, com status 'falhou' (não muda a versão vigente), e a apaga no fim.

    docker compose up --build -d && docker compose wait cdc-conector
    docker compose run --rm tests
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from banco import TesteComBanco, conectar

try:
    import pyarrow as pa
    from deltalake import DeltaTable

    from blackspot.cdc import consumidor, eventos
except ImportError:  # Python local sem as dependências do projeto
    eventos = None

LAKE = Path(os.environ.get("BLACKSPOT_CDC_TESTE", "/app/lake/cdc"))
ESPERA = 60  # segundos para uma mudança atravessar o fluxo

AGORA = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def esquema_ocorrencia() -> "eventos.Esquema":
    """Um pedaço de ocorrencia com um tipo de cada (sem banco)."""
    campos = [pa.field("id_lote", pa.int32()), pa.field("id", pa.int64()),
              pa.field("ocorrido_em", pa.timestamp("us")), pa.field("km", pa.decimal128(6, 1)),
              pa.field("tracado_via", pa.list_(pa.string())), pa.field("uso_solo_urbano", pa.bool_())]
    schema = pa.schema(eventos.METADADOS + campos + [pa.field("ano", pa.int16())])
    return eventos.Esquema("ocorrencia", schema, campos, ["id_lote", "id"])


def evento(op: str, lsn: int, antes: dict | None, depois: dict | None) -> dict:
    return {"op": op, "before": antes, "after": depois, "ts_ms": 1792152000100,
            "source": {"lsn": lsn, "txId": 7, "ts_ms": 1792152000000}}


DEPOIS = {"id_lote": 3, "id": 42, "ocorrido_em": 1767268800000000,  # 2026-01-01 12:00
          "km": "12.5", "tracado_via": ["Reta", "Declive"], "uso_solo_urbano": False}


@unittest.skipIf(eventos is None, "deltalake/pyarrow/confluent-kafka indisponíveis")
class TestEventos(unittest.TestCase):
    """Evento do Debezium -> linha da tabela Delta."""

    def setUp(self):
        self.esq = esquema_ocorrencia()
        self.anos = {3: 2026}

    def linha(self, ev: dict) -> dict | None:
        return eventos.linha(ev, self.esq, self.anos.__getitem__, ("t", 0, 9), AGORA)

    def test_insert_converte_os_tipos(self):
        ln = self.linha(evento("c", 100, None, DEPOIS))
        self.assertEqual(ln["ocorrido_em"], datetime(2026, 1, 1, 12, 0))  # sem fuso, como no banco
        self.assertEqual(ln["km"], Decimal("12.5"))
        self.assertEqual(ln["tracado_via"], ["Reta", "Declive"])
        self.assertEqual(ln["ano"], 2026)  # do lote
        self.assertEqual((ln["_op"], ln["_lsn"], ln["_tx_id"], ln["_offset"]), ("c", 100, 7, 9))
        self.assertEqual(ln["_confirmado_em"], datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc))
        # A linha cabe no esquema Arrow da tabela.
        self.assertEqual(eventos.tabela_arrow([ln], self.esq).num_rows, 1)

    def test_delete_usa_o_antes_e_traz_so_a_chave(self):
        ln = self.linha(evento("d", 101, {"id_lote": 3, "id": 42}, None))
        self.assertEqual((ln["_op"], ln["id_lote"], ln["id"], ln["ano"]), ("d", 3, 42, 2026))
        self.assertIsNone(ln["km"])

    def test_lote_carga_tira_o_ano_da_propria_linha_e_do_lote_no_delete(self):
        campos = [pa.field("id_lote", pa.int32()), pa.field("ano", pa.int16()),
                  pa.field("status", pa.string())]
        esq = eventos.Esquema("lote_carga", pa.schema(eventos.METADADOS + campos), campos, ["id_lote"])
        ins = eventos.linha(evento("c", 1, None, {"id_lote": 9, "ano": 2019, "status": "em_carga"}),
                            esq, {}.__getitem__, ("t", 0, 0), AGORA)
        self.assertEqual(ins["ano"], 2019)
        # No DELETE só a chave é dado: o Debezium preenche as colunas NOT NULL fora da chave
        # com 0 e ''. O ano vem do lote, que o consumidor já conhece, e não do 0.
        de = eventos.linha(evento("d", 2, {"id_lote": 9, "ano": 0, "status": ""}, None), esq,
                           {9: 2019}.__getitem__, ("t", 0, 1), AGORA)
        self.assertEqual((de["ano"], de["status"]), (2019, None))

    def test_mensagem_sem_mudanca_e_ignorada(self):
        self.assertIsNone(self.linha({"op": "t", "before": None, "after": None, "source": {}}))


@unittest.skipIf(eventos is None, "deltalake/pyarrow/confluent-kafka indisponíveis")
class TestGravacaoIdempotente(unittest.TestCase):
    """Reler eventos (queda do consumidor, reprocessamento) não duplica linhas."""

    def setUp(self):
        self.esq = esquema_ocorrencia()
        self.dir = tempfile.TemporaryDirectory()
        self.caminho = Path(self.dir.name) / "ocorrencia"

    def tearDown(self):
        self.dir.cleanup()

    def tabela(self, *evs: dict, offset: int = 0) -> "pa.Table":
        linhas = [eventos.linha(ev, self.esq, {3: 2026, 4: 2025}.__getitem__, ("t", 0, offset + i), AGORA)
                  for i, ev in enumerate(evs)]
        return eventos.tabela_arrow(linhas, self.esq)

    def gravar(self, t: "pa.Table") -> int:
        return consumidor.gravar_eventos(self.caminho, t, self.esq.chave_do_evento)

    def linhas(self) -> int:
        return DeltaTable(str(self.caminho)).to_pyarrow_dataset().count_rows()

    def test_reprocessar_nao_duplica(self):
        lote = self.tabela(evento("c", 100, None, DEPOIS), evento("c", 101, None, {**DEPOIS, "id": 43}))
        self.assertEqual(self.gravar(lote), 2)
        # Mesmos eventos relidos, em outros offsets (ex.: reenvio do Debezium depois de reiniciar).
        self.assertEqual(self.gravar(self.tabela(*[evento("c", 100 + i, None, {**DEPOIS, "id": 42 + i})
                                                   for i in range(2)], offset=50)), 0)
        self.assertEqual(self.linhas(), 2)

    def test_evento_repetido_no_mesmo_lote_de_mensagens(self):
        ev = evento("c", 100, None, DEPOIS)
        self.assertEqual(self.gravar(self.tabela(ev, ev, ev)), 1)
        self.assertEqual(self.gravar(self.tabela(ev, evento("d", 200, {"id_lote": 3, "id": 42}, None))), 1)
        self.assertEqual(self.linhas(), 2)

    def test_mesma_linha_em_mudancas_diferentes_sao_eventos_diferentes(self):
        # INSERT e DELETE da mesma chave primária: LSNs diferentes, os dois ficam.
        self.gravar(self.tabela(evento("c", 100, None, DEPOIS)))
        self.gravar(self.tabela(evento("d", 101, {"id_lote": 3, "id": 42}, None)))
        ops = DeltaTable(str(self.caminho)).to_pyarrow_table(columns=["_op"]).column("_op").to_pylist()
        self.assertEqual(sorted(ops), ["c", "d"])

    def test_particiona_pelo_ano_do_lote(self):
        self.gravar(self.tabela(evento("c", 100, None, DEPOIS),
                                evento("c", 101, None, {**DEPOIS, "id_lote": 4})))
        arquivos = DeltaTable(str(self.caminho)).file_uris()
        self.assertEqual(sorted(f.split("ano=")[1].split("/")[0] for f in arquivos), ["2025", "2026"])

    def test_compactacao_junta_os_arquivos_sem_mudar_as_linhas(self):
        # Uma mudança por lote de mensagens: um arquivo por evento na partição de 2026.
        for i in range(12):
            self.gravar(self.tabela(evento("c", 100 + i, None, {**DEPOIS, "id": 42 + i})))
        self.gravar(self.tabela(evento("c", 200, None, {**DEPOIS, "id_lote": 4})))  # 2025: 1 arquivo
        dt = DeltaTable(str(self.caminho))
        antes = sorted(dt.to_pyarrow_table(columns=["_lsn"]).column("_lsn").to_pylist())
        self.assertEqual(len(dt.file_uris()), 13)

        self.assertEqual(consumidor.compactar(self.caminho, minimo=10), (12, 1))
        dt = DeltaTable(str(self.caminho))
        arquivos = sorted(f.split("ano=")[1].split("/")[0] for f in dt.file_uris())
        self.assertEqual(arquivos, ["2025", "2026"])  # um arquivo por partição
        self.assertEqual(sorted(dt.to_pyarrow_table(columns=["_lsn"]).column("_lsn").to_pylist()), antes)
        # Sem partição acima do mínimo, não cria versão nova; e reler os eventos continua sem duplicar.
        self.assertEqual(consumidor.compactar(self.caminho, minimo=10), (0, 0))
        self.assertEqual(self.gravar(self.tabela(evento("c", 100, None, DEPOIS))), 0)
        self.assertEqual(self.linhas(), 13)


@unittest.skipIf(eventos is None, "deltalake/pyarrow/confluent-kafka indisponíveis")
class TestTabelasDoCdc(TesteComBanco):
    """As tabelas Delta gravadas pelo serviço `cdc-consumidor`."""

    @classmethod
    def setUpClass(cls):
        if not (LAKE / "lote_carga" / "_delta_log").exists():
            raise unittest.SkipTest(f"tabelas do CDC não encontradas em {LAKE}; rode `docker compose up` antes")
        super().setUpClass()

    def test_sem_evento_repetido(self):
        for tabela in ("lote_carga", "ocorrencia", "veiculo", "pessoa"):
            if not (LAKE / tabela / "_delta_log").exists():
                continue
            chave = eventos.esquema(self.conn, tabela).chave_do_evento
            t = DeltaTable(str(LAKE / tabela)).to_pyarrow_table(columns=chave)
            with self.subTest(tabela=tabela):
                self.assertEqual(t.group_by(chave).aggregate([]).num_rows, t.num_rows)

    def test_estado_de_lote_carga_reconstruido_dos_eventos_igual_ao_banco(self):
        # lote_carga entra inteira no retrato inicial; aplicando os eventos em ordem de LSN,
        # o estado tem de ser o do banco.
        t = DeltaTable(str(LAKE / "lote_carga")).to_pyarrow_table(columns=["_lsn", "_op", "id_lote", "status"])
        estado: dict[int, str] = {}
        for ev in sorted(t.to_pylist(), key=lambda r: r["_lsn"]):
            if ev["_op"] == "d":
                estado.pop(ev["id_lote"], None)
            else:
                estado[ev["id_lote"]] = ev["status"]
        self.assertEqual(estado, dict(self.todos("SELECT id_lote, status FROM lote_carga")))


@unittest.skipIf(eventos is None, "deltalake/pyarrow/confluent-kafka indisponíveis")
class TestFluxo(unittest.TestCase):
    """Uma mudança confirmada no banco chega no Delta (precisa do cdc-consumidor rodando)."""

    @classmethod
    def setUpClass(cls):
        if not (LAKE / "lote_carga" / "_delta_log").exists():
            raise unittest.SkipTest(f"tabelas do CDC não encontradas em {LAKE}; rode `docker compose up` antes")
        cls.conn = conectar()
        cls.conn.autocommit = True  # a mudança precisa ser confirmada para virar evento

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def esperar(self, id_lote: int, op: str) -> float:
        t0 = time.monotonic()
        while time.monotonic() - t0 < ESPERA:
            t = DeltaTable(str(LAKE / "lote_carga")).to_pyarrow_table(
                filters=[("ano", "=", 2026), ("id_lote", "=", id_lote), ("_op", "=", op)], columns=["_op"])
            if t.num_rows:
                return time.monotonic() - t0
            time.sleep(0.2)
        self.fail(f"evento {op} do lote {id_lote} não chegou no Delta em {ESPERA} s; "
                  "o serviço cdc-consumidor está rodando?")

    def test_insert_e_delete_atravessam_o_fluxo(self):
        id_lote = self.conn.execute(
            "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (2026, 'falhou', now()) RETURNING id_lote"
        ).fetchone()[0]
        try:
            self.esperar(id_lote, "c")
        finally:
            self.conn.execute("DELETE FROM lote_carga WHERE id_lote = %s", (id_lote,))
        self.esperar(id_lote, "d")


if __name__ == "__main__":
    unittest.main()
