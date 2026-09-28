"""Testes de dado faltante (issue #8): o que a carga faz com cada valor vazio ou inválido.

A regra de cada campo está no README, seção "Carga" (tabela "Na fonte / No banco"):

| Campo                                        | Valor na fonte                  | O que a carga faz |
|----------------------------------------------|---------------------------------|-------------------|
| classificacao_acidente, regional, delegacia, uop | vazio, NA, N/A              | NULL              |
| tipo_acidente                                | vazio                           | NULL              |
| idade                                        | vazio, NA, 0, negativa, > 110   | NULL              |
| ano_fabricacao_veiculo                       | vazio, NA, 0                    | NULL              |
| ano_fabricacao_veiculo                       | entre 1 e 1899                  | rejeita a linha   |
| latitude, longitude                          | vazia ou fora do limite válido  | as duas NULL      |
| id, pesid, id_veiculo                        | não inteiro (ex.: 4e+05)        | rejeita a linha   |
| km, uf, municipio, causa, data               | vazio ou inválido               | rejeita a linha   |
| pesid = 0                                    | —                               | só veículo        |
| id_veiculo = 0                               | —                               | pessoa sem veículo |

TestConversoes testa as funções da carga sem banco. TestDadoFaltanteNoBanco confere,
no banco carregado, que nenhum marcador de ausência da fonte sobrou gravado.
"""

from __future__ import annotations

import unittest

from banco import ANO, EXIGIR_BANCO, TesteComCarga

try:
    from blackspot import load
except ImportError:  # Python local sem psycopg/PyYAML
    if EXIGIR_BANCO:
        raise
    load = None


class DominioFalso:
    """Substitui o catálogo de causa/tipo, que precisa de banco."""

    def id(self, descricao: str) -> int:
        return 1


def linha_ocorrencia(**campos) -> dict:
    """Uma linha válida do datatranAAAA, como o csv.reader entrega (tudo texto)."""
    r = {
        "id": "123", "data_inversa": f"{ANO}-06-15", "horario": "14:30:00", "uf": "GO",
        "br": "60", "km": "12,5", "municipio": "ANAPOLIS", "latitude": "-16,3", "longitude": "-48,9",
        "causa_acidente": "Velocidade Incompatível", "tipo_acidente": "Colisão traseira",
        "classificacao_acidente": "Com Vítimas Feridas", "fase_dia": "Pleno dia",
        "sentido_via": "Crescente", "condicao_metereologica": "Céu Claro", "tipo_pista": "Dupla",
        "tracado_via": "Reta", "uso_solo": "Não", "pessoas": "2", "mortos": "0",
        "feridos_leves": "1", "feridos_graves": "1", "feridos": "2", "ilesos": "0",
        "ignorados": "0", "veiculos": "1", "regional": "SPRF-GO", "delegacia": "DEL01-GO",
        "uop": "UOP01-DEL01-GO",
    }
    r.update(campos)
    return r


@unittest.skipIf(load is None, "blackspot.load indisponível")
class TestConversoes(unittest.TestCase):

    def converter(self, **campos) -> dict:
        tupla = load.converter_ocorrencia(linha_ocorrencia(**campos), 1, ANO,
                                          DominioFalso(), DominioFalso(), load.Resumo())
        return dict(zip(load.OCORRENCIA_COLS, tupla))

    def test_marcadores_de_ausencia_viram_null(self):
        for valor in ("", "NA", "N/A", "  "):
            with self.subTest(valor=valor):
                self.assertIsNone(load.ausente(valor))
        self.assertEqual(load.ausente("SPRF-GO"), "SPRF-GO")

    def test_idade_desconhecida_vira_null(self):
        for valor in ("", "NA", "0", "-1", "111"):
            with self.subTest(valor=valor):
                self.assertIsNone(load.idade(valor))
        self.assertEqual(load.idade("40"), 40)
        self.assertEqual(load.idade("110"), 110)

    def test_idade_nao_numerica_rejeita(self):
        with self.assertRaises(load.Rejeitada):
            load.idade("quarenta")

    def test_ano_de_fabricacao(self):
        for valor in ("", "NA", "0"):
            with self.subTest(valor=valor):
                self.assertIsNone(load.ano_fabricacao(valor))
        self.assertEqual(load.ano_fabricacao("2015"), 2015)
        with self.assertRaises(load.Rejeitada):
            load.ano_fabricacao("1850")

    def test_coordenada_invalida_anula_o_par(self):
        for lat, lon in (("-91", "-48,9"), ("-16,3", "181"), ("", "-48,9"), ("NA", "NA"), ("x", "y")):
            with self.subTest(lat=lat, lon=lon):
                self.assertEqual(load.coordenadas(lat, lon), (None, None, True))
        self.assertEqual(load.coordenadas("-16,3", "-48,9"), ("-16.3", "-48.9", False))

    def test_ocorrencia_valida_converte(self):
        r = self.converter()
        self.assertEqual((r["id"], r["br"], r["km"], r["uso_solo_urbano"], r["tracado_via"]),
                         (123, 60, "12.5", False, ["Reta"]))

    def test_campos_opcionais_vazios_viram_null(self):
        r = self.converter(tipo_acidente="", classificacao_acidente="NA", regional="NA",
                           delegacia="N/A", uop="")
        for campo in ("id_tipo", "classificacao_acidente", "regional", "delegacia", "uop"):
            with self.subTest(campo=campo):
                self.assertIsNone(r[campo])

    def test_campos_obrigatorios_vazios_rejeitam(self):
        casos = {
            "id": "4e+05", "km": "", "uf": "", "municipio": "", "causa_acidente": "",
            "data_inversa": "", "fase_dia": "", "tracado_via": "", "uso_solo": "",
            "mortos": "NA",
        }
        for campo, valor in casos.items():
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(load.Rejeitada):
                    self.converter(**{campo: valor})

    def test_data_fora_do_ano_do_arquivo_rejeita(self):
        with self.assertRaises(load.Rejeitada):
            self.converter(data_inversa=f"{ANO - 1}-12-31")


class TestDadoFaltanteNoBanco(TesteComCarga):

    def test_nenhum_marcador_de_ausencia_gravado_como_texto(self):
        for coluna in ("regional", "delegacia", "uop", "municipio", "fase_dia", "sentido_via",
                       "condicao_meteorologica", "tipo_pista"):
            with self.subTest(coluna=coluna):
                n = self.um(f"SELECT count(*) FROM ocorrencia_vigente WHERE trim({coluna}) IN ('', 'NA', 'N/A')")
                self.assertEqual(n, 0)
        for tabela, coluna in (("pessoa_vigente", "sexo"), ("veiculo_vigente", "marca"),
                               ("veiculo_vigente", "tipo_veiculo")):
            with self.subTest(coluna=f"{tabela}.{coluna}"):
                n = self.um(f"SELECT count(*) FROM {tabela} WHERE trim({coluna}) IN ('', 'N/A')")
                self.assertEqual(n, 0)

    def test_idade_sentinela_nao_gravada(self):
        self.assertEqual(self.um("SELECT count(*) FROM pessoa_vigente WHERE idade <= 0 OR idade > 110"), 0)

    def test_ano_de_fabricacao_sentinela_nao_gravado(self):
        self.assertEqual(self.um("SELECT count(*) FROM veiculo_vigente WHERE ano_fabricacao = 0"), 0)

    def test_classificacao_na_vira_null(self):
        nulos = self.um("SELECT count(*) FROM ocorrencia_vigente WHERE classificacao_acidente IS NULL")
        if list(self.anos_iguais_ao_perfil()) == list(range(2017, 2026)):
            esperado = self.perfil()["ocorrencia"]["classificacao_acidente"].get("NA", 0)
            self.assertEqual(nulos, esperado)
        else:
            self.skipTest("algum ano foi republicado depois do perfil; contagem esperada desconhecida")

    def test_pessoa_sem_veiculo_so_para_quem_nao_esta_em_veiculo(self):
        n = self.um("""SELECT count(*) FROM pessoa_vigente
                       WHERE (id_veiculo IS NULL) <> (tipo_envolvido IN ('Pedestre', 'Testemunha', 'Cavaleiro'))""")
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
