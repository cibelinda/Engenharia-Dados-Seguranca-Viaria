"""Testes de reprocessamento (issue #8): rodar a carga de novo e receber um arquivo
republicado fazem o que a decisão insert-only promete (ADR 0001).

- Mesmos arquivos: a segunda carga não grava nada.
- Arquivo com SHA-256 novo: a carga cria um lote novo do ano, que vira o vigente, e o
  lote anterior continua no banco, intacto. A simulação roda dentro da transação do
  teste e é desfeita no fim.

Precisam dos ZIPs baixados (volume rawdata no compose) e do banco carregado.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from banco import ANOS, EXIGIR_BANCO, TesteComCarga

try:
    from blackspot import load
except ImportError:  # Python local sem psycopg/PyYAML
    if EXIGIR_BANCO:
        raise
    load = None

# Ano usado na simulação de republicação: o menor do recorte, para o teste ser rápido.
ANO_REPUBLICADO = 2020

CONTAGENS = """
    SELECT (SELECT count(*) FROM lote_carga), (SELECT count(*) FROM lote_arquivo),
           (SELECT count(*) FROM ocorrencia), (SELECT count(*) FROM veiculo),
           (SELECT count(*) FROM pessoa), (SELECT count(*) FROM linha_rejeitada)
"""


@unittest.skipIf(load is None, "blackspot.load indisponível")
class TestReprocessamento(TesteComCarga):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                cls.arquivos = load.arquivos_do_recorte()
        except SystemExit as e:  # ZIPs ausentes
            cls.conn.close()
            if EXIGIR_BANCO:
                raise AssertionError(f"arquivos do recorte indisponíveis: {e}") from None
            raise unittest.SkipTest(f"arquivos do recorte indisponíveis: {e}") from None

    def test_segunda_carga_nao_grava_nada(self):
        for ano in ANOS:
            if not load.ja_carregado(self.conn, ano, self.arquivos[ano]):
                self.skipTest(f"{ano} não está carregado com os arquivos atuais; rode a carga antes")
        antes = self.conn.execute(CONTAGENS).fetchone()
        self.conn.rollback()

        with contextlib.redirect_stderr(io.StringIO()) as saida:
            codigo = load.main()

        self.assertEqual(codigo, 0, saida.getvalue())
        self.assertEqual(self.conn.execute(CONTAGENS).fetchone(), antes)
        self.assertEqual(saida.getvalue().count("já carregado"), len(ANOS))

    def test_arquivo_republicado_cria_lote_novo_e_preserva_o_antigo(self):
        ano = ANO_REPUBLICADO
        # Cópia dos arquivos do ano com um SHA-256 diferente: é como a carga enxerga uma
        # republicação da PRF (mesmo nome, conteúdo novo).
        arqs = {d: load.Arquivo(a.dataset, a.chave, a.path, "f" * 64, a.tamanho, a.drive_last_modified)
                for d, a in self.arquivos[ano].items()}
        antigo = self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ano,))
        self.assertFalse(load.ja_carregado(self.conn, ano, arqs))

        with self.conn.transaction():  # savepoint; o tearDown desfaz tudo
            load.carregar_ano(self.conn, ano, arqs)

        novo = self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ano,))
        self.assertGreater(novo, antigo)
        for tabela in ("ocorrencia", "veiculo", "pessoa", "linha_rejeitada"):
            with self.subTest(tabela=tabela):
                n_antigo = self.um(f"SELECT count(*) FROM {tabela} WHERE id_lote = %s", (antigo,))
                n_novo = self.um(f"SELECT count(*) FROM {tabela} WHERE id_lote = %s", (novo,))
                self.assertEqual(n_novo, n_antigo)  # mesmo conteúdo, nova versão
                if tabela != "linha_rejeitada":
                    self.assertGreater(n_antigo, 0)
        # A view mostra só a versão nova; as tabelas guardam as duas.
        self.assertEqual(
            self.todos("SELECT DISTINCT id_lote FROM ocorrencia_vigente WHERE ano = %s", (ano,)), [(novo,)])
        self.assertEqual(
            self.um("SELECT count(DISTINCT id_lote) FROM ocorrencia WHERE ano = %s AND id_lote IN (%s, %s)",
                    (ano, antigo, novo)), 2)


if __name__ == "__main__":
    unittest.main()
