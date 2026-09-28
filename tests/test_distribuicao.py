"""Testes de distribuição (issue #8): o dado carregado tem a forma esperada.

Os limiares vêm do que foi medido na carga de 2026-09-28, com folga, e estão
explicados em cada constante. Um teste que falha aqui não é necessariamente um erro
da carga: pode ser uma republicação da PRF que mudou o dado, e precisa ser olhado.
"""

from __future__ import annotations

import unittest

from banco import ANOS, TesteComCarga

# Maior variação anual observada no BAT: -22,6% (2017 -> 2018). Acima de 30%, algo mudou
# no registro ou na carga (docs/caracterizacao-da-carga.md, "Crescimento e sazonalidade").
VARIACAO_ANUAL_MAX = 0.30
# Acidentes com morto ou ferido grave variam menos: no máximo 7,5% (2023 -> 2024).
VARIACAO_ANUAL_GRAVES_MAX = 0.15

# Percentual máximo de NULL por campo. Medido: coordenadas 0,005% (33 pares fora do
# limite em 2017), idade 9,9% (0, negativa ou acima de 110 na fonte), ano de fabricação
# 6,7% (0 na fonte), classificação 0,002% ('NA' em 10 ocorrências), tipo de acidente
# 0,006% (41 vazios).
NULOS_MAX = {
    ("ocorrencia_vigente", "latitude"): 0.001,
    ("ocorrencia_vigente", "classificacao_acidente"): 0.001,
    ("ocorrencia_vigente", "id_tipo"): 0.001,
    ("pessoa_vigente", "idade"): 0.12,
    ("veiculo_vigente", "ano_fabricacao"): 0.10,
}

# Coordenadas fora de uma caixa que contém o Brasil. Medido: 20 (0,003%), já apontadas
# em docs/modelagem-origem.md; a carga não corrige coordenada dentro do limite válido.
CAIXA_BRASIL = {"lat": (-34, 6), "lon": (-74, -28)}
FORA_DO_BRASIL_MAX = 0.001


class TestDistribuicao(TesteComCarga):

    def por_ano(self, filtro: str = "true") -> dict[int, int]:
        return dict(self.todos(f"SELECT ano, count(*) FROM ocorrencia_vigente WHERE {filtro} GROUP BY ano"))

    def assertVariacaoAnual(self, contagens: dict[int, int], limite: float):
        for ano in ANOS[1:]:
            with self.subTest(ano=ano):
                variacao = contagens[ano] / contagens[ano - 1] - 1
                self.assertLessEqual(abs(variacao), limite,
                                     f"{ano - 1} -> {ano}: {variacao:+.1%}")

    def test_ocorrencias_por_ano_sem_salto(self):
        self.assertVariacaoAnual(self.por_ano(), VARIACAO_ANUAL_MAX)

    def test_acidentes_graves_por_ano_sem_salto(self):
        self.assertVariacaoAnual(self.por_ano("mortos > 0 OR feridos_graves > 0"), VARIACAO_ANUAL_GRAVES_MAX)

    def test_todo_mes_tem_ocorrencias(self):
        vazios = self.todos(
            """SELECT a.ano, m.mes FROM generate_series(2017, 2025) a(ano)
               CROSS JOIN generate_series(1, 12) m(mes)
               WHERE NOT EXISTS (SELECT 1 FROM ocorrencia_vigente o
                                 WHERE o.ano = a.ano AND extract(month FROM o.ocorrido_em) = m.mes)""")
        self.assertEqual(vazios, [])

    def test_nulos_abaixo_do_limiar(self):
        for (tabela, coluna), limite in NULOS_MAX.items():
            with self.subTest(campo=f"{tabela}.{coluna}"):
                taxa = self.um(f"SELECT avg(({coluna} IS NULL)::int)::float FROM {tabela}")
                self.assertLessEqual(taxa, limite, f"{taxa:.3%} de NULL")

    def test_campos_do_trecho_nunca_nulos(self):
        # br, uf e km montam o trecho da pergunta de gestão.
        n = self.um("SELECT count(*) FROM ocorrencia_vigente WHERE br IS NULL OR uf IS NULL OR km IS NULL "
                    "OR municipio IS NULL")
        self.assertEqual(n, 0)

    def test_coordenadas_dentro_do_brasil(self):
        (lat_min, lat_max), (lon_min, lon_max) = CAIXA_BRASIL["lat"], CAIXA_BRASIL["lon"]
        taxa = self.um(
            """SELECT avg((NOT (latitude BETWEEN %s AND %s AND longitude BETWEEN %s AND %s))::int)::float
               FROM ocorrencia_vigente WHERE latitude IS NOT NULL""",
            (lat_min, lat_max, lon_min, lon_max))
        self.assertLessEqual(taxa, FORA_DO_BRASIL_MAX, f"{taxa:.3%} fora do Brasil")

    def test_data_dentro_do_ano_do_arquivo(self):
        n = self.um("SELECT count(*) FROM ocorrencia_vigente o JOIN lote_vigente l USING (id_lote) "
                    "WHERE o.ano <> l.ano")
        self.assertEqual(n, 0)

    def test_mortos_nao_passam_de_pessoas(self):
        self.assertEqual(self.um("SELECT count(*) FROM ocorrencia_vigente WHERE mortos > pessoas"), 0)

    def test_mortos_batem_com_obitos_das_pessoas(self):
        # Consistência entre os dois arquivos da PRF: a contagem da ocorrência é igual ao
        # número de pessoas com estado_fisico = 'Óbito'. Vale em 100% do recorte.
        n = self.um(
            """SELECT count(*) FROM ocorrencia_vigente o
               LEFT JOIN (SELECT id_lote, id, count(*) FILTER (WHERE estado_fisico = 'Óbito') AS obitos
                          FROM pessoa_vigente GROUP BY id_lote, id) p USING (id_lote, id)
               WHERE o.mortos <> coalesce(p.obitos, 0)""")
        self.assertEqual(n, 0)

    def test_ano_de_fabricacao_nao_e_futuro(self):
        n = self.um("""SELECT count(*) FROM veiculo_vigente v JOIN lote_vigente l USING (id_lote)
                       WHERE v.ano_fabricacao > l.ano + 1""")
        self.assertEqual(n, 0)

    def test_br_zero_fica_no_banco(self):
        # Decisão da squad (docs/pergunta-e-recorte.md, "Decidido depois"): as ocorrências com
        # br = 0 ficam no banco, e as consultas do ranking as tiram com WHERE br <> 0.
        br_zero = self.um("SELECT count(*) FROM ocorrencia_vigente WHERE br = 0")
        if list(self.anos_iguais_ao_perfil()) == list(ANOS):
            self.assertEqual(br_zero, self.perfil()["ocorrencia"]["br_zero"])
        else:
            self.assertGreater(br_zero, 0)


if __name__ == "__main__":
    unittest.main()
