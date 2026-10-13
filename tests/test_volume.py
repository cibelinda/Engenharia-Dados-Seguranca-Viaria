"""Testes de volume (issue #8): a carga não perde nem inventa linhas.

Rodam sobre o banco carregado: `docker compose run --rm tests`.
"""

from __future__ import annotations

import unittest

from banco import ANOS, ANOS_BAT, TesteComCarga


class TestVolume(TesteComCarga):

    def test_todo_ano_tem_lote_com_os_seus_arquivos(self):
        # Ocorrência e pessoa em todo ano; no BAT, também todas as causas e tipos.
        rows = self.todos(
            """SELECT l.ano, count(*), bool_and(a.linhas_lidas IS NOT NULL)
               FROM lote_vigente l JOIN lote_arquivo a USING (id_lote) GROUP BY l.ano""")
        self.assertEqual({ano: (n, ok) for ano, n, ok in rows},
                         {ano: (3 if ano in ANOS_BAT else 2, True) for ano in ANOS})

    def test_todo_ano_do_bat_tem_causas_e_tipos(self):
        for tabela in ("ocorrencia_causa_vigente", "ocorrencia_tipo_vigente"):
            with self.subTest(tabela=tabela):
                anos = {r[0] for r in self.todos(
                    f"SELECT DISTINCT o.ano FROM {tabela} t JOIN ocorrencia_vigente o USING (id_lote, id)")}
                self.assertEqual(anos, set(ANOS_BAT))

    def test_toda_ocorrencia_do_bat_tem_uma_causa_principal(self):
        n = self.um(
            """SELECT count(*) FROM ocorrencia_vigente o JOIN lote_vigente l USING (id_lote)
               WHERE l.sistema = 'bat' AND NOT EXISTS (
                   SELECT 1 FROM ocorrencia_causa_vigente c
                   WHERE c.id_lote = o.id_lote AND c.id = o.id AND c.causa_principal AND c.id_causa = o.id_causa)""")
        self.assertEqual(n, 0)

    def test_nenhum_ano_sem_linhas(self):
        for tabela in ("ocorrencia_vigente", "veiculo_vigente", "pessoa_vigente"):
            with self.subTest(tabela=tabela):
                rows = dict(self.todos(
                    f"""SELECT l.ano, count(t.id_lote) FROM lote_vigente l
                        LEFT JOIN {tabela} t USING (id_lote) GROUP BY l.ano"""))
                self.assertEqual([a for a in ANOS if not rows.get(a)], [])

    def test_rejeitadas_registradas_batem_com_o_lote(self):
        # lote_arquivo.linhas_rejeitadas é o que a carga contou; linha_rejeitada, o que gravou.
        rows = self.todos(
            """SELECT l.ano, a.dataset, a.linhas_rejeitadas,
                      (SELECT count(*) FROM linha_rejeitada r
                       WHERE r.id_lote = a.id_lote AND r.dataset = a.dataset)
               FROM lote_vigente l JOIN lote_arquivo a USING (id_lote)""")
        for ano, dataset, contadas, gravadas in rows:
            with self.subTest(ano=ano, dataset=dataset):
                self.assertEqual(contadas, gravadas)

    def test_ocorrencia_lidas_igual_carregadas_mais_rejeitadas(self):
        rows = self.todos(
            """SELECT l.ano, a.linhas_lidas, a.linhas_rejeitadas,
                      (SELECT count(*) FROM ocorrencia o WHERE o.id_lote = a.id_lote)
               FROM lote_vigente l JOIN lote_arquivo a USING (id_lote)
               WHERE a.dataset = 'ocorrencia'""")
        for ano, lidas, rejeitadas, carregadas in rows:
            with self.subTest(ano=ano):
                self.assertEqual(lidas, carregadas + rejeitadas)

    def test_pessoa_lidas_igual_carregadas_mais_rejeitadas(self):
        # Cada linha aceita do arquivo de pessoa vira uma pessoa, ou um veículo sem pessoa
        # (pesid = 0). Um veículo com pessoas aparece em várias linhas, mas é gravado uma vez.
        rows = self.todos(
            """SELECT l.ano, a.linhas_lidas, a.linhas_rejeitadas,
                      (SELECT count(*) FROM pessoa p WHERE p.id_lote = a.id_lote),
                      (SELECT count(*) FROM veiculo v WHERE v.id_lote = a.id_lote
                         AND NOT EXISTS (SELECT 1 FROM pessoa p WHERE p.id_lote = v.id_lote
                                         AND p.id = v.id AND p.id_veiculo = v.id_veiculo))
               FROM lote_vigente l JOIN lote_arquivo a USING (id_lote)
               WHERE a.dataset = 'pessoa'""")
        for ano, lidas, rejeitadas, pessoas, veiculos_sem_pessoa in rows:
            with self.subTest(ano=ano):
                self.assertEqual(lidas, pessoas + veiculos_sem_pessoa + rejeitadas)

    def test_lidas_iguais_ao_perfil_dos_arquivos(self):
        # Contagem independente: bench/perfil_recorte.py lê os ZIPs sem passar pela carga.
        perfil = self.perfil()
        esperado = {
            "ocorrencia": perfil["ocorrencia"]["registros_por_ano"],
            "pessoa": perfil["pessoa"]["registros_por_ano"],
        }
        rows = self.todos(
            """SELECT l.ano, a.dataset, a.linhas_lidas
               FROM lote_vigente l JOIN lote_arquivo a USING (id_lote)
               WHERE l.ano = ANY(%s) AND a.dataset IN ('ocorrencia', 'pessoa')""", (self.anos_iguais_ao_perfil(),))
        for ano, dataset, lidas in rows:
            with self.subTest(ano=ano, dataset=dataset):
                self.assertEqual(lidas, esperado[dataset][str(ano)])

    def test_rejeitadas_sao_so_os_casos_conhecidos(self):
        # Os problemas que o perfil achou e que o esquema não aceita. Um motivo novo indica
        # mudança na fonte ou na carga, e precisa ser olhado.
        #   BAT: IDs em notação científica e a linha com pesid = 0 e id_veiculo = 0; no
        #        arquivo de todas as causas, também as linhas das ocorrências rejeitadas.
        #   BR-Brasil: pessoa sem ocorrência no datatran (821 em 2007), id de ocorrência
        #        repetido no arquivo (0 a 7 por ano) e o que decorre dele (pesid repetido,
        #        veículo em duas ocorrências), e ano de fabricação entre 1851 e 1899.
        conhecidos = (
            r"id não inteiro: '\de\+\d+'",
            r"pesid = 0 e id_veiculo = 0: nem pessoa nem veículo",
            r"sem ocorrência carregada: id \d+",
            r"id repetido no arquivo: \d+",
            r"pesid repetido: \d+",
            r"id_veiculo \d+ em duas ocorrências",
            r"ano_fabricacao_veiculo inválido: '1[89]\d\d'",
        )
        perfil = self.perfil()
        anos = self.anos_iguais_ao_perfil()
        motivos = self.todos(
            """SELECT r.motivo, l.sistema, count(*) FROM linha_rejeitada r
               JOIN lote_vigente l USING (id_lote) WHERE l.ano = ANY(%s) GROUP BY 1, 2""", (anos,))
        for motivo, sistema, _ in motivos:
            with self.subTest(motivo=motivo):
                self.assertRegex(motivo, "^(" + "|".join(conhecidos) + ")$")
        # Contagem exata dos IDs em notação científica nos arquivos de ocorrência e pessoa,
        # contra a contagem independente do perfil.
        notacao = dict(self.todos(
            """SELECT l.ano, count(*) FROM linha_rejeitada r JOIN lote_vigente l USING (id_lote)
               WHERE l.ano = ANY(%s) AND r.dataset IN ('ocorrencia', 'pessoa')
                 AND r.motivo LIKE 'id não inteiro%%' GROUP BY 1""", (anos,)))
        for ano in anos:
            with self.subTest(ano=ano):
                esperado = (perfil["ocorrencia"]["ids_nao_numericos_por_ano"].get(str(ano), 0)
                            + perfil["pessoa"]["registros_com_id_nao_numerico_por_ano"].get(str(ano), 0))
                self.assertEqual(notacao.get(ano, 0), esperado)

if __name__ == "__main__":
    unittest.main()
