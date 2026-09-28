"""Medição do ADR 0001: alternativa A (opção nula) × alternativa C (insert-only por lote).

Roda contra o banco já carregado (esquema da #3, carga da #4), que é a alternativa C:

    docker compose up --build -d && docker compose wait load
    docker compose run --rm -v ./bench:/app/bench tests python bench/medicao_adr.py

O que faz:
1. Monta a alternativa A no schema `alt_a`: uma tabela por arquivo da PRF, planas, sem FK e
   sem índice, com os dados da versão vigente (datatran = ocorrência; acidentes = pessoa com
   os dados do acidente e do veículo repetidos em cada linha, como no CSV).
2. Roda a Q1 e a Q2 da pergunta de gestão (docs/caracterizacao-da-carga.md) em A e em C,
   com EXPLAIN (ANALYZE, BUFFERS), N vezes cada, e guarda a mediana.
3. Mede o tamanho em disco de A e de C (pg_total_relation_size, com índices).
4. Simula uma republicação de 2024 em C (um lote novo com as mesmas linhas), mede quanto o
   banco cresce e quanto as consultas mudam, e desfaz tudo (rollback).

Grava o resultado em bench/resultados/medicao_adr.json. O schema `alt_a` é apagado no fim.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

OUT = Path(__file__).resolve().parent / "resultados" / "medicao_adr.json"
RODADAS = 5
ANO_REGRAVADO = 2024

TABELAS_C = ["lote_carga", "lote_arquivo", "causa_acidente", "tipo_acidente",
             "ocorrencia", "veiculo", "pessoa", "linha_rejeitada"]
TABELAS_A = ["alt_a.datatran", "alt_a.acidentes"]

Q1 = """
SELECT br, uf, floor(km / 10) * 10 AS km_inicio, ano,
       count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
FROM {fonte}
WHERE br <> 0
GROUP BY br, uf, km_inicio, ano
"""

Q2 = """
WITH por_trecho AS (
    SELECT br, uf, floor(km / 10) * 10 AS km_inicio, ano,
           count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
    FROM {fonte}
    WHERE br <> 0
    GROUP BY br, uf, km_inicio, ano
), ranqueado AS (
    SELECT *, rank() OVER (PARTITION BY ano ORDER BY graves DESC) AS posicao
    FROM por_trecho
)
SELECT br, uf, km_inicio, count(*) AS anos_entre_os_50, sum(graves) AS graves_total
FROM ranqueado
WHERE posicao <= 50
GROUP BY br, uf, km_inicio
ORDER BY anos_entre_os_50 DESC, graves_total DESC
"""

FONTES = {"A": "alt_a.datatran", "C": "ocorrencia_vigente"}

MONTA_A = """
DROP SCHEMA IF EXISTS alt_a CASCADE;
CREATE SCHEMA alt_a;

-- datatranAAAA: uma linha por ocorrência, causa e tipo como texto.
CREATE TABLE alt_a.datatran AS
SELECT o.id, o.ocorrido_em, o.ano, o.uf, o.br, o.km, o.municipio, o.latitude, o.longitude,
       c.descricao AS causa_acidente, t.descricao AS tipo_acidente, o.classificacao_acidente,
       o.fase_dia, o.sentido_via, o.condicao_meteorologica, o.tipo_pista, o.tracado_via,
       o.uso_solo_urbano, o.pessoas, o.mortos, o.feridos_leves, o.feridos_graves, o.feridos,
       o.ilesos, o.ignorados, o.veiculos, o.regional, o.delegacia, o.uop
FROM ocorrencia_vigente o
JOIN causa_acidente c USING (id_causa)
LEFT JOIN tipo_acidente t USING (id_tipo);

-- acidentesAAAA: uma linha por pessoa (ou por veículo sem pessoa), repetindo o acidente e o
-- veículo, como no CSV da PRF.
CREATE TABLE alt_a.acidentes AS
SELECT d.*, p.pesid, v.id_veiculo, v.tipo_veiculo, v.marca, v.ano_fabricacao,
       p.tipo_envolvido, p.estado_fisico, p.idade, p.sexo
FROM pessoa_vigente p
JOIN alt_a.datatran d ON d.id = p.id
LEFT JOIN veiculo_vigente v ON v.id_lote = p.id_lote AND v.id = p.id AND v.id_veiculo = p.id_veiculo
UNION ALL
SELECT d.*, 0, v.id_veiculo, v.tipo_veiculo, v.marca, v.ano_fabricacao,
       NULL, NULL, NULL, NULL
FROM veiculo_vigente v
JOIN alt_a.datatran d ON d.id = v.id
WHERE NOT EXISTS (SELECT 1 FROM pessoa_vigente p
                  WHERE p.id_lote = v.id_lote AND p.id = v.id AND p.id_veiculo = v.id_veiculo);

ANALYZE alt_a.datatran;
ANALYZE alt_a.acidentes;
"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def tamanho(conn, tabelas: list[str]) -> int:
    return sum(conn.execute("SELECT pg_total_relation_size(%s)", (t,)).fetchone()[0] for t in tabelas)


def linhas(conn, tabela: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def medir(conn, sql: str) -> dict:
    """Mediana de RODADAS execuções com EXPLAIN (ANALYZE, BUFFERS), depois de uma de aquecimento."""
    conn.execute(sql).fetchall()  # aquecimento: cache do PostgreSQL
    tempos, buffers = [], []
    for _ in range(RODADAS):
        plano = conn.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}").fetchone()[0][0]
        tempos.append(plano["Execution Time"])
        topo = plano["Plan"]
        buffers.append(topo.get("Shared Hit Blocks", 0) + topo.get("Shared Read Blocks", 0))
    return {"mediana_ms": round(statistics.median(tempos), 1),
            "min_ms": round(min(tempos), 1), "max_ms": round(max(tempos), 1),
            "buffers_8kb": int(statistics.median(buffers)),
            "linhas_resultado": len(conn.execute(sql).fetchall())}


def consultas(conn) -> dict:
    return {f"{q}_{alt}": medir(conn, sql.format(fonte=fonte))
            for q, sql in (("Q1", Q1), ("Q2", Q2)) for alt, fonte in FONTES.items()}


def main() -> int:
    res: dict = {"gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "rodadas": RODADAS}
    with psycopg.connect(autocommit=True) as conn:
        res["postgres"] = conn.execute("SHOW server_version").fetchone()[0]
        log("montando a alternativa A...")
        conn.execute(MONTA_A)
        conn.execute("VACUUM ANALYZE ocorrencia, veiculo, pessoa")

        res["linhas"] = {
            "A": {t: linhas(conn, t) for t in TABELAS_A},
            "C": {t: linhas(conn, t) for t in ("ocorrencia", "veiculo", "pessoa", "linha_rejeitada")},
        }
        res["tamanho_bytes"] = {"A": tamanho(conn, TABELAS_A), "C": tamanho(conn, TABELAS_C)}
        res["tamanho_por_tabela_C"] = {t: tamanho(conn, [t]) for t in TABELAS_C}

        log("medindo as consultas...")
        res["consultas"] = consultas(conn)

        log(f"simulando uma republicação de {ANO_REGRAVADO}...")
        antes = tamanho(conn, TABELAS_C)
        with conn.transaction(force_rollback=True):
            # Mesmo caminho da carga (#4): um lote novo do ano, com todas as linhas do ano.
            velho = conn.execute("SELECT id_lote FROM lote_vigente WHERE ano = %s", (ANO_REGRAVADO,)).fetchone()[0]
            novo = conn.execute(
                "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (%s, 'concluido', now()) RETURNING id_lote",
                (ANO_REGRAVADO,)).fetchone()[0]
            n = {}
            for tabela in ("ocorrencia", "veiculo", "pessoa"):
                cols = [r[0] for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s "
                    "AND column_name NOT IN ('id_lote', 'ano') ORDER BY ordinal_position", (tabela,))]
                lista = ", ".join(cols)
                n[tabela] = conn.execute(
                    f"INSERT INTO {tabela} (id_lote, {lista}) SELECT %s, {lista} FROM {tabela} WHERE id_lote = %s",
                    (novo, velho)).rowcount
            conn.execute("ANALYZE ocorrencia, veiculo, pessoa")
            res["republicacao"] = {
                "ano": ANO_REGRAVADO,
                "linhas_adicionadas": n,
                "bytes_adicionados": tamanho(conn, TABELAS_C) - antes,
                "consultas_C_com_duas_versoes": {
                    q: medir(conn, sql.format(fonte=FONTES["C"])) for q, sql in (("Q1", Q1), ("Q2", Q2))},
            }
        conn.execute("VACUUM ocorrencia, veiculo, pessoa, lote_carga")
        conn.execute("DROP SCHEMA alt_a CASCADE")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    log(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
