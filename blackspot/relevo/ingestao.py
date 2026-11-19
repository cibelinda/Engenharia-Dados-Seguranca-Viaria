"""Ingestão do relevo do IBGE para o schema `relevo` do PostgreSQL (issue #59).

Uso:
    python -m blackspot.relevo.ingestao

Baixa o mapeamento de geomorfologia do IBGE (escala 1:250.000, versão 2026) e grava um
polígono por modelado de relevo em `relevo.modelado`, com o compartimento (planalto, serra,
planície...), a unidade geomorfológica e o domínio morfoestrutural.

O arquivo é um shapefile nacional (~500 MB compactado). Ele fica guardado em
data/raw/relevo/ e só é baixado de novo se faltar ou se o SHA-256 não bater. Pode rodar de
novo sem duplicar: tudo acontece numa transação, que troca o conteúdo da tabela.

O shapefile é lido aqui mesmo, sem GDAL: o formato é simples (.dbf com os atributos, .shp
com as coordenadas). Cada polígono vai para o banco como o conjunto dos seus anéis, e o
PostGIS remonta o polígono (ST_BuildArea), decidindo o que é contorno e o que é buraco.
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import BinaryIO, Iterator

import psycopg

URL = ("https://geoftp.ibge.gov.br/informacoes_ambientais/geomorfologia/vetores/"
       "escala_250_mil/versao_2026/geom_area.zip")
# SHA-256 do arquivo baixado em 2026-11-18. Se o IBGE republicar, a ingestão avisa e segue
# com o arquivo novo (como o downloader da PRF): o hash lido fica registrado em relevo.carga.
SHA256_REFERENCIA = "2a12a4bff6fcdca7470f5aee38984539d6ea27f1c9e99a6847b3b17b6ad33210"

# Campos do .dbf (o nome vem truncado em 10 letras) -> coluna de relevo.modelado.
CAMPOS = {
    "id1": "id1",
    "compartime": "compartimento",
    "nm_dominio": "nm_dominio",
    "nm_regiao": "nm_regiao",
    "id_unidade": "id_unidade",
    "nm_unidade": "nm_unidade",
    "categoria": "categoria",
    "natureza": "natureza",
    "forma": "forma",
    "dens_dren": "dens_dren",
    "aprof_inci": "aprof_inci",
    "leg_carga": "legenda",
    "ar_poli_km": "area_km2",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(destino: Path) -> str:
    """Garante o zip em `destino` e devolve o SHA-256 dele."""
    if destino.exists() and sha256(destino) == SHA256_REFERENCIA:
        log(f"  {destino.name} já baixado e íntegro")
        return SHA256_REFERENCIA
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".parcial")
    log(f"  baixando {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": "blackspot/0.1 (BD2 FCTE/UnB)"})
    with urllib.request.urlopen(req, timeout=120) as resp, temporario.open("wb") as f:
        for bloco in iter(lambda: resp.read(1 << 20), b""):
            f.write(bloco)
    temporario.replace(destino)
    lido = sha256(destino)
    if lido != SHA256_REFERENCIA:
        log(f"  AVISO: SHA-256 {lido} diferente da referência {SHA256_REFERENCIA}; "
            "o IBGE pode ter republicado o arquivo. Seguindo com o arquivo novo.")
    return lido


def ler_dbf(f: BinaryIO, codificacao: str) -> Iterator[dict | None]:
    """Atributos do .dbf, um dicionário por registro (nome do campo em minúsculas)."""
    cabecalho = f.read(32)
    n_registros, tam_cabecalho, tam_registro = struct.unpack("<IHH", cabecalho[4:12])
    descritores = f.read(tam_cabecalho - 32)
    campos = []
    for pos in range(0, len(descritores) - 1, 32):
        if descritores[pos] == 0x0D:
            break
        nome = descritores[pos:pos + 11].split(b"\x00")[0].decode("ascii").lower()
        campos.append((nome, chr(descritores[pos + 11]), descritores[pos + 16]))
    for _ in range(n_registros):
        reg = f.read(tam_registro)
        if reg[:1] == b"*":  # registro apagado
            yield None
            continue
        valores, pos = {}, 1
        for nome, tipo, tamanho in campos:
            bruto = reg[pos:pos + tamanho].decode(codificacao).strip()
            pos += tamanho
            # "*****": número que não coube no campo (o próprio .dbf marca assim). Vira NULL.
            if not bruto or bruto.startswith("*"):
                valores[nome] = None
            elif tipo in "NF":
                valores[nome] = float(bruto) if "." in bruto else int(bruto)
            else:
                valores[nome] = bruto
        yield valores


def ler_shp(f: BinaryIO) -> Iterator[bytes | None]:
    """Cada polígono do .shp como WKB de MULTILINESTRING com os seus anéis (None se vazio)."""
    cabecalho = f.read(100)
    tipo = struct.unpack("<i", cabecalho[32:36])[0]
    if tipo not in (5, 15, 25):
        raise ValueError(f"o shapefile não é de polígonos (tipo {tipo})")
    while (cab_registro := f.read(8)):
        _, tam_palavras = struct.unpack(">ii", cab_registro)
        conteudo = f.read(2 * tam_palavras)
        if struct.unpack("<i", conteudo[:4])[0] == 0:  # forma nula
            yield None
            continue
        n_partes, n_pontos = struct.unpack("<ii", conteudo[36:44])
        partes = list(struct.unpack(f"<{n_partes}i", conteudo[44:44 + 4 * n_partes])) + [n_pontos]
        base = 44 + 4 * n_partes  # os pontos já estão como doubles little-endian, igual ao WKB
        wkb = [struct.pack("<BII", 1, 5, n_partes)]
        for a, b in zip(partes, partes[1:]):
            wkb.append(struct.pack("<BII", 1, 2, b - a))
            wkb.append(conteudo[base + 16 * a:base + 16 * b])
        yield b"".join(wkb)


def main() -> int:
    inicio = time.monotonic()
    raw = Path(os.environ.get("BLACKSPOT_RAW_DIR", "data/raw")) / "relevo"
    arquivo = raw / "geom_area_2026.zip"
    hash_lido = baixar(arquivo)

    colunas = ", ".join(CAMPOS.values())
    with zipfile.ZipFile(arquivo) as z, psycopg.connect() as conn, conn.transaction():
        prj = z.read("geom_area.prj").decode("ascii", "replace").upper()
        if "SIRGAS" not in prj or "PROJCS" in prj:
            raise RuntimeError(f"projeção inesperada no .prj (esperado SIRGAS 2000 geográfico): {prj}")
        cpg = z.read("geom_area.cpg").decode("ascii").strip() if "geom_area.cpg" in z.namelist() else "latin-1"
        codificacao = "utf-8" if "UTF" in cpg.upper() else cpg

        id_carga = conn.execute(
            "INSERT INTO relevo.carga (arquivo, sha256) VALUES (%s, %s) RETURNING id_carga",
            (URL, hash_lido)).fetchone()[0]
        conn.execute("TRUNCATE relevo.modelado")
        conn.execute(f"""CREATE TEMP TABLE modelado_bruto ({", ".join(f"{c} text" for c in CAMPOS.values())},
                         aneis bytea) ON COMMIT DROP""")
        # Lê o .dbf e o .shp juntos, registro a registro, direto do zip para o COPY.
        lidos = 0
        with z.open("geom_area.dbf") as dbf, z.open("geom_area.shp") as shp, \
                conn.cursor().copy(f"COPY modelado_bruto ({colunas}, aneis) FROM STDIN") as copia:
            for atributos, wkb in zip(ler_dbf(dbf, codificacao), ler_shp(shp)):
                if atributos is None or wkb is None:
                    continue
                copia.write_row(tuple(atributos.get(c) for c in CAMPOS) + (wkb,))
                lidos += 1
        log(f"  polígonos lidos: {lidos}; remontando no PostGIS")
        # Alguns anéis do IBGE cruzam a si mesmos, e aí o ST_BuildArea devolve NULL. Nesses,
        # o ST_Node quebra o anel nos cruzamentos antes de remontar (a área bate com a do IBGE).
        conn.execute(f"""
            INSERT INTO relevo.modelado ({colunas}, geom, id_carga)
            SELECT id1::numeric::integer, compartimento, nm_dominio, nm_regiao, id_unidade::numeric::integer,
                   nm_unidade, categoria, natureza, forma, dens_dren, aprof_inci, legenda, area_km2::numeric,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(area), 3)),
                   %s
            FROM modelado_bruto,
                 LATERAL (SELECT ST_GeomFromWKB(aneis, 4674) AS linhas) l,
                 LATERAL (SELECT coalesce(ST_BuildArea(linhas), ST_BuildArea(ST_Node(linhas))) AS area) a
            WHERE area IS NOT NULL""", (id_carga,))
        n = conn.execute("SELECT count(*) FROM relevo.modelado").fetchone()[0]
        if n < lidos:
            log(f"  AVISO: {lidos - n} polígonos sem área válida ficaram de fora")
        conn.execute("UPDATE relevo.carga SET terminada_em = clock_timestamp(), poligonos = %s WHERE id_carga = %s",
                     (n, id_carga))

    log(f"\ningestão do relevo terminada em {time.monotonic() - inicio:.0f} s ({n} polígonos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
