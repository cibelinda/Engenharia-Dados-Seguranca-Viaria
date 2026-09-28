"""Testes de esquema (issue #8): as migrações chegam ao estado esperado e as
restrições barram dado inválido.

    docker compose run --rm tests          # contra o banco do compose
    python -m unittest discover tests      # sem banco, estes testes são pulados
"""

from __future__ import annotations

import unittest
from pathlib import Path

from banco import ANO, TesteComBanco, psycopg

if psycopg is not None:
    from psycopg import errors
    CHECK, NOT_NULL = errors.CheckViolation, errors.NotNullViolation
    FK, UNICO = errors.ForeignKeyViolation, errors.UniqueViolation
else:
    CHECK = NOT_NULL = FK = UNICO = Exception

MIGRACOES = Path(__file__).resolve().parent.parent / "db" / "migrations"

TABELAS = {"lote_carga", "lote_arquivo", "causa_acidente", "tipo_acidente",
           "ocorrencia", "veiculo", "pessoa", "linha_rejeitada"}
VIEWS = {"lote_vigente", "ocorrencia_vigente", "veiculo_vigente", "pessoa_vigente"}

# Colunas da chave primária de cada tabela, na ordem.
PKS = {
    "lote_carga": ["id_lote"],
    "lote_arquivo": ["id_lote", "dataset"],
    "causa_acidente": ["id_causa"],
    "tipo_acidente": ["id_tipo"],
    "ocorrencia": ["id_lote", "id"],
    "veiculo": ["id_lote", "id", "id_veiculo"],
    "pessoa": ["id_lote", "pesid"],
    "linha_rejeitada": ["id_rejeicao"],
}

# (tabela, colunas) -> (tabela referenciada, colunas). Toda linha de dado aponta
# para o seu lote, e pessoa aponta para ocorrência e para veículo.
FKS = {
    ("lote_arquivo", ("id_lote",)): ("lote_carga", ("id_lote",)),
    ("ocorrencia", ("id_lote", "ano")): ("lote_carga", ("id_lote", "ano")),
    ("ocorrencia", ("id_causa",)): ("causa_acidente", ("id_causa",)),
    ("ocorrencia", ("id_tipo",)): ("tipo_acidente", ("id_tipo",)),
    ("veiculo", ("id_lote", "id")): ("ocorrencia", ("id_lote", "id")),
    ("pessoa", ("id_lote", "id")): ("ocorrencia", ("id_lote", "id")),
    ("pessoa", ("id_lote", "id", "id_veiculo")): ("veiculo", ("id_lote", "id", "id_veiculo")),
    ("linha_rejeitada", ("id_lote", "dataset")): ("lote_arquivo", ("id_lote", "dataset")),
}


class TestMigracoes(TesteComBanco):
    """O banco chegou ao esquema esperado pelas migrações de db/migrations/."""

    def test_flyway_aplicou_todas_as_migracoes(self):
        if not self.um("SELECT to_regclass('flyway_schema_history') IS NOT NULL"):
            self.skipTest("banco sem flyway_schema_history (migrações aplicadas fora do Flyway)")
        if not MIGRACOES.is_dir():
            self.skipTest(f"{MIGRACOES} não encontrado")
        esperadas = sorted(p.name.split("__")[0].lstrip("V") for p in MIGRACOES.glob("V*__*.sql"))
        aplicadas = self.todos(
            "SELECT version, success FROM flyway_schema_history WHERE version IS NOT NULL ORDER BY installed_rank")
        self.assertEqual([v for v, _ in aplicadas], esperadas)
        self.assertTrue(all(ok for _, ok in aplicadas), "há migração com success = false")

    def test_tabelas_e_views_existem(self):
        tabelas = {r[0] for r in self.todos(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")}
        views = {r[0] for r in self.todos(
            "SELECT table_name FROM information_schema.views WHERE table_schema = 'public'")}
        self.assertLessEqual(TABELAS, tabelas)
        self.assertLessEqual(VIEWS, views)

    def test_chaves_primarias(self):
        for tabela, colunas in PKS.items():
            with self.subTest(tabela=tabela):
                pk = self.todos(
                    """
                    SELECT a.attname
                    FROM pg_constraint c
                    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ordem) ON true
                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                    WHERE c.conrelid = %s::regclass AND c.contype = 'p'
                    ORDER BY k.ordem
                    """, (tabela,))
                self.assertEqual([r[0] for r in pk], colunas)

    def test_chaves_estrangeiras(self):
        rows = self.todos(
            """
            SELECT c.conrelid::regclass::text, c.confrelid::regclass::text,
                   array(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n, o)
                         JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n ORDER BY k.o),
                   array(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(n, o)
                         JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n ORDER BY k.o)
            FROM pg_constraint c
            WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
            """)
        existentes = {(t, tuple(cols)): (ref, tuple(refcols)) for t, ref, cols, refcols in rows}
        for chave, alvo in FKS.items():
            with self.subTest(fk=chave):
                self.assertEqual(existentes.get(chave), alvo)

    def test_toda_tabela_e_view_declara_seu_carimbo_de_tempo(self):
        # O enunciado pede que cada tabela deixe claro que tempo guarda; o esquema
        # faz isso no COMMENT ON TABLE/VIEW.
        for nome in sorted(TABELAS | VIEWS):
            with self.subTest(objeto=nome):
                comentario = self.um("SELECT obj_description(%s::regclass, 'pg_class')", (nome,))
                self.assertTrue(comentario, f"{nome} sem COMMENT")
                self.assertRegex(comentario.lower(), r"carimbo|hora")


class TestRestricoes(TesteComBanco):
    """Cada restrição do esquema barra o dado inválido que ela promete barrar."""

    def setUp(self):
        self.id_lote = self.lote()

    def test_linhas_validas_entram(self):
        # Garante que as falhas abaixo vêm do campo alterado, e não do exemplo.
        self.acidente(self.id_lote)
        self.inserir("pessoa", self.linha_pessoa(
            self.id_lote, pesid=101, id_veiculo=None, tipo_envolvido="Pedestre"))
        self.assertEqual(self.um("SELECT count(*) FROM pessoa WHERE id_lote = %s", (self.id_lote,)), 2)

    # --- lote ----------------------------------------------------------------------

    def test_lote_fora_do_recorte(self):
        self.assertFalha(CHECK, "INSERT INTO lote_carga (ano) VALUES (2016)")

    def test_lote_concluido_sem_fim(self):
        self.assertFalha(CHECK, "INSERT INTO lote_carga (ano, status) VALUES (%s, 'concluido')", (ANO,))

    def test_status_de_lote_invalido(self):
        self.assertFalha(CHECK, "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (%s, 'ok', now())", (ANO,))

    def test_duas_cargas_simultaneas_do_mesmo_ano(self):
        # Um teste anterior interrompido não deixa lote em_carga: tudo é desfeito no rollback.
        if self.um("SELECT count(*) FROM lote_carga WHERE ano = %s AND status = 'em_carga'", (ANO,)):
            self.skipTest(f"há uma carga de {ANO} em andamento no banco")
        self.lote(status="em_carga")
        self.assertFalha(UNICO, "INSERT INTO lote_carga (ano) VALUES (%s)", (ANO,))

    def test_arquivo_com_mais_rejeitadas_que_lidas(self):
        self.assertFalha(
            CHECK,
            """INSERT INTO lote_arquivo (id_lote, dataset, chave_manifesto, arquivo, sha256,
                                         tamanho_bytes, linhas_lidas, linhas_rejeitadas)
               VALUES (%s, 'ocorrencia', 'bat_2025_ocorrencia', 'datatran2025.zip', %s, 1, 10, 11)""",
            (self.id_lote, "a" * 64))

    def test_sha256_invalido(self):
        self.assertFalha(
            CHECK,
            """INSERT INTO lote_arquivo (id_lote, dataset, chave_manifesto, arquivo, sha256, tamanho_bytes)
               VALUES (%s, 'ocorrencia', 'bat_2025_ocorrencia', 'datatran2025.zip', %s, 1)""",
            (self.id_lote, "Z" * 64))

    # --- ocorrência ----------------------------------------------------------------

    def test_ocorrencia_de_outro_ano_que_o_lote(self):
        self.assertInsertFalha(FK, "ocorrencia", self.linha_ocorrencia(
            self.id_lote, ocorrido_em=f"{ANO - 1}-06-15 14:30:00"))

    def test_ocorrencia_sem_municipio(self):
        self.assertInsertFalha(NOT_NULL, "ocorrencia", self.linha_ocorrencia(self.id_lote, municipio=None))

    def test_ocorrencia_sem_data(self):
        self.assertInsertFalha(NOT_NULL, "ocorrencia", self.linha_ocorrencia(self.id_lote, ocorrido_em=None))

    def test_uf_invalida(self):
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, uf="XX"))

    def test_km_negativo(self):
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, km=-1))

    def test_id_nao_positivo(self):
        # IDs em notação científica (ex.: '4e+05') não viram número válido e vão para os rejeitados.
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, id=0))

    def test_latitude_sem_longitude(self):
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, longitude=None))

    def test_latitude_fora_do_limite(self):
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, latitude=-91))

    def test_feridos_diferente_da_soma(self):
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, feridos=3))

    def test_contagem_negativa(self):
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(self.id_lote, mortos=-1))

    def test_classificacao_invalida(self):
        # 'NA' aparece em 10 ocorrências do recorte; a carga deve gravar NULL.
        self.assertInsertFalha(CHECK, "ocorrencia", self.linha_ocorrencia(
            self.id_lote, classificacao_acidente="NA"))

    def test_causa_inexistente(self):
        self.assertInsertFalha(FK, "ocorrencia", self.linha_ocorrencia(self.id_lote, id_causa=-1))

    def test_ocorrencia_repetida_no_mesmo_lote(self):
        self.inserir("ocorrencia", self.linha_ocorrencia(self.id_lote))
        self.assertInsertFalha(UNICO, "ocorrencia", self.linha_ocorrencia(self.id_lote))

    # --- veículo e pessoa ----------------------------------------------------------

    def test_veiculo_sem_ocorrencia(self):
        self.assertInsertFalha(FK, "veiculo", self.linha_veiculo(self.id_lote, id=999))

    def test_mesmo_veiculo_em_duas_ocorrencias_do_lote(self):
        self.acidente(self.id_lote, id=1, id_veiculo=10, pesid=100)
        self.inserir("ocorrencia", self.linha_ocorrencia(self.id_lote, id=2))
        self.assertInsertFalha(UNICO, "veiculo", self.linha_veiculo(self.id_lote, id=2, id_veiculo=10))

    def test_pessoa_sem_ocorrencia(self):
        self.assertInsertFalha(FK, "pessoa", self.linha_pessoa(
            self.id_lote, id=999, id_veiculo=None, tipo_envolvido="Pedestre"))

    def test_pessoa_em_veiculo_de_outra_ocorrencia(self):
        self.acidente(self.id_lote, id=1, id_veiculo=10, pesid=100)
        self.inserir("ocorrencia", self.linha_ocorrencia(self.id_lote, id=2))
        self.assertInsertFalha(FK, "pessoa", self.linha_pessoa(self.id_lote, pesid=101, id=2, id_veiculo=10))

    def test_pesid_zero_nao_e_pessoa(self):
        # No arquivo da PRF, pesid = 0 marca veículo sem pessoa (144.628 linhas no recorte).
        self.acidente(self.id_lote)
        self.assertInsertFalha(CHECK, "pessoa", self.linha_pessoa(self.id_lote, pesid=0))

    def test_condutor_sem_veiculo(self):
        self.inserir("ocorrencia", self.linha_ocorrencia(self.id_lote))
        self.assertInsertFalha(CHECK, "pessoa", self.linha_pessoa(self.id_lote, id_veiculo=None))

    def test_pedestre_com_veiculo(self):
        self.acidente(self.id_lote)
        self.assertInsertFalha(CHECK, "pessoa", self.linha_pessoa(
            self.id_lote, pesid=101, tipo_envolvido="Pedestre"))

    def test_estado_fisico_invalido(self):
        self.acidente(self.id_lote)
        self.assertInsertFalha(CHECK, "pessoa", self.linha_pessoa(self.id_lote, pesid=101, estado_fisico="NA"))

    def test_pessoa_repetida_no_mesmo_lote(self):
        self.acidente(self.id_lote)
        self.assertInsertFalha(UNICO, "pessoa", self.linha_pessoa(self.id_lote))

    # --- linha rejeitada -----------------------------------------------------------

    def test_rejeitada_sem_arquivo_do_lote(self):
        self.assertFalha(
            FK,
            """INSERT INTO linha_rejeitada (id_lote, dataset, numero_linha, linha_bruta, motivo)
               VALUES (%s, 'pessoa', 1, 'x', 'teste')""",
            (self.id_lote,))

    def test_rejeitada_sem_motivo(self):
        self.conn.execute(
            """INSERT INTO lote_arquivo (id_lote, dataset, chave_manifesto, arquivo, sha256, tamanho_bytes)
               VALUES (%s, 'pessoa', 'bat_2025_pessoa', 'acidentes2025.zip', %s, 1)""",
            (self.id_lote, "a" * 64))
        self.assertFalha(
            CHECK,
            """INSERT INTO linha_rejeitada (id_lote, dataset, numero_linha, linha_bruta, motivo)
               VALUES (%s, 'pessoa', 1, 'x', '')""",
            (self.id_lote,))


if __name__ == "__main__":
    unittest.main()
