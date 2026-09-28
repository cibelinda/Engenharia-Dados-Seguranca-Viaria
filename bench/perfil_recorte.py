"""Perfil do recorte (BAT 2017–2025, ocorrência e pessoa) direto dos ZIPs baixados.

Gera os números de cardinalidade, sazonalidade e chaves usados na caracterização
da carga (issue #6), sem depender do banco. Quando a carga real (#4) existir, os
mesmos números devem ser conferidos no PostgreSQL.

Uso:
    python -m blackspot.download --system bat --dataset ocorrencia --dataset pessoa \\
        --year 2017 ... --year 2025
    python bench/perfil_recorte.py            # grava bench/resultados/perfil_recorte.json

Só usa a biblioteca padrão.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import statistics
import sys
import zipfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / os.environ.get("BLACKSPOT_RAW_DIR", "data/raw")
OUT = REPO_ROOT / "bench" / "resultados" / "perfil_recorte.json"
ANOS = range(2017, 2026)
ENCODING = "cp1252"  # todos os arquivos da PRF, sem BOM (docs/fontes/README.md)
TRECHO_KM = 10


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def ler(zip_name: str):
    """Itera os registros do único CSV do ZIP como dicionários (valores com strip)."""
    with zipfile.ZipFile(RAW_DIR / zip_name) as zf:
        (member,) = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        with zf.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding=ENCODING, newline="")
            for row in csv.DictReader(text, delimiter=";"):
                yield {k: (v or "").strip() for k, v in row.items()}


def inteiro(v: str) -> int | None:
    return int(v) if v.isdigit() else None


def decimal(v: str) -> float | None:
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def resumo(valores: list[int]) -> dict:
    valores = sorted(valores)
    return {
        "media": round(statistics.fmean(valores), 3),
        "mediana": statistics.median(valores),
        "p95": valores[int(0.95 * (len(valores) - 1))],
        "max": valores[-1],
    }


def perfil_ocorrencia() -> tuple[dict, set[str]]:
    por_ano, graves_ano, por_mes, por_ano_mes = Counter(), Counter(), Counter(), Counter()
    classificacao, causa, tipo, br, uf, municipio = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    trechos: set[tuple] = set()
    ids: Counter = Counter()
    ids_notacao: list[str] = []
    id_invalido = km_invalido = br_invalido = br_zero = sem_coord = data_invalida = 0
    pessoas, veiculos = [], []

    for ano in ANOS:
        for r in ler(f"datatran{ano}.zip"):
            por_ano[ano] += 1
            ids[r["id"]] += 1
            if not r["id"].isdigit():
                id_invalido += 1
                ids_notacao.append(r["id"])
            data = r["data_inversa"]
            if len(data) == 10 and data[4] == "-":
                por_mes[int(data[5:7])] += 1
                por_ano_mes[data[:7]] += 1
            else:
                data_invalida += 1
            mortos, fg = inteiro(r["mortos"]) or 0, inteiro(r["feridos_graves"]) or 0
            if mortos > 0 or fg > 0:
                graves_ano[ano] += 1
            classificacao[r["classificacao_acidente"]] += 1
            causa[r["causa_acidente"]] += 1
            tipo[r["tipo_acidente"]] += 1
            uf[r["uf"]] += 1
            municipio[(r["uf"], r["municipio"])] += 1
            b, km = inteiro(r["br"]), decimal(r["km"])
            br[r["br"]] += 1
            if b is None:
                br_invalido += 1
            elif b == 0:
                br_zero += 1  # rodovia não identificada
            if km is None:
                km_invalido += 1
            if b is not None and km is not None:
                trechos.add((b, r["uf"], int(km // TRECHO_KM)))
            if decimal(r["latitude"]) is None or decimal(r["longitude"]) is None:
                sem_coord += 1
            if (p := inteiro(r["pessoas"])) is not None:
                pessoas.append(p)
            if (v := inteiro(r["veiculos"])) is not None:
                veiculos.append(v)
        log(f"  ocorrencia {ano}: {por_ano[ano]}")

    total = sum(por_ano.values())
    meses_ano = sorted(por_ano_mes)
    return {
        "registros_por_ano": dict(por_ano),
        "registros_total": total,
        "graves_por_ano": dict(graves_ano),
        "graves_total": sum(graves_ano.values()),
        "ids_distintos": len(ids),
        "ids_repetidos": sum(1 for n in ids.values() if n > 1),
        "ids_nao_numericos": id_invalido,
        "ids_nao_numericos_valores": ids_notacao,
        "data_fora_do_formato": data_invalida,
        "br_invalida": br_invalido,
        "br_zero": br_zero,
        "km_invalido": km_invalido,
        "sem_coordenada_valida": sem_coord,
        "trechos_distintos_10km": len(trechos),
        "distintos": {
            "classificacao_acidente": len(classificacao),
            "causa_acidente": len(causa),
            "tipo_acidente": len(tipo),
            "br": len(br),
            "uf": len(uf),
            "municipio_uf": len(municipio),
        },
        "classificacao_acidente": dict(classificacao.most_common()),
        "pessoas_por_ocorrencia_coluna": resumo(pessoas),
        "veiculos_por_ocorrencia_coluna": resumo(veiculos),
        "por_mes_do_ano_total": {m: por_mes[m] for m in range(1, 13)},
        "por_ano_mes": {k: por_ano_mes[k] for k in meses_ano},
    }, set(ids)


def perfil_pessoa(ids_ocorrencia: set[str]) -> dict:
    por_ano = Counter()
    por_ocorrencia: Counter = Counter()
    veiculos_por_ocorrencia: dict[str, set] = {}
    pares, triplas = Counter(), Counter()
    pesids, veic = set(), set()
    pesid_vazio = veic_vazio = pesid_zero = 0
    pesid_real: Counter = Counter()  # pesid != 0, isto é, linha que é de fato uma pessoa
    pesid_zero_por_envolvido: Counter = Counter()
    registros_id_nao_numerico: Counter = Counter()
    dup_por_ano = {}

    for ano in ANOS:
        pares_ano, triplas_ano, linhas = set(), set(), 0
        for r in ler(f"acidentes{ano}.zip"):
            linhas += 1
            i, p, v = r["id"], r["pesid"], r["id_veiculo"]
            por_ocorrencia[i] += 1
            veiculos_por_ocorrencia.setdefault(i, set()).add(v)
            pares[(i, p)] += 1
            triplas[(i, p, v)] += 1
            pares_ano.add((i, p))
            triplas_ano.add((i, p, v))
            pesids.add(p)
            veic.add(v)
            pesid_vazio += not p
            if p == "0":
                pesid_zero += 1  # veículo sem pessoa associada
                pesid_zero_por_envolvido[f"{r['tipo_envolvido']}/{r['estado_fisico']}"] += 1
            else:
                pesid_real[p] += 1
            veic_vazio += not v
            if not i.isdigit():
                registros_id_nao_numerico[i] += 1
        por_ano[ano] = linhas
        dup_por_ano[ano] = {
            "linhas": linhas,
            "pares_id_pesid_distintos": len(pares_ano),
            "triplas_id_pesid_veiculo_distintas": len(triplas_ano),
        }
        log(f"  pessoa {ano}: {linhas}")

    ids_pessoa = set(por_ocorrencia)
    return {
        "registros_por_ano": dict(por_ano),
        "registros_total": sum(por_ano.values()),
        "pesid_distintos": len(pesids),
        "id_veiculo_distintos": len(veic),
        "pesid_vazio": pesid_vazio,
        "id_veiculo_vazio": veic_vazio,
        "linhas_pesid_zero": pesid_zero,
        "linhas_pessoa_real": sum(pesid_real.values()),
        "pesid_real_repetido": sum(1 for n in pesid_real.values() if n > 1),
        "pesid_zero_por_tipo_envolvido_estado_fisico": dict(pesid_zero_por_envolvido.most_common()),
        "registros_com_id_nao_numerico": sum(registros_id_nao_numerico.values()),
        "registros_com_id_nao_numerico_por_id": dict(sorted(registros_id_nao_numerico.items())),
        "excedentes_id_pesid_com_pesid_zero": sum(n - 1 for (_, p), n in pares.items() if n > 1 and p == "0"),
        "chave_id_pesid": {
            "distintos": len(pares),
            "linhas_excedentes": sum(n - 1 for n in pares.values()),
        },
        "chave_id_pesid_id_veiculo": {
            "distintos": len(triplas),
            "linhas_excedentes": sum(n - 1 for n in triplas.values()),
        },
        "chaves_por_ano": dup_por_ano,
        "registros_por_ocorrencia": resumo(list(por_ocorrencia.values())),
        "veiculos_distintos_por_ocorrencia": resumo([len(s) for s in veiculos_por_ocorrencia.values()]),
        "ids_sem_ocorrencia": len(ids_pessoa - ids_ocorrencia),
        "ocorrencias_sem_pessoa": len(ids_ocorrencia - ids_pessoa),
    }


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    faltando = [f"{p}{a}.zip" for p in ("datatran", "acidentes") for a in ANOS
                if not (RAW_DIR / f"{p}{a}.zip").exists()]
    if faltando:
        log(f"faltam arquivos em {RAW_DIR}: {', '.join(faltando)}; rode o download antes")
        return 1
    log("ocorrencia:")
    oc, ids = perfil_ocorrencia()
    log("pessoa:")
    pe = perfil_pessoa(ids)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # SHA-256 dos arquivos lidos: identifica a versão da PRF que gerou estes números.
    arquivos = {z: sha256_of(RAW_DIR / z) for p in ("datatran", "acidentes") for z in
                (f"{p}{a}.zip" for a in ANOS)}
    OUT.write_text(json.dumps({"recorte": "BAT 2017-2025", "arquivos_sha256": arquivos,
                               "ocorrencia": oc, "pessoa": pe},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"\nresultado em {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
