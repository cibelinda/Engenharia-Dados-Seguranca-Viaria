"""Medição do ADR 0002: PostgreSQL sem extensão (E1) × PostgreSQL com PostGIS.

Roda contra o banco já carregado com o dataset completo:

    docker compose up --build -d && docker compose wait load
    docker compose run --rm -v ./bench:/app/bench load python bench/medicao_espacial.py

(O serviço `load`, e não o `tests`, porque o `tests` monta bench/resultados só para leitura.)

O que mede:
1. Raio: acidentes graves a menos de 2 km de um ponto, (a) como na E1, com latitude e
   longitude numéricas e a distância calculada por haversine, sem índice espacial, e (b) com
   PostGIS, ST_DWithin sobre geography e índice GiST. EXPLAIN (ANALYZE, BUFFERS), mediana de
   N execuções.
2. Agrupamento: ST_ClusterDBSCAN dos acidentes graves do BAT (2017–2025), o que nenhuma
   consulta da E1 conseguia fazer: quantos grupos, o tempo e os maiores, com o raio do menor
   círculo que contém cada grupo. Em duas variantes: com todos os pontos (100 m, 25
   acidentes) e sem os pontos repetidos do passo 4 (300 m, 20 acidentes). Com todos os pontos
   e 500 m, o DBSCAN encadeava regiões metropolitanas inteiras (BR-101/SC do km 0 ao 221).
3. Coerência entre o ponto e o trecho: para cada trecho de 10 km (BR + UF + km) do BAT, a
   distância mediana dos acidentes ao centro do trecho. Se o km publicado e a coordenada
   concordam, a distância é de poucos km.
4. Coordenadas repetidas: quantos pontos exatos concentram 10 ou mais acidentes (coordenada
   padrão, e não local do acidente), e que fração dos acidentes de cada ano está neles.
5. Espaço: tamanho da coluna geom e dos índices GiST.

Grava o resultado em bench/resultados/medicao_espacial.json. Só lê o banco.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

OUT = Path(__file__).resolve().parent / "resultados" / "medicao_espacial.json"
RODADAS = 5
RAIO_M = 2000
# (raio em metros, mínimo de acidentes) de cada variante do agrupamento. Com todos os pontos,
# um raio pequeno, porque os pontos repetidos já formam grupos densos; sem eles, um raio maior.
DBSCAN_PARAMS = {"todos_os_pontos": (100, 25), "sem_pontos_repetidos": (300, 20)}

GRAVE = "(mortos > 0 OR feridos_graves > 0)"

# O ponto do raio é o centro do maior grupo DBSCAN sem pontos repetidos (passo 2), para a
# consulta cair num ponto negro real.
RAIO_E1 = f"""
SELECT ano, count(*) FROM ocorrencia_vigente
WHERE {GRAVE} AND latitude IS NOT NULL
  AND 2 * 6371000 * asin(sqrt(
        power(sin(radians(latitude::float8 - %(lat)s) / 2), 2)
        + cos(radians(%(lat)s)) * cos(radians(latitude::float8))
          * power(sin(radians(longitude::float8 - %(lon)s) / 2), 2))) <= {RAIO_M}
GROUP BY ano
"""

RAIO_POSTGIS = f"""
SELECT ano, count(*) FROM ocorrencia_vigente
WHERE {GRAVE}
  AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4674)::geography, {RAIO_M})
GROUP BY ano
"""

# {filtro} tira ou não os pontos repetidos (ver REPETIDAS): com eles, os maiores grupos são
# coordenadas padrão, e não pontos negros.
DBSCAN = f"""
WITH repetidos AS (
    SELECT geom FROM ocorrencia_vigente WHERE geom IS NOT NULL GROUP BY geom HAVING count(*) >= 10
), graves AS (
    SELECT id_lote, id, br, uf, km, ano, ST_Transform(geom, 5880) AS p
    FROM ocorrencia_vigente o
    WHERE {GRAVE} AND geom IS NOT NULL AND ano BETWEEN 2017 AND 2025
      AND ({{filtro}})
), agrupado AS (
    SELECT *, ST_ClusterDBSCAN(p, eps := %(eps)s, minpoints := %(minpoints)s) OVER () AS grupo
    FROM graves
)
SELECT grupo, count(*) AS acidentes, count(DISTINCT ano) AS anos,
       mode() WITHIN GROUP (ORDER BY br) AS br, mode() WITHIN GROUP (ORDER BY uf) AS uf,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY km) AS km_mediano,
       (ST_MinimumBoundingRadius(ST_Collect(p))).radius AS raio_m,
       ST_Y(ST_Transform(ST_Centroid(ST_Collect(p)), 4674)) AS lat,
       ST_X(ST_Transform(ST_Centroid(ST_Collect(p)), 4674)) AS lon
FROM agrupado
WHERE grupo IS NOT NULL
GROUP BY grupo
ORDER BY acidentes DESC
"""

COERENCIA = """
WITH bat AS (
    SELECT br, uf, floor(km / 10) AS faixa, ST_Transform(geom, 5880) AS p
    FROM ocorrencia_vigente
    WHERE geom IS NOT NULL AND br <> 0 AND km IS NOT NULL
      AND ST_Intersects(geom, ST_MakeEnvelope(-74, -34, -28, 6, 4674))
), centro AS (
    SELECT br, uf, faixa, ST_Centroid(ST_Collect(p)) AS c, count(*) AS n
    FROM bat GROUP BY br, uf, faixa HAVING count(*) >= 20
), dist AS (
    SELECT b.br, b.uf, b.faixa, percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_Distance(b.p, c.c)) AS mediana_m
    FROM bat b JOIN centro c USING (br, uf, faixa)
    GROUP BY b.br, b.uf, b.faixa
)
SELECT count(*) AS trechos,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY mediana_m) AS mediana_das_medianas_m,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY mediana_m) AS p90_m,
       avg((mediana_m <= 5000)::int) AS fracao_ate_5km
FROM dist
"""

# Coordenadas repetidas: o mesmo ponto exato em 10 ou mais acidentes, quase sempre de kms
# diferentes, é uma coordenada padrão (ex.: a de uma unidade da PRF), e não o local do acidente.
REPETIDAS = """
SELECT count(*) FILTER (WHERE n >= 10) AS pontos_com_10_ou_mais,
       coalesce(sum(n) FILTER (WHERE n >= 10), 0) AS acidentes_nesses_pontos,
       max(n) AS maior_repeticao,
       count(*) FILTER (WHERE n >= 10 AND kms > 1) AS pontos_com_kms_diferentes
FROM (SELECT geom, count(*) AS n, count(DISTINCT km) AS kms
      FROM ocorrencia_vigente WHERE geom IS NOT NULL GROUP BY geom) t
"""

REPETIDAS_POR_ANO = """
SELECT ano, avg((n >= 10)::int)::float
FROM (SELECT ano, count(*) OVER (PARTITION BY geom) AS n FROM ocorrencia_vigente WHERE geom IS NOT NULL) t
GROUP BY ano ORDER BY ano
"""

ESPACO = """
SELECT (SELECT sum(pg_column_size(geom)) FROM ocorrencia) AS geom_bytes,
       pg_relation_size('ocorrencia_geom_idx') AS geom_idx_bytes,
       pg_relation_size('ocorrencia_geog_idx') AS geog_idx_bytes,
       pg_total_relation_size('ocorrencia') AS ocorrencia_bytes,
       pg_database_size(current_database()) AS banco_bytes
"""


def explain(conn: psycopg.Connection, sql: str, params: dict) -> dict:
    """Mediana de RODADAS execuções, depois de uma de aquecimento."""
    tempos, plano = [], None
    for i in range(RODADAS + 1):
        plano = conn.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", params).fetchone()[0][0]
        if i:
            tempos.append(plano["Execution Time"])
    texto = json.dumps(plano)
    return {
        "mediana_ms": round(statistics.median(tempos), 1),
        "min_ms": round(min(tempos), 1),
        "max_ms": round(max(tempos), 1),
        "usa_indice_espacial": "ocorrencia_geog_idx" in texto or "ocorrencia_geom_idx" in texto,
        "buffers": plano["Plan"].get("Shared Hit Blocks", 0) + plano["Plan"].get("Shared Read Blocks", 0),
    }


def main() -> int:
    with psycopg.connect() as conn:
        dbscan = {}
        for nome, filtro in (("todos_os_pontos", "true"),
                             ("sem_pontos_repetidos", "NOT EXISTS (SELECT 1 FROM repetidos r WHERE r.geom = o.geom)")):
            eps, minpoints = DBSCAN_PARAMS[nome]
            t0 = time.monotonic()
            grupos = conn.execute(DBSCAN.replace("{filtro}", filtro),
                                  {"eps": eps, "minpoints": minpoints}).fetchall()
            dbscan[nome] = {
                "eps_m": eps, "minpoints": minpoints,
                "grupos": len(grupos), "acidentes_em_grupos": sum(g[1] for g in grupos),
                "segundos": round(time.monotonic() - t0, 1),
                "maiores": [
                    {"acidentes": n, "anos": anos, "br": br, "uf": uf, "km_mediano": float(km),
                     "raio_m": round(raio), "lat": round(lat, 5), "lon": round(lon, 5)}
                    for _, n, anos, br, uf, km, raio, lat, lon in grupos[:10]],
            }
        maior = dbscan["sem_pontos_repetidos"]["maiores"][0]
        ponto = {"lat": maior["lat"], "lon": maior["lon"]}

        # Haversine usa uma esfera; geography, o elipsoide. Na borda do raio as contagens
        # podem diferir em poucos acidentes, e as duas ficam registradas.
        e1 = conn.execute(RAIO_E1, ponto).fetchall()
        pg = conn.execute(RAIO_POSTGIS, ponto).fetchall()

        trechos, mediana, p90, ate5 = conn.execute(COERENCIA).fetchone()
        pontos10, acidentes10, maior_rep, kms_diferentes = conn.execute(REPETIDAS).fetchone()
        por_ano = {ano: round(f, 3) for ano, f in conn.execute(REPETIDAS_POR_ANO).fetchall()}
        geom_b, geom_idx_b, geog_idx_b, oc_b, banco_b = conn.execute(ESPACO).fetchone()

        resultado = {
            "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "postgis": conn.execute("SELECT postgis_full_version()").fetchone()[0],
            "raio": {
                "raio_m": RAIO_M, "ponto": ponto,
                "graves_no_raio_postgis": sum(n for _, n in pg),
                "graves_no_raio_haversine": sum(n for _, n in e1),
                "e1_haversine_sem_indice": explain(conn, RAIO_E1, ponto),
                "postgis_geography_gist": explain(conn, RAIO_POSTGIS, ponto),
            },
            "dbscan": {"periodo": "2017-2025", **dbscan},
            "coerencia_ponto_trecho": {
                "trechos_com_20_ou_mais": trechos,
                "mediana_das_medianas_m": round(mediana),
                "p90_das_medianas_m": round(p90),
                "fracao_ate_5km": round(float(ate5), 3),
            },
            "coordenadas_repetidas": {
                "pontos_com_10_ou_mais_acidentes": pontos10,
                "acidentes_nesses_pontos": int(acidentes10),
                "maior_repeticao": maior_rep,
                "pontos_com_kms_diferentes": kms_diferentes,
                "fracao_dos_acidentes_por_ano": por_ano,
            },
            "espaco": {
                "coluna_geom_mb": round(geom_b / 2**20, 1),
                "indice_geom_mb": round(geom_idx_b / 2**20, 1),
                "indice_geography_mb": round(geog_idx_b / 2**20, 1),
                "ocorrencia_total_mb": round(oc_b / 2**20, 1),
                "banco_mb": round(banco_b / 2**20, 1),
            },
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(resultado, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
