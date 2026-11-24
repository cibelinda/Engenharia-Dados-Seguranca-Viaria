"""ETL reverso dos trechos críticos (E4, issue #54). Decisão e medição no ADR 0006; quem consome
e o que faz com o dado em docs/e4/etl-reverso.md.

Uso (dentro do container da orquestração; o Dagster roda o mesmo comando, todo dia depois do
dbt build):
    python -m orquestracao.etl_reverso

Quem consome: a superintendência da PRF em cada UF, que usa a lista para decidir onde pôr
viatura e operação de fiscalização no mês seguinte. Cada UF recebe só o próprio arquivo.

O que sai, no destino (ETL_REVERSO_DESTINO, uma pasta compartilhada):

    geracoes/2026-11-23T030512/trechos_criticos_MG.csv   um CSV por UF
                               ...
                               manifesto.json            data, linhas e SHA-256 de cada arquivo
    atual -> geracoes/2026-11-23T030512                  a geração vigente

Trecho crítico é o que ficou entre os 50 mais graves do ano em pelo menos um ano completo
(anos_completos_no_top_50 >= 1): o ano corrente, parcial, não basta, porque no começo do ano
poucas semanas de dado já põem um trecho no top 50. Nenhuma métrica é calculada aqui: as colunas vêm prontas de
analitico_marts (contrato da E4), e este módulo só escolhe as colunas e separa por UF.

Entrega segura para quem lê:
- a geração nova é escrita inteira numa pasta própria, e só no fim o link `atual` passa a
  apontar para ela (troca atômica). Quem abre `atual/` nunca vê metade de uma geração;
- se o destino estiver fora do ar (pasta ausente ou sem permissão de escrita), o comando falha,
  o Dagster tenta de novo, e o `atual` continua na geração anterior;
- se o dado não mudou desde a última geração (mesmo SHA-256 em todos os arquivos), nada é
  escrito: a PRF republica uma vez por mês, e o ETL roda todo dia;
- ficam as últimas GERACOES_MANTIDAS gerações; as mais antigas são apagadas.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

DESTINO = Path(os.environ.get("ETL_REVERSO_DESTINO", "/app/saida/trechos_criticos"))
GERACOES_MANTIDAS = int(os.environ.get("ETL_REVERSO_GERACOES", "6"))
SCHEMA = "analitico_marts"

# Colunas do arquivo, na ordem. As descrições vão no manifesto, para quem abre o CSV saber o
# que cada coluna quer dizer sem procurar documentação.
COLUNAS = {
    "trecho": "BR, UF e faixa de 10 km (ex.: BR-116/MG km 400–410)",
    "br": "Número da rodovia federal",
    "km_inicio": "Início da faixa de 10 km",
    "km_fim": "Fim da faixa de 10 km",
    "anos_completos_no_top_50": "Em quantos anos completos o trecho ficou entre os 50 mais graves do país",
    "anos_no_top_50": "O mesmo, contando também o ano corrente (parcial)",
    "primeiro_ano_no_top_50": "Primeiro ano em que ficou entre os 50 mais graves",
    "ultimo_ano_no_top_50": "Último ano em que ficou entre os 50 mais graves",
    "graves_nos_anos_no_top_50": "Acidentes graves somados nos anos em que ficou no top 50",
    "ano_referencia": "Último ano completo da PRF",
    "graves_ano_referencia": "Acidentes com morto ou ferido grave no ano de referência",
    "mortos_ano_referencia": "Mortos no ano de referência",
    "posicao_ano_referencia": "Posição no ranking nacional do ano de referência (1 = o pior)",
}

CONSULTA = f"""
with referencia as (
    select max(ano) as ano from {SCHEMA}.mart_risco_trecho_ano where ano_completo
)
select
    p.uf,
    p.rotulo                    as trecho,
    p.br,
    p.km_inicio,
    p.km_fim,
    p.anos_completos_no_top_50,
    p.anos_no_top_50,
    p.primeiro_ano_no_top_50,
    p.ultimo_ano_no_top_50,
    p.graves_no_total           as graves_nos_anos_no_top_50,
    r.ano                       as ano_referencia,
    coalesce(a.graves, 0)       as graves_ano_referencia,
    coalesce(a.mortos, 0)       as mortos_ano_referencia,
    a.posicao                   as posicao_ano_referencia
from {SCHEMA}.mart_persistencia_trecho p
cross join referencia r
left join {SCHEMA}.mart_risco_trecho_ano a
       on a.chave_trecho = p.chave_trecho and a.ano = r.ano
where p.anos_completos_no_top_50 >= 1
order by p.uf, p.anos_completos_no_top_50 desc, p.graves_no_total desc, p.br, p.km_inicio
"""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def consultar() -> list[dict]:
    with psycopg.connect() as conn, conn.cursor() as cur:
        cur.execute(CONSULTA)
        nomes = [c.name for c in cur.description]
        return [dict(zip(nomes, linha)) for linha in cur.fetchall()]


def csv_da_uf(linhas: list[dict]) -> bytes:
    """CSV como o Excel em português abre sem configurar nada: `;` e UTF-8 com BOM."""
    buf = io.StringIO()
    escritor = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    escritor.writerow(COLUNAS)
    for linha in linhas:
        escritor.writerow(["" if linha[c] is None else linha[c] for c in COLUNAS])
    return buf.getvalue().encode("utf-8-sig")


def montar(linhas: list[dict]) -> dict[str, bytes]:
    """Um arquivo por UF: nome -> conteúdo."""
    por_uf: dict[str, list[dict]] = {}
    for linha in linhas:
        por_uf.setdefault(linha["uf"], []).append(linha)
    return {f"trechos_criticos_{uf}.csv": csv_da_uf(ls) for uf, ls in sorted(por_uf.items())}


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def manifesto_atual(destino: Path) -> dict | None:
    try:
        return json.loads((destino / "atual" / "manifesto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def publicar(arquivos: dict[str, bytes], destino: Path, gerado_em: datetime) -> tuple[str, bool]:
    """Escreve a geração e troca o link `atual`. Devolve (pasta da geração, se escreveu)."""
    if not destino.is_dir() or not os.access(destino, os.W_OK):
        raise RuntimeError(f"destino fora do ar: {destino} não existe ou não aceita escrita")

    hashes = {nome: sha256(dados) for nome, dados in arquivos.items()}
    anterior = manifesto_atual(destino)
    if anterior and {n: a["sha256"] for n, a in anterior["arquivos"].items()} == hashes:
        return anterior["geracao"], False

    geracao = gerado_em.strftime("%Y-%m-%dT%H%M%S")
    pasta = destino / "geracoes" / geracao
    temporaria = destino / "geracoes" / f".{geracao}.parcial"
    shutil.rmtree(temporaria, ignore_errors=True)
    temporaria.mkdir(parents=True)
    for nome, dados in arquivos.items():
        (temporaria / nome).write_bytes(dados)
    manifesto = {
        "geracao": geracao,
        "gerado_em": gerado_em.isoformat(timespec="seconds"),
        "fonte": f"{SCHEMA}.mart_persistencia_trecho e {SCHEMA}.mart_risco_trecho_ano",
        "criterio": "trecho que ficou entre os 50 mais graves do ano em pelo menos um ano completo",
        "colunas": COLUNAS,
        "arquivos": {n: {"linhas": dados.count(b"\r\n") - 1, "bytes": len(dados), "sha256": hashes[n]}
                     for n, dados in arquivos.items()},
    }
    (temporaria / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    temporaria.rename(pasta)

    # Troca atômica do link: cria o novo ao lado e renomeia por cima do antigo.
    link_novo = destino / ".atual.novo"
    if link_novo.is_symlink() or link_novo.exists():
        link_novo.unlink()
    link_novo.symlink_to(Path("geracoes") / geracao)
    os.replace(link_novo, destino / "atual")

    antigas = sorted(p for p in (destino / "geracoes").iterdir() if not p.name.startswith("."))
    for velha in antigas[:-GERACOES_MANTIDAS]:
        shutil.rmtree(velha)
    return geracao, True


def main() -> int:
    inicio = time.monotonic()
    linhas = consultar()
    if not linhas:
        raise RuntimeError("nenhum trecho crítico: a mart_persistencia_trecho está vazia?")
    arquivos = montar(linhas)
    geracao, escreveu = publicar(arquivos, DESTINO, datetime.now(timezone.utc).astimezone())
    situacao = "geração nova" if escreveu else "sem mudança, geração mantida"
    log(f"ETL reverso terminado em {time.monotonic() - inicio:.1f} s: {len(linhas)} trechos "
        f"críticos, {len(arquivos)} UFs, {situacao} ({geracao})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
