"""Testes de volume (issue #8): a carga não perde nem inventa linhas.

Rodam sobre o banco carregado: `docker compose run --rm tests`.
"""

from __future__ import annotations

import unittest

from banco import ANOS, TesteComCarga


class TestVolume(TesteComCarga):

    def test_todo_ano_do_recorte_tem_lote_com_os_dois_arquivos(self):
        rows = self.todos(
            """SELECT l.ano, count(*), bool_and(a.linhas_lidas IS NOT NULL)
               FROM lote_vigente l JOIN lote_arquivo a USING (id_lote) GROUP BY l.ano""")
        self.assertEqual({ano: (n, ok) for ano, n, ok in rows}, {ano: (2, True) for ano in ANOS})

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
               WHERE l.ano = ANY(%s)""", (self.anos_iguais_ao_perfil(),))
        for ano, dataset, lidas in rows:
            with self.subTest(ano=ano, dataset=dataset):
                self.assertEqual(lidas, esperado[dataset][str(ano)])

    def test_rejeitadas_sao_so_os_casos_conhecidos(self):
        # Os únicos problemas que o perfil achou e que o esquema não aceita: IDs em
        # notação científica e a linha com pesid = 0 e id_veiculo = 0. Um motivo novo
        # indica mudança na fonte ou na carga, e precisa ser olhado.
        perfil = self.perfil()
        anos = self.anos_iguais_ao_perfil()
        motivos = self.todos(
            """SELECT r.motivo, count(*) FROM linha_rejeitada r
               JOIN lote_vigente l USING (id_lote) WHERE l.ano = ANY(%s) GROUP BY r.motivo""", (anos,))
        for motivo, _ in motivos:
            with self.subTest(motivo=motivo):
                self.assertRegex(motivo, r"^id não inteiro: '\de\+\d+'$|^pesid = 0 e id_veiculo = 0")
        if list(anos) == list(ANOS):
            esperado = (perfil["ocorrencia"]["ids_nao_numericos"]
                        + perfil["pessoa"]["registros_com_id_nao_numerico"] + 1)
            self.assertEqual(sum(n for _, n in motivos), esperado)


if __name__ == "__main__":
    unittest.main()
