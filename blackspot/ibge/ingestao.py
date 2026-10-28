"""Ingestão da base de municípios do IBGE para o schema `ibge` do PostgreSQL.

Uso:
    python -m blackspot.ibge.ingestao

Baixa três coisas das APIs públicas do IBGE e grava nas tabelas do schema `ibge`:
- a lista de municípios (código, nome e UF);
- a população de cada município por ano (estimativas anuais e os censos de 2010 e 2022);
- o contorno de cada município no mapa (malha municipal).

Pode rodar de novo sem duplicar: tudo acontece numa transação, que troca o conteúdo das
tabelas pelo que o IBGE publica hoje. O histórico de nome e UF fica no dbt (dim_municipio).
"""

from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.request

import psycopg

LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?intrarregiao=municipio"
         "&qualidade=intermediaria&formato=application/vnd.geo%2Bjson")
SIDRA = "https://apisidra.ibge.gov.br/values"
# Estimativas anuais (tabela 6579). A API limita 50 mil valores por consulta, então vai um
# ano por vez. 2007, 2010, 2022 e 2023 não têm estimativa.
ANOS_ESTIMATIVA = [a for a in range(2001, 2027) if a not in (2007, 2010, 2022, 2023)]
CENSOS = {
    2010: "/t/1378/n6/all/v/93/p/2010/c1/0/c2/0/c287/0/c455/0",
    2022: "/t/4709/n6/all/v/93/p/2022",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def baixar_json(url: str, tentativas: int = 3):
    for tentativa in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "blackspot/0.1 (BD2 FCTE/UnB)"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                corpo = resp.read()
            # A API do IBGE às vezes responde compactada (gzip) mesmo sem pedir.
            if corpo[:2] == b"\x1f\x8b":
                corpo = gzip.decompress(corpo)
            return json.loads(corpo)
        except OSError as e:
            if tentativa == tentativas:
                raise RuntimeError(f"falha ao baixar {url}: {e}") from e
            time.sleep(2 ** tentativa)


def uf_do_municipio(m: dict) -> str:
    """A UF vem dentro da microrregião; alguns municípios só têm a região imediata."""
    if m.get("microrregiao"):
        return m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    return m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]


def linhas_sidra(caminho: str, fonte: str) -> list[tuple]:
    dados = baixar_json(SIDRA + caminho)
    linhas = []
    for r in dados[1:]:  # a primeira linha é o cabeçalho
        if r["V"].isdigit():
            linhas.append((r["D1C"], int(r["D3N"]), int(r["V"]), fonte))
    return linhas


def main() -> int:
    inicio = time.monotonic()

    municipios = [(str(m["id"]), m["nome"], uf_do_municipio(m)) for m in baixar_json(LOCALIDADES)]
    log(f"  municípios: {len(municipios)}")

    populacao: dict[tuple[str, int], tuple] = {}
    for ano in ANOS_ESTIMATIVA:
        for cod, a, valor, fonte in linhas_sidra(f"/t/6579/n6/all/v/9324/p/{ano}", "estimativa"):
            populacao[(cod, a)] = (cod, a, valor, fonte)
    for ano, caminho in CENSOS.items():
        for cod, a, valor, fonte in linhas_sidra(caminho, "censo"):
            populacao[(cod, a)] = (cod, a, valor, fonte)
    log(f"  população: {len(populacao)} linhas (município × ano)")

    malha = baixar_json(MALHA)["features"]
    log(f"  malha municipal: {len(malha)} contornos")

    with psycopg.connect() as conn, conn.transaction():
        id_carga = conn.execute("INSERT INTO ibge.carga DEFAULT VALUES RETURNING id_carga").fetchone()[0]
        conn.execute("TRUNCATE ibge.municipio, ibge.populacao, ibge.malha_municipal")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO ibge.municipio (cod_municipio, nome, uf, id_carga) VALUES (%s, %s, %s, %s)",
                [(*m, id_carga) for m in municipios])
            cur.executemany(
                """INSERT INTO ibge.populacao (cod_municipio, ano, populacao, fonte, id_carga)
                   VALUES (%s, %s, %s, %s, %s)""",
                [(*p, id_carga) for p in populacao.values()])
            cur.executemany(
                """INSERT INTO ibge.malha_municipal (cod_municipio, geom, id_carga)
                   VALUES (%s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4674)), 3)), %s)""",
                [(f["properties"]["codarea"], json.dumps(f["geometry"]), id_carga) for f in malha])
        conn.execute(
            """UPDATE ibge.carga SET terminada_em = now(), municipios = %s, populacao = %s, malha = %s
               WHERE id_carga = %s""",
            (len(municipios), len(populacao), len(malha), id_carga))

    log(f"\ningestão do IBGE terminada em {time.monotonic() - inicio:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
