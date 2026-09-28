"""Testes do histórico insert-only (issue #8): as views *_vigente mostram só o
lote vigente de cada ano, e as versões antigas continuam nas tabelas.

É o comportamento que o ADR 0001 e docs/modelagem-origem.md prometem para uma
republicação da PRF: um SHA-256 novo gera um lote novo, e nada é sobrescrito.
"""

from __future__ import annotations

import unittest

from banco import ANO, TesteComBanco


class TestVersaoVigente(TesteComBanco):

    def contar(self, tabela: str, lotes: list[int]) -> dict[int, int]:
        rows = self.todos(
            f"SELECT id_lote, count(*) FROM {tabela} WHERE id_lote = ANY(%s) GROUP BY id_lote", (lotes,))
        return dict(rows)

    def test_republicacao_troca_a_versao_vigente_sem_apagar_a_antiga(self):
        antigo = self.lote()
        self.acidente(antigo)
        novo = self.lote()  # a PRF republicou o ano: mesma ocorrência, novo lote
        self.acidente(novo)

        self.assertEqual(self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ANO,)), novo)
        for tabela in ("ocorrencia", "veiculo", "pessoa"):
            with self.subTest(tabela=tabela):
                self.assertEqual(self.contar(f"{tabela}_vigente", [antigo, novo]), {novo: 1})
                self.assertEqual(self.contar(tabela, [antigo, novo]), {antigo: 1, novo: 1})

    def test_lote_em_carga_nao_e_vigente(self):
        concluido = self.lote()
        self.acidente(concluido)
        em_carga = self.lote(status="em_carga")
        self.acidente(em_carga)

        self.assertEqual(self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ANO,)), concluido)
        self.assertEqual(self.contar("ocorrencia_vigente", [concluido, em_carga]), {concluido: 1})

    def test_lote_que_falhou_nao_e_vigente(self):
        concluido = self.lote()
        self.acidente(concluido)
        falhou = self.lote(status="falhou")
        self.acidente(falhou)

        self.assertEqual(self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ANO,)), concluido)
        self.assertEqual(self.contar("ocorrencia_vigente", [concluido, falhou]), {concluido: 1})

    def test_um_lote_vigente_por_ano(self):
        self.lote(ano=ANO)
        self.lote(ano=ANO - 1)
        repetidos = self.todos("SELECT ano FROM lote_vigente GROUP BY ano HAVING count(*) > 1")
        self.assertEqual(repetidos, [])

    def test_versao_vigente_de_um_ano_nao_afeta_outro(self):
        de_um_ano = self.lote(ano=ANO - 1)
        self.lote(ano=ANO)
        self.assertEqual(self.um("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ANO - 1,)), de_um_ano)


if __name__ == "__main__":
    unittest.main()
