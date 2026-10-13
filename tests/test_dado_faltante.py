"""Testes de dado faltante (issue #8): o que a carga faz com cada valor vazio ou inválido.

A regra de cada campo está no README, seção "Carga" (tabela "Na fonte / No banco"):

"Ausente" é vazio, NA, N/A ou (null) (o marcador do BR-Brasil).

| Campo                                        | Valor na fonte                  | O que a carga faz |
|----------------------------------------------|---------------------------------|-------------------|
| uf, br, km, causa, tipo, classificação, fase do dia, sentido, condição, pista, traçado, uso do solo, regional, delegacia, uop | ausente | NULL |
| km                                           | negativo (BR-Brasil)            | NULL              |
| idade                                        | ausente, 0, negativa, > 110     | NULL              |
| ano_fabricacao_veiculo                       | ausente, 0, > ano do arquivo + 1 | NULL             |
| ano_fabricacao_veiculo                       | entre 1 e 1899                  | rejeita a linha   |
| latitude, longitude                          | ausente ou fora do limite válido | as duas NULL     |
| latitude, longitude                          | coluna não existe (BR-Brasil)   | as duas NULL      |
| id, pesid, id_veiculo                        | não inteiro (ex.: 4e+05)        | rejeita a linha   |
| id_veiculo                                   | 0 (BAT), (null) ou NA (BR-Brasil) | pessoa sem veículo |
| uf, km, data, uso do solo, classificação     | valor inválido                  | rejeita a linha   |
| municipio                                    | vazio                           | rejeita a linha   |
| pesid = 0                                    | —                               | só veículo        |

TestConversoes testa as funções da carga sem banco. TestDadoFaltanteNoBanco confere,
no banco carregado, que nenhum marcador de ausência da fonte sobrou gravado.
"""

from __future__ import annotations

import unittest

from banco import ANO, ANOS, EXIGIR_BANCO, TesteComCarga

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
        for valor in ("", "NA", "N/A", "  ", "(null)"):
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
                self.assertIsNone(load.ano_fabricacao(valor, 2020))
        self.assertEqual(load.ano_fabricacao("2015", 2020), 2015)
        self.assertEqual(load.ano_fabricacao("2021", 2020), 2021)  # modelo do ano seguinte
        for valor in ("2022", "9999", "2222"):  # sentinelas e erros do BR-Brasil
            with self.subTest(valor=valor):
                self.assertIsNone(load.ano_fabricacao(valor, 2020))
        with self.assertRaises(load.Rejeitada):
            load.ano_fabricacao("1850", 2020)

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
                           delegacia="N/A", uop="", uf="(null)", br="(null)", km="(null)",
                           causa_acidente="(null)", fase_dia="(null)", condicao_metereologica="",
                           tipo_pista="(null)", tracado_via="(null)", uso_solo="(null)")
        for campo in ("id_tipo", "classificacao_acidente", "regional", "delegacia", "uop", "uf", "br",
                      "km", "id_causa", "fase_dia", "condicao_meteorologica", "tipo_pista",
                      "tracado_via", "uso_solo_urbano"):
            with self.subTest(campo=campo):
                self.assertIsNone(r[campo])

    def test_campos_invalidos_rejeitam(self):
        casos = {
            "id": "4e+05", "km": "abc", "uf": "XX", "municipio": "", "data_inversa": "",
            "uso_solo": "Talvez", "classificacao_acidente": "Grave", "mortos": "NA",
        }
        for campo, valor in casos.items():
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(load.Rejeitada):
                    self.converter(**{campo: valor})

    def test_data_fora_do_ano_do_arquivo_rejeita(self):
        with self.assertRaises(load.Rejeitada):
            self.converter(data_inversa=f"{ANO - 1}-12-31")


@unittest.skipIf(load is None, "blackspot.load indisponível")
class TestConversoesBrBrasil(unittest.TestCase):
    """Os formatos do BR-Brasil (2007–2016), medidos nos arquivos (docs/fontes/README.md)."""

    def converter(self, ano: int, **campos) -> dict:
        r = linha_ocorrencia(**campos)
        for c in ("latitude", "longitude", "regional", "delegacia", "uop"):  # não existem no BR-Brasil
            r.pop(c)
        tupla = load.converter_ocorrencia(r, 1, ano, DominioFalso(), DominioFalso(), load.Resumo())
        return dict(zip(load.OCORRENCIA_COLS, tupla))

    def test_tres_formatos_de_data(self):
        for ano, data in ((2010, "15/06/2010"), (2013, "2013-06-15"), (2016, "15/06/16")):
            with self.subTest(data=data):
                self.assertEqual(str(self.converter(ano, data_inversa=data)["ocorrido_em"]),
                                 f"{ano}-06-15 14:30:00")

    def test_sem_colunas_de_coordenada_e_unidade_da_prf(self):
        r = self.converter(2010, data_inversa="15/06/2010")
        for campo in ("latitude", "longitude", "regional", "delegacia", "uop"):
            with self.subTest(campo=campo):
                self.assertIsNone(r[campo])

    def test_km_com_ponto_e_km_negativo(self):
        self.assertEqual(self.converter(2010, data_inversa="15/06/2010", km="87.1")["km"], "87.1")
        resumo = load.Resumo()
        r = linha_ocorrencia(data_inversa="15/06/2010", km="-687.4")
        tupla = load.converter_ocorrencia(r, 1, 2010, DominioFalso(), DominioFalso(), resumo)
        self.assertIsNone(dict(zip(load.OCORRENCIA_COLS, tupla))["km"])
        self.assertEqual(resumo.km_nulos, 1)

    def test_uso_solo_urbano_rural(self):
        for valor, urbano in (("Urbano", True), ("Rural", False), ("Sim", True), ("Não", False)):
            with self.subTest(valor=valor):
                self.assertEqual(self.converter(2010, data_inversa="15/06/2010", uso_solo=valor)
                                 ["uso_solo_urbano"], urbano)

    def test_id_veiculo_ausente_e_sem_veiculo(self):
        for valor in ("0", "(null)", "NA", ""):
            with self.subTest(valor=valor):
                self.assertEqual(load.id_veiculo(valor), 0)
        self.assertEqual(load.id_veiculo("123"), 123)
        with self.assertRaises(load.Rejeitada):
            load.id_veiculo("1e+05")


class TestDadoFaltanteNoBanco(TesteComCarga):

    def test_nenhum_marcador_de_ausencia_gravado_como_texto(self):
        marcadores = "('', 'NA', 'N/A', '(null)')"
        for coluna in ("regional", "delegacia", "uop", "municipio", "fase_dia", "sentido_via",
                       "condicao_meteorologica", "tipo_pista", "classificacao_acidente"):
            with self.subTest(coluna=coluna):
                n = self.um(f"SELECT count(*) FROM ocorrencia_vigente WHERE trim({coluna}) IN {marcadores}")
                self.assertEqual(n, 0)
        for tabela, coluna in (("pessoa_vigente", "sexo"), ("pessoa_vigente", "estado_fisico"),
                               ("pessoa_vigente", "nacionalidade"), ("veiculo_vigente", "marca"),
                               ("veiculo_vigente", "tipo_veiculo")):
            with self.subTest(coluna=f"{tabela}.{coluna}"):
                n = self.um(f"SELECT count(*) FROM {tabela} WHERE trim({coluna}) IN {marcadores}")
                self.assertEqual(n, 0)

    def test_texto_sem_espacos_de_preenchimento(self):
        # O BR-Brasil completa estado_fisico e marca com espaços ('Ileso       ').
        for tabela, coluna in (("pessoa_vigente", "estado_fisico"), ("veiculo_vigente", "marca")):
            with self.subTest(coluna=f"{tabela}.{coluna}"):
                self.assertEqual(self.um(f"SELECT count(*) FROM {tabela} WHERE {coluna} <> trim({coluna})"), 0)

    def test_idade_sentinela_nao_gravada(self):
        self.assertEqual(self.um("SELECT count(*) FROM pessoa_vigente WHERE idade <= 0 OR idade > 110"), 0)

    def test_ano_de_fabricacao_sentinela_nao_gravado(self):
        self.assertEqual(self.um("SELECT count(*) FROM veiculo_vigente WHERE ano_fabricacao = 0"), 0)

    def test_classificacao_ausente_vira_null(self):
        # O perfil conta todas as linhas do arquivo; algumas das que vêm sem classificação
        # podem estar entre as ocorrências rejeitadas (ex.: id repetido no BR-Brasil).
        nulos = self.um("SELECT count(*) FROM ocorrencia_vigente WHERE classificacao_acidente IS NULL")
        if list(self.anos_iguais_ao_perfil()) == list(ANOS):
            contagem = self.perfil()["ocorrencia"]["classificacao_acidente"]
            esperado = sum(contagem.get(v, 0) for v in ("", "NA", "N/A", "(null)"))
            rejeitadas = self.um("""SELECT count(*) FROM linha_rejeitada JOIN lote_vigente USING (id_lote)
                                    WHERE dataset = 'ocorrencia'""")
            self.assertLessEqual(nulos, esperado)
            self.assertGreaterEqual(nulos, esperado - rejeitadas)
        else:
            self.skipTest("algum ano foi republicado depois do perfil; contagem esperada desconhecida")

    def test_pessoa_sem_veiculo_so_para_quem_nao_esta_em_veiculo_no_bat(self):
        # Regra do BAT, verificada na carga. No BR-Brasil ela não vale (V0010).
        n = self.um("""SELECT count(*) FROM pessoa_vigente p JOIN lote_vigente l USING (id_lote)
                       WHERE l.sistema = 'bat'
                         AND (id_veiculo IS NULL) <> (tipo_envolvido IN ('Pedestre', 'Testemunha', 'Cavaleiro'))""")
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
