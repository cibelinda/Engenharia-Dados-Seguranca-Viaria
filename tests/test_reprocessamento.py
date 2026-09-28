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

# Todas as tabelas em que a carga grava, incluindo os catálogos de causa e tipo, que
# recebem descrições novas conforme a carga as encontra.
CONTAGENS = """
    SELECT (SELECT count(*) FROM lote_carga), (SELECT count(*) FROM lote_arquivo),
           (SELECT count(*) FROM causa_acidente), (SELECT count(*) FROM tipo_acidente),
           (SELECT count(*) FROM ocorrencia), (SELECT count(*) FROM veiculo),
           (SELECT count(*) FROM pessoa), (SELECT count(*) FROM linha_rejeitada)
"""

# Chave de ordenação de cada tabela de dado dentro de um lote, para a impressão digital.
ORDEM = {
    "ocorrencia": "id",
    "veiculo": "id, id_veiculo",
    "pessoa": "pesid",
    "linha_rejeitada": "dataset, numero_linha",
}


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
        antes = {tabela: self.impressao(tabela, antigo) for tabela in ORDEM}

        with self.conn.transaction():  # savepoint; o tearDown desfaz tudo
            load.carregar_ano(self.conn, ano, arqs)

        novo = self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ano,))
        self.assertGreater(novo, antigo)
        for tabela in ORDEM:
            with self.subTest(tabela=tabela):
                # O lote antigo ficou intacto: nenhuma linha alterada, apagada ou trocada.
                self.assertEqual(self.impressao(tabela, antigo), antes[tabela])
                # O lote novo tem o mesmo conteúdo (os arquivos são os mesmos), noutra versão.
                self.assertEqual(self.impressao(tabela, novo), antes[tabela])
                if tabela != "linha_rejeitada":
                    self.assertGreater(self.um(f"SELECT count(*) FROM {tabela} WHERE id_lote = %s",
                                               (antigo,)), 0)
        # A view mostra só a versão nova; as tabelas guardam as duas.
        self.assertEqual(
            self.todos("SELECT DISTINCT id_lote FROM ocorrencia_vigente WHERE ano = %s", (ano,)), [(novo,)])
        self.assertEqual(
            self.um("SELECT count(DISTINCT id_lote) FROM ocorrencia WHERE ano = %s AND id_lote IN (%s, %s)",
                    (ano, antigo, novo)), 2)


    def impressao(self, tabela: str, id_lote: int) -> str:
        """MD5 de todas as linhas do lote, em ordem de chave, sem as colunas que identificam
        a versão (id_lote) ou são geradas pelo banco (id_rejeicao)."""
        colunas = [r[0] for r in self.todos(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s
                 AND column_name NOT IN ('id_lote', 'id_rejeicao')
               ORDER BY ordinal_position""", (tabela,))]
        linha = "ROW(" + ", ".join(colunas) + ")::text"
        return self.um(
            f"SELECT md5(coalesce(string_agg({linha}, E'\\n' ORDER BY {ORDEM[tabela]}), '')) "
            f"FROM {tabela} WHERE id_lote = %s", (id_lote,))


if __name__ == "__main__":
    unittest.main()
