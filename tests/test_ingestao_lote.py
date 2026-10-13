"""Testes da ingestão em lote da E2 (issue #31).

- Regra de reescrita e escrita de partição: rodam com tabelas Delta temporárias, sem banco.
- Tabelas do lake: conferem as tabelas Delta gravadas pelo serviço `ingestao-lote` contra as
  views *_vigente do banco. Precisam de `docker compose up` antes; sem as tabelas, são
  puladas com o motivo.

    docker compose up --build -d && docker compose wait ingestao-lote
    docker compose run --rm tests
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from banco import TesteComBanco

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from deltalake import DeltaTable

    from blackspot import ingestao_lote
except ImportError:  # Python local sem as dependências do projeto
    ingestao_lote = None

LAKE = Path(os.environ.get("BLACKSPOT_LAKE_TESTE", "/app/lake/lote"))

# Tabela Delta -> (view de origem, chave primária no banco). A PRF reusa IDs entre o
# BR-Brasil e o BAT, então a unicidade é pela mesma chave do banco, que começa por id_lote.
TABELAS = {
    "ocorrencia": ("ocorrencia_vigente", ["id_lote", "id"]),
    "veiculo": ("veiculo_vigente", ["id_lote", "id", "id_veiculo"]),
    "pessoa": ("pessoa_vigente", ["id_lote", "pesid"]),
    "ocorrencia_causa": ("ocorrencia_causa_vigente", ["id_lote", "id", "id_causa"]),
    "ocorrencia_tipo": ("ocorrencia_tipo_vigente", ["id_lote", "id", "ordem"]),
}


def sql_contagem(view: str) -> str:
    if view == "ocorrencia_vigente":
        return "SELECT ano, count(*) FROM ocorrencia_vigente GROUP BY ano"
    return (f"SELECT o.ano, count(*) FROM {view} t "
            f"JOIN ocorrencia_vigente o USING (id_lote, id) GROUP BY o.ano")


@unittest.skipIf(ingestao_lote is None, "deltalake/pyarrow indisponíveis")
class TestRegraDeEscrita(unittest.TestCase):
    """A lógica de idempotência e de reprocessamento de janela, sem banco."""

    def test_reescreve_so_quando_o_lote_vigente_muda(self):
        self.assertTrue(ingestao_lote.precisa_reescrever(set(), 4))       # partição nova
        self.assertFalse(ingestao_lote.precisa_reescrever({4}, 4))        # nada mudou
        self.assertTrue(ingestao_lote.precisa_reescrever({4}, 11))        # republicação
        self.assertTrue(ingestao_lote.precisa_reescrever({4, 11}, 11))    # partição misturada

    def _tabela(self, ano: int, id_lote: int, ids: list[int]) -> "pa.Table":
        return pa.table({"id": pa.array(ids, pa.int64()),
                         "id_lote": pa.array([id_lote] * len(ids), pa.int32()),
                         "ano": pa.array([ano] * len(ids), pa.int16())})

    def test_republicacao_reescreve_so_a_particao_do_ano(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = Path(d) / "ocorrencia"
            ingestao_lote.gravar_particao(caminho, self._tabela(2019, 3, [1, 2, 3]), 2019)
            ingestao_lote.gravar_particao(caminho, self._tabela(2020, 4, [4, 5]), 2020)
            # Republicação de 2020: lote novo, com uma linha a mais.
            ingestao_lote.gravar_particao(caminho, self._tabela(2020, 11, [4, 5, 6]), 2020)

            dt = DeltaTable(str(caminho))
            self.assertEqual(ingestao_lote.lotes_na_particao(caminho, 2019), {3})
            self.assertEqual(ingestao_lote.lotes_na_particao(caminho, 2020), {11})
            self.assertEqual(dt.to_pyarrow_dataset().count_rows(), 6)  # 3 de 2019 + 3 de 2020
            # A versão anterior continua no histórico (viagem no tempo).
            antiga = DeltaTable(str(caminho), version=dt.version() - 1)
            self.assertEqual(antiga.to_pyarrow_table(filters=[("ano", "=", 2020)]).num_rows, 2)

    def test_coluna_nova_na_origem_entra_na_tabela(self):
        # Mudança de esquema: a origem ganha uma coluna depois que a tabela já existe.
        with tempfile.TemporaryDirectory() as d:
            caminho = Path(d) / "pessoa"
            ingestao_lote.gravar_particao(caminho, self._tabela(2019, 3, [1, 2]), 2019)
            nova = self._tabela(2020, 4, [3]).append_column("nacionalidade", pa.array(["Brasileira"]))
            ingestao_lote.gravar_particao(caminho, nova, 2020)
            t = DeltaTable(str(caminho)).to_pyarrow_table()
            self.assertIn("nacionalidade", t.schema.names)
            por_ano = {r["ano"]: r["nacionalidade"] for r in t.to_pylist()}
            self.assertIsNone(por_ano[2019])
            self.assertEqual(por_ano[2020], "Brasileira")

    def test_escrita_usa_zstd_e_um_arquivo_por_particao(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = Path(d) / "ocorrencia"
            for ano, lote in ((2019, 3), (2020, 4)):
                ingestao_lote.gravar_particao(caminho, self._tabela(ano, lote, list(range(100))), ano)
            arquivos = [f.replace("file://", "") for f in DeltaTable(str(caminho)).file_uris()]
            self.assertEqual(len(arquivos), 2)
            codec = pq.ParquetFile(arquivos[0]).metadata.row_group(0).column(0).compression
            self.assertEqual(codec, "ZSTD")


@unittest.skipIf(ingestao_lote is None, "deltalake/pyarrow indisponíveis")
class TestTabelasDoLake(TesteComBanco):
    """As tabelas Delta gravadas pelo serviço `ingestao-lote` batem com a versão vigente."""

    @classmethod
    def setUpClass(cls):
        if not all((LAKE / t / "_delta_log").exists() for t in ("ocorrencia", "veiculo", "pessoa")):
            raise unittest.SkipTest(
                f"tabelas do lote não encontradas em {LAKE}; rode `docker compose up` antes")
        super().setUpClass()

    def contagens_na_origem(self, view: str) -> dict:
        return dict(self.todos(sql_contagem(view)))

    def test_contagens_por_ano_iguais_as_views_vigentes(self):
        for tabela, (view, _) in TABELAS.items():
            esperado = self.contagens_na_origem(view)
            if not esperado:
                continue
            t = DeltaTable(str(LAKE / tabela)).to_pyarrow_table(columns=["ano"])
            r = t.group_by("ano").aggregate([("ano", "count")])
            obtido = dict(zip(r["ano"].to_pylist(), r["ano_count"].to_pylist()))
            with self.subTest(tabela=tabela):
                self.assertEqual(obtido, esperado)

    def test_cada_particao_tem_so_o_lote_vigente(self):
        vigentes = dict(self.todos("SELECT ano, id_lote FROM lote_vigente"))
        for tabela, (view, _) in TABELAS.items():
            for ano in self.contagens_na_origem(view):  # só os anos com linhas na origem
                id_lote = vigentes[ano]
                with self.subTest(tabela=tabela, ano=ano):
                    self.assertEqual(ingestao_lote.lotes_na_particao(LAKE / tabela, ano), {id_lote})

    def test_sem_linha_duplicada(self):
        for tabela, (view, chave) in TABELAS.items():
            if not (LAKE / tabela / "_delta_log").exists():
                continue
            t = DeltaTable(str(LAKE / tabela)).to_pyarrow_table(columns=chave)
            distintas = t.group_by(chave).aggregate([]).num_rows
            with self.subTest(tabela=tabela):
                self.assertEqual(distintas, t.num_rows)

    def test_um_arquivo_por_particao_em_zstd(self):
        for tabela in TABELAS:
            if not (LAKE / tabela / "_delta_log").exists():
                continue
            arquivos = [f.replace("file://", "") for f in DeltaTable(str(LAKE / tabela)).file_uris()]
            particoes = [f.split("ano=")[1].split("/")[0] for f in arquivos]
            with self.subTest(tabela=tabela):
                self.assertEqual(len(particoes), len(set(particoes)))
                codec = pq.ParquetFile(arquivos[0]).metadata.row_group(0).column(0).compression
                self.assertEqual(codec, "ZSTD")


if __name__ == "__main__":
    unittest.main()
