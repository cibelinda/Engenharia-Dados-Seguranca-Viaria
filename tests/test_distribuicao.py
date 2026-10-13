"""Testes de distribuição (issue #8): o dado carregado tem a forma esperada.

Os limiares vêm do que foi medido na carga de 2026-09-28 (BAT) e na carga do
dataset completo de 2026-10-12 (BR-Brasil), com folga, e estão explicados em cada
constante. Um teste que falha aqui não é necessariamente um erro
da carga: pode ser uma republicação da PRF que mudou o dado, e precisa ser olhado.
"""

from __future__ import annotations

import unittest

from banco import ANOS, ANOS_COMPLETOS, TesteComCarga

# Maior variação anual observada de 2007 a 2025: -27,8% (2014 -> 2015, BR-Brasil); no BAT,
# -22,6% (2017 -> 2018). Acima de 30%, algo mudou no registro ou na carga
# (docs/caracterizacao-da-carga.md, "Crescimento e sazonalidade").
VARIACAO_ANUAL_MAX = 0.30
# Acidentes com morto ou ferido grave variam menos: no máximo -13,3% (2014 -> 2015) e
# -11,2% na troca de sistema (2016 -> 2017).
VARIACAO_ANUAL_GRAVES_MAX = 0.15

# Percentual máximo de NULL por campo e sistema. Medido:
# - coordenadas: BAT 0,005% (33 pares fora do limite em 2017); o BR-Brasil não tem coordenada;
# - idade: BAT 9,9%, BR-Brasil 13,7% (0, negativa ou acima de 110 na fonte);
# - ano de fabricação: BAT 6,8%, BR-Brasil 6,2% (0, vazio ou (null) na fonte);
# - classificação: 0,002% nos dois ('NA' ou (null));
# - tipo de acidente: 0,006% no BAT (41 vazios), nenhum no BR-Brasil.
NULOS_MAX = {
    ("ocorrencia", "latitude", "bat"): 0.001,
    ("ocorrencia", "classificacao_acidente", "bat"): 0.001,
    ("ocorrencia", "classificacao_acidente", "br_brasil"): 0.001,
    ("ocorrencia", "id_tipo", "bat"): 0.001,
    ("ocorrencia", "id_tipo", "br_brasil"): 0.001,
    ("pessoa", "idade", "bat"): 0.12,
    ("pessoa", "idade", "br_brasil"): 0.16,
    ("veiculo", "ano_fabricacao", "bat"): 0.10,
    ("veiculo", "ano_fabricacao", "br_brasil"): 0.10,
}

# Coordenadas fora de uma caixa que contém o Brasil. Medido: 20 (0,003%), já apontadas
# em docs/modelagem-origem.md; a carga não corrige coordenada dentro do limite válido.
CAIXA_BRASIL = {"lat": (-34, 6), "lon": (-74, -28)}
FORA_DO_BRASIL_MAX = 0.001


class TestDistribuicao(TesteComCarga):

    def por_ano(self, filtro: str = "true") -> dict[int, int]:
        return dict(self.todos(f"SELECT ano, count(*) FROM ocorrencia_vigente WHERE {filtro} GROUP BY ano"))

    def assertVariacaoAnual(self, contagens: dict[int, int], limite: float):
        for ano in ANOS_COMPLETOS[1:]:
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
            """SELECT a.ano, m.mes FROM generate_series(2007, 2025) a(ano)
               CROSS JOIN generate_series(1, 12) m(mes)
               WHERE NOT EXISTS (SELECT 1 FROM ocorrencia_vigente o
                                 WHERE o.ano = a.ano AND extract(month FROM o.ocorrido_em) = m.mes)""")
        self.assertEqual(vazios, [])

    def test_nulos_abaixo_do_limiar(self):
        for (tabela, coluna, sistema), limite in NULOS_MAX.items():
            with self.subTest(campo=f"{tabela}.{coluna}", sistema=sistema):
                taxa = self.um(
                    f"""SELECT avg(({coluna} IS NULL)::int)::float FROM {tabela}_vigente
                        JOIN lote_vigente l USING (id_lote) WHERE l.sistema = %s""", (sistema,))
                self.assertLessEqual(taxa, limite, f"{taxa:.3%} de NULL")

    def test_campos_do_trecho_so_faltam_no_br_brasil(self):
        # br, uf e km montam o trecho da pergunta de gestão. Faltam (null) em 12 ocorrências
        # do BR-Brasil, e km é anulado em 19 com km negativo; no BAT, nunca.
        rows = dict(self.todos(
            """SELECT l.sistema, count(*) FROM ocorrencia_vigente o JOIN lote_vigente l USING (id_lote)
               WHERE br IS NULL OR uf IS NULL OR km IS NULL GROUP BY 1"""))
        self.assertEqual(rows.get("bat", 0), 0)
        self.assertLessEqual(rows.get("br_brasil", 0), 50)
        self.assertEqual(self.um("SELECT count(*) FROM ocorrencia_vigente WHERE municipio IS NULL"), 0)

    def test_coordenada_so_no_bat(self):
        rows = dict(self.todos(
            """SELECT l.sistema, avg((o.geom IS NOT NULL)::int)::float
               FROM ocorrencia_vigente o JOIN lote_vigente l USING (id_lote) GROUP BY 1"""))
        self.assertEqual(rows["br_brasil"], 0)
        self.assertGreater(rows["bat"], 0.999)

    def test_coordenadas_dentro_do_brasil(self):
        (lat_min, lat_max), (lon_min, lon_max) = CAIXA_BRASIL["lat"], CAIXA_BRASIL["lon"]
        caixa = f"ST_MakeEnvelope({lon_min}, {lat_min}, {lon_max}, {lat_max}, 4674)"
        taxa = self.um(
            f"""SELECT avg((NOT ST_Intersects(geom, {caixa}))::int)::float
                FROM ocorrencia_vigente WHERE geom IS NOT NULL""")
        self.assertLessEqual(taxa, FORA_DO_BRASIL_MAX, f"{taxa:.3%} fora do Brasil")

    def test_data_dentro_do_ano_do_arquivo(self):
        n = self.um("SELECT count(*) FROM ocorrencia_vigente o JOIN lote_vigente l USING (id_lote) "
                    "WHERE o.ano <> l.ano")
        self.assertEqual(n, 0)

    def test_mortos_nao_passam_de_pessoas(self):
        self.assertEqual(self.um("SELECT count(*) FROM ocorrencia_vigente WHERE mortos > pessoas"), 0)

    def contagens_que_nao_batem(self) -> dict[str, tuple[int, int]]:
        """Por sistema: ocorrências cujos mortos e feridos graves diferem das pessoas."""
        rows = self.todos(
            """SELECT l.sistema,
                      count(*) FILTER (WHERE o.mortos <> coalesce(p.mortos, 0)),
                      count(*) FILTER (WHERE o.feridos_graves <> coalesce(p.graves, 0))
               FROM ocorrencia_vigente o JOIN lote_vigente l USING (id_lote)
               LEFT JOIN (SELECT id_lote, id,
                                 count(*) FILTER (WHERE estado_fisico IN ('Óbito', 'Morto')) AS mortos,
                                 count(*) FILTER (WHERE estado_fisico IN ('Lesões Graves', 'Ferido Grave')) AS graves
                          FROM pessoa_vigente GROUP BY id_lote, id) p USING (id_lote, id)
               GROUP BY 1""")
        return {sistema: (m, g) for sistema, m, g in rows}

    def test_mortos_e_graves_batem_com_as_pessoas_no_bat(self):
        # Consistência entre os dois arquivos da PRF: 100% no BAT.
        self.assertEqual(self.contagens_que_nao_batem()["bat"], (0, 0))

    def test_mortos_e_graves_batem_com_as_pessoas_no_br_brasil(self):
        # No BR-Brasil, só não batem as ocorrências que perderam pessoas para linha_rejeitada
        # (medido: 8 com mortos e 19 com feridos graves diferentes, em 1,56 milhão).
        mortos, graves = self.contagens_que_nao_batem()["br_brasil"]
        self.assertLessEqual(mortos, 50)
        self.assertLessEqual(graves, 50)

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
