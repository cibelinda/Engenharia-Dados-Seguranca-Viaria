"""Apoio aos testes de dados (issue #8): conexão e linhas válidas de exemplo.

A conexão vem das variáveis padrão do PostgreSQL (PGHOST, PGPORT, PGDATABASE,
PGUSER, PGPASSWORD), como em blackspot/load.py.

Sem banco acessível, os testes de dados são pulados, para que
`python -m unittest discover tests` continue rodando sem Docker. No serviço
`tests` do docker-compose.yml, BLACKSPOT_EXIGIR_BANCO=1 transforma a falta de
banco em erro, para que um teste nunca passe por ter sido pulado.

Cada teste roda dentro de uma transação desfeita no fim (rollback). Por isso os
testes podem rodar tanto no banco vazio quanto no banco já carregado, sem deixar
nada gravado.
"""

from __future__ import annotations

import json
import os
import unittest
import uuid
from pathlib import Path

try:
    import psycopg
except ImportError:  # Python local sem as dependências do projeto
    psycopg = None

EXIGIR_BANCO = os.environ.get("BLACKSPOT_EXIGIR_BANCO") == "1"

ANOS = range(2017, 2026)  # recorte do projeto (docs/pergunta-e-recorte.md)

# Números medidos direto nos ZIPs por bench/perfil_recorte.py. Servem de valor esperado
# para a carga, mas só para os anos cujo arquivo carregado é o mesmo que foi perfilado
# (mesmo SHA-256): se a PRF republicar um ano, os números dele mudam de propósito.
PERFIL = Path(__file__).resolve().parent.parent / "bench" / "resultados" / "perfil_recorte.json"

# Ano usado nas linhas de exemplo. Os lotes criados pelos testes são sempre os
# mais novos do ano (id_lote é IDENTITY), então viram a versão vigente dele.
ANO = 2025


def conectar():
    """Abre uma conexão sem autocommit, ou pula o teste se não houver banco."""
    if psycopg is None:
        if EXIGIR_BANCO:
            raise RuntimeError("psycopg não está instalado")
        raise unittest.SkipTest("psycopg não instalado; testes de dados pulados")
    try:
        return psycopg.connect(connect_timeout=3)
    except psycopg.OperationalError as e:
        if EXIGIR_BANCO:
            raise
        raise unittest.SkipTest(f"sem banco acessível ({e.__class__.__name__}); testes de dados pulados")


class TesteComBanco(unittest.TestCase):
    """Uma conexão por classe e uma transação desfeita por teste."""

    @classmethod
    def setUpClass(cls):
        cls.conn = conectar()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def um(self, sql: str, params=()):
        """Primeira coluna da primeira linha."""
        row = self.conn.execute(sql, params).fetchone()
        return row[0] if row else None

    def todos(self, sql: str, params=()) -> list[tuple]:
        return self.conn.execute(sql, params).fetchall()

    def assertFalha(self, erro, sql: str, params=()):
        """Confere que o comando falha com `erro`, sem abortar a transação do teste."""
        with self.assertRaises(erro):
            with self.conn.transaction():  # savepoint: a falha desfaz só este comando
                self.conn.execute(sql, params)

    # --- linhas válidas de exemplo -------------------------------------------------

    def lote(self, ano: int = ANO, status: str = "concluido") -> int:
        fim = "NULL" if status == "em_carga" else "now()"
        return self.um(
            f"INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (%s, %s, {fim}) RETURNING id_lote",
            (ano, status),
        )

    def causa(self) -> int:
        return self.um(
            "INSERT INTO causa_acidente (descricao) VALUES (%s) RETURNING id_causa",
            (f"teste {uuid.uuid4()}",),
        )

    def linha_ocorrencia(self, id_lote: int, id: int = 1, **campos) -> dict:
        linha = {
            "id_lote": id_lote, "id": id, "ocorrido_em": f"{ANO}-06-15 14:30:00",
            "uf": "GO", "br": 60, "km": 12.5, "municipio": "ANAPOLIS",
            "latitude": -16.3, "longitude": -48.9, "id_causa": self.causa(),
            "classificacao_acidente": "Com Vítimas Feridas",
            "fase_dia": "Pleno dia", "sentido_via": "Crescente",
            "condicao_meteorologica": "Céu Claro", "tipo_pista": "Dupla",
            "tracado_via": ["Reta"], "uso_solo_urbano": False,
            "pessoas": 2, "mortos": 0, "feridos_leves": 1, "feridos_graves": 1,
            "feridos": 2, "ilesos": 0, "ignorados": 0, "veiculos": 1,
        }
        return {**linha, **campos}

    def linha_veiculo(self, id_lote: int, id: int = 1, id_veiculo: int = 10, **campos) -> dict:
        linha = {"id_lote": id_lote, "id": id, "id_veiculo": id_veiculo,
                 "tipo_veiculo": "Automóvel", "marca": "TESTE", "ano_fabricacao": 2015}
        return {**linha, **campos}

    def linha_pessoa(self, id_lote: int, pesid: int = 100, id: int = 1,
                     id_veiculo: int | None = 10, **campos) -> dict:
        linha = {"id_lote": id_lote, "pesid": pesid, "id": id, "id_veiculo": id_veiculo,
                 "tipo_envolvido": "Condutor", "estado_fisico": "Lesões Graves",
                 "idade": 40, "sexo": "Masculino"}
        return {**linha, **campos}

    def acidente(self, id_lote: int, id: int = 1, id_veiculo: int = 10, pesid: int = 100) -> None:
        """Uma ocorrência válida com um veículo e o condutor."""
        self.inserir("ocorrencia", self.linha_ocorrencia(id_lote, id))
        self.inserir("veiculo", self.linha_veiculo(id_lote, id, id_veiculo))
        self.inserir("pessoa", self.linha_pessoa(id_lote, pesid, id, id_veiculo))

    @staticmethod
    def _insert(tabela: str, linha: dict) -> tuple[str, list]:
        colunas = ", ".join(linha)
        valores = ", ".join(["%s"] * len(linha))
        return f"INSERT INTO {tabela} ({colunas}) VALUES ({valores})", list(linha.values())

    def inserir(self, tabela: str, linha: dict) -> None:
        self.conn.execute(*self._insert(tabela, linha))

    def assertInsertFalha(self, erro, tabela: str, linha: dict):
        self.assertFalha(erro, *self._insert(tabela, linha))


class TesteComCarga(TesteComBanco):
    """Testes que leem o banco já carregado (issue #4). Não gravam nada.

    Sem nenhum lote concluído, os testes são pulados, ou falham com
    BLACKSPOT_EXIGIR_BANCO=1, porque no compose o serviço `tests` roda depois do `load`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        anos = {r[0] for r in cls.conn.execute("SELECT ano FROM lote_vigente").fetchall()}
        cls.conn.rollback()
        if set(ANOS) - anos:
            faltam = sorted(set(ANOS) - anos)
            if EXIGIR_BANCO:
                raise AssertionError(f"anos sem lote concluído: {faltam}; a carga rodou?")
            cls.conn.close()
            raise unittest.SkipTest(f"banco sem carga para {faltam}; rode `docker compose up` antes")

    @classmethod
    def perfil(cls) -> dict:
        if not PERFIL.exists():
            raise unittest.SkipTest(f"{PERFIL.name} não encontrado")
        return json.loads(PERFIL.read_text(encoding="utf-8"))

    def anos_iguais_ao_perfil(self) -> list[int]:
        """Anos cujos dois arquivos vigentes têm o mesmo SHA-256 dos arquivos perfilados."""
        sha = self.perfil()["arquivos_sha256"]
        carregado = self.todos(
            """SELECT l.ano, a.arquivo, a.sha256 FROM lote_vigente l
               JOIN lote_arquivo a USING (id_lote)""")
        diferentes = {ano for ano, arquivo, h in carregado if sha.get(arquivo) != h}
        anos = [a for a in ANOS if a not in diferentes]
        if not anos:
            self.skipTest("nenhum ano carregado é igual ao perfilado (a PRF republicou tudo?)")
        return anos
