"""Carga dos arquivos da PRF no esquema da origem (issue #4).

Uso:
    python -m blackspot.load

Carrega o recorte do projeto (BAT 2017–2025, ocorrência e pessoa; ver
docs/pergunta-e-recorte.md), um ANO por vez. Cada ano vira um lote
(lote_carga), com os dois arquivos do ano (lote_arquivo): é o insert-only
versionado por lote de docs/modelagem-origem.md.

Reprocessamento: um ano só é carregado de novo quando o SHA-256 de algum dos
seus arquivos muda (republicação pela PRF). Rodar duas vezes com os mesmos
arquivos não grava nada na segunda.

Registros que não cabem no esquema vão para linha_rejeitada, com o motivo, e
lidas = carregadas + rejeitadas em cada arquivo. As regras de conversão estão
em docs/modelagem-origem.md, seção "Achados para a carga (issue #4)", e no
README.

A conexão vem das variáveis padrão do PostgreSQL (PGHOST, PGPORT, PGDATABASE,
PGUSER, PGPASSWORD). A pasta dos arquivos vem de BLACKSPOT_RAW_DIR.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psycopg
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / os.environ.get("BLACKSPOT_RAW_DIR", "data/raw")
MANIFEST = REPO_ROOT / "sources.yaml"
REPORT = "_download_report.json"
ENCODING = "cp1252"  # todos os arquivos da PRF, sem BOM (docs/fontes/README.md)

# Recorte do projeto (docs/pergunta-e-recorte.md).
SYSTEM = "bat"
YEARS = range(2017, 2026)
DATASETS = ("ocorrencia", "pessoa")

UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split())
CLASSIFICACOES = {"Sem Vítimas", "Com Vítimas Feridas", "Com Vítimas Fatais"}
ENVOLVIDOS = {"Condutor", "Passageiro", "Pedestre", "Testemunha", "Cavaleiro"}
SEM_VEICULO = {"Pedestre", "Testemunha", "Cavaleiro"}
ESTADOS = {"Ileso", "Lesões Leves", "Lesões Graves", "Óbito", "Não Informado"}
AUSENTE = {"", "NA", "N/A"}
IDADE_MAX = 110

OCORRENCIA_COLS = (
    "id_lote", "id", "ocorrido_em", "uf", "br", "km", "municipio", "latitude", "longitude",
    "id_causa", "id_tipo", "classificacao_acidente", "fase_dia", "sentido_via",
    "condicao_meteorologica", "tipo_pista", "tracado_via", "uso_solo_urbano",
    "pessoas", "mortos", "feridos_leves", "feridos_graves", "feridos", "ilesos", "ignorados",
    "veiculos", "regional", "delegacia", "uop",
)
CONTAGENS = ("pessoas", "mortos", "feridos_leves", "feridos_graves", "feridos", "ilesos", "ignorados", "veiculos")
VEICULO_COLS = ("id_lote", "id", "id_veiculo", "tipo_veiculo", "marca", "ano_fabricacao")
PESSOA_COLS = ("id_lote", "pesid", "id", "id_veiculo", "tipo_envolvido", "estado_fisico", "idade", "sexo")


class Rejeitada(Exception):
    """Registro que não cabe no esquema; a mensagem é o motivo."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- arquivos -----------------------------------------------------------------


@dataclass
class Arquivo:
    dataset: str
    chave: str
    path: Path
    sha256: str
    tamanho: int
    drive_last_modified: str | None
    lidas: int = 0
    rejeitadas: int = 0


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def arquivos_do_recorte() -> dict[int, dict[str, Arquivo]]:
    """Os arquivos do recorte, por ano, a partir do sources.yaml."""
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    report = {}
    if (RAW_DIR / REPORT).exists():
        report = {r["key"]: r for r in json.loads((RAW_DIR / REPORT).read_text(encoding="utf-8"))["results"]}
    por_ano: dict[int, dict[str, Arquivo]] = {}
    for e in manifest["files"]:
        if e["system"] != SYSTEM or e["dataset"] not in DATASETS or e["year"] not in YEARS:
            continue
        path = RAW_DIR / e["filename"]
        if not path.exists():
            raise SystemExit(f"{path.name} não encontrado em {RAW_DIR}; rode o download antes")
        sha = sha256_of(path)
        ref = e.get("reference") or {}
        # Data de publicação na fonte: a da referência se o arquivo é o mesmo; senão, a
        # que o download registrou; senão, desconhecida.
        if sha == ref.get("sha256"):
            modificado = ref.get("drive_last_modified")
        else:
            modificado = (report.get(e["key"]) or {}).get("drive_last_modified")
        por_ano.setdefault(e["year"], {})[e["dataset"]] = Arquivo(
            e["dataset"], e["key"], path, sha, path.stat().st_size, modificado)
    faltando = [y for y in YEARS if set(por_ano.get(y, {})) != set(DATASETS)]
    if faltando:
        raise SystemExit(f"sources.yaml sem os dois arquivos do recorte para: {faltando}")
    return por_ano


def registros(path: Path):
    """(número do registro a partir de 1, dict da linha, linha reconstruída)."""
    with zipfile.ZipFile(path) as zf:
        membros = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if len(membros) != 1:
            raise RuntimeError(f"{path.name}: esperado 1 CSV, encontrado(s) {len(membros)}")
        with zf.open(membros[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding=ENCODING, newline=""), delimiter=";")
            cabecalho = next(reader)
            for n, valores in enumerate(reader, start=1):
                yield n, dict(zip(cabecalho, valores)), valores


def linha_bruta(valores: list[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="").writerow(valores)
    return buf.getvalue()


# --- conversões -------------------------------------------------------------------


def inteiro(valor: str, campo: str) -> int:
    try:
        return int(valor)
    except ValueError:
        raise Rejeitada(f"{campo} não inteiro: {valor!r}") from None


def decimal(valor: str) -> float | None:
    try:
        return float(valor.replace(",", "."))
    except ValueError:
        return None


def ausente(valor: str) -> str | None:
    return None if valor.strip() in AUSENTE else valor


def coordenadas(lat: str, lon: str) -> tuple[str | None, str | None, bool]:
    """Latitude e longitude, ou as duas NULL se alguma estiver fora do limite válido."""
    la, lo = decimal(lat), decimal(lon)
    if la is None or lo is None or not (-90 <= la <= 90) or not (-180 <= lo <= 180):
        return None, None, True
    return lat.replace(",", "."), lon.replace(",", "."), False


def idade(valor: str) -> int | None:
    """0 é sentinela de desconhecida na fonte; negativas e acima de 110 também viram NULL."""
    if valor.strip() in AUSENTE:
        return None
    n = inteiro(valor, "idade")
    return n if 0 < n <= IDADE_MAX else None


def ano_fabricacao(valor: str) -> int | None:
    """0 é sentinela de desconhecido na fonte."""
    if valor.strip() in AUSENTE:
        return None
    n = inteiro(valor, "ano_fabricacao_veiculo")
    if n == 0:
        return None
    if n < 1900:
        raise Rejeitada(f"ano_fabricacao_veiculo inválido: {valor!r}")
    return n


# --- domínios ---------------------------------------------------------------------


class Dominio:
    """Catálogo cumulativo (causa_acidente, tipo_acidente): insere descrições novas."""

    def __init__(self, conn: psycopg.Connection, tabela: str, pk: str):
        self.conn, self.tabela, self.pk = conn, tabela, pk
        self.ids = dict(conn.execute(f"SELECT descricao, {pk} FROM {tabela}").fetchall())

    def id(self, descricao: str) -> int:
        if descricao not in self.ids:
            self.ids[descricao] = self.conn.execute(
                f"INSERT INTO {self.tabela} (descricao) VALUES (%s) RETURNING {self.pk}", (descricao,)
            ).fetchone()[0]
        return self.ids[descricao]


# --- carga de um ano --------------------------------------------------------------


@dataclass
class Resumo:
    ocorrencias: int = 0
    veiculos: int = 0
    pessoas: int = 0
    coordenadas_nulas: int = 0
    rejeitadas: list[tuple] = field(default_factory=list)


def rejeitar(resumo: Resumo, arq: Arquivo, n: int, valores: list[str], motivo: str) -> None:
    arq.rejeitadas += 1
    resumo.rejeitadas.append((arq.dataset, n, linha_bruta(valores), motivo))


def converter_ocorrencia(r: dict, id_lote: int, ano: int, causas: Dominio, tipos: Dominio, resumo: Resumo) -> tuple:
    id_ = inteiro(r["id"], "id")
    if id_ <= 0:
        raise Rejeitada(f"id não positivo: {r['id']!r}")
    try:
        ocorrido_em = datetime.strptime(f"{r['data_inversa']} {r['horario']}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise Rejeitada(f"data/horário inválidos: {r['data_inversa']!r} {r['horario']!r}") from None
    if ocorrido_em.year != ano:
        raise Rejeitada(f"data fora do ano do arquivo: {r['data_inversa']}")
    if r["uf"] not in UFS:
        raise Rejeitada(f"uf inválida: {r['uf']!r}")
    br = inteiro(r["br"], "br")
    if not 0 <= br <= 999:
        raise Rejeitada(f"br fora de 0–999: {br}")
    km = decimal(r["km"])
    if km is None or km < 0:
        raise Rejeitada(f"km inválido: {r['km']!r}")
    if not r["municipio"] or not r["causa_acidente"]:
        raise Rejeitada("municipio ou causa_acidente vazio")
    lat, lon, anulada = coordenadas(r["latitude"], r["longitude"])
    resumo.coordenadas_nulas += anulada
    classificacao = ausente(r["classificacao_acidente"])
    if classificacao is not None and classificacao not in CLASSIFICACOES:
        raise Rejeitada(f"classificacao_acidente inválida: {classificacao!r}")
    if r["uso_solo"] not in ("Sim", "Não"):
        raise Rejeitada(f"uso_solo inválido: {r['uso_solo']!r}")
    tracado = [t for t in r["tracado_via"].split(";") if t]
    for campo in ("fase_dia", "sentido_via", "condicao_metereologica", "tipo_pista"):
        if not r[campo]:
            raise Rejeitada(f"{campo} vazio")
    if not tracado:
        raise Rejeitada("tracado_via vazio")
    n = {c: inteiro(r[c], c) for c in CONTAGENS}
    if any(v < 0 for v in n.values()):
        raise Rejeitada("contagem negativa")
    if n["feridos"] != n["feridos_leves"] + n["feridos_graves"]:
        raise Rejeitada("feridos diferente de feridos_leves + feridos_graves")
    tipo = ausente(r["tipo_acidente"])
    return (
        id_lote, id_, ocorrido_em, r["uf"], br, f"{km:.1f}", r["municipio"], lat, lon,
        causas.id(r["causa_acidente"]), tipos.id(tipo) if tipo else None, classificacao,
        r["fase_dia"], r["sentido_via"], r["condicao_metereologica"], r["tipo_pista"], tracado,
        r["uso_solo"] == "Sim", *(n[c] for c in CONTAGENS),
        ausente(r["regional"]), ausente(r["delegacia"]), ausente(r["uop"]),
    )


def carregar_ano(conn: psycopg.Connection, ano: int, arqs: dict[str, Arquivo]) -> Resumo:
    """Carrega um ano inteiro numa transação. Se algo falhar, nada do ano fica gravado."""
    resumo = Resumo()
    id_lote = conn.execute("INSERT INTO lote_carga (ano) VALUES (%s) RETURNING id_lote", (ano,)).fetchone()[0]
    for a in arqs.values():
        conn.execute(
            """INSERT INTO lote_arquivo (id_lote, dataset, chave_manifesto, arquivo, sha256,
                                         tamanho_bytes, drive_last_modified)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (id_lote, a.dataset, a.chave, a.path.name, a.sha256, a.tamanho, a.drive_last_modified))
    causas = Dominio(conn, "causa_acidente", "id_causa")
    tipos = Dominio(conn, "tipo_acidente", "id_tipo")

    # Ocorrências
    arq = arqs["ocorrencia"]
    ids: set[int] = set()
    linhas = []
    for n, r, valores in registros(arq.path):
        arq.lidas += 1
        try:
            linha = converter_ocorrencia(r, id_lote, ano, causas, tipos, resumo)
            if linha[1] in ids:
                raise Rejeitada(f"id repetido no arquivo: {linha[1]}")
        except Rejeitada as e:
            rejeitar(resumo, arq, n, valores, str(e))
            continue
        ids.add(linha[1])
        linhas.append(linha)
    copiar(conn, "ocorrencia", OCORRENCIA_COLS, linhas)
    resumo.ocorrencias = len(linhas)

    # Veículos e pessoas (o mesmo arquivo: pesid = 0 é veículo sem pessoa, id_veiculo = 0 é
    # pessoa sem veículo)
    arq = arqs["pessoa"]
    veiculos: dict[int, tuple] = {}
    pessoas: dict[int, tuple] = {}
    for n, r, valores in registros(arq.path):
        arq.lidas += 1
        try:
            id_ = inteiro(r["id"], "id")
            pesid = inteiro(r["pesid"], "pesid")
            id_veiculo = inteiro(r["id_veiculo"], "id_veiculo")
            if pesid == 0 and id_veiculo == 0:
                raise Rejeitada("pesid = 0 e id_veiculo = 0: nem pessoa nem veículo")
            if id_ not in ids:
                raise Rejeitada(f"sem ocorrência carregada: id {id_}")
            veiculo = None
            if id_veiculo != 0:
                if not r["tipo_veiculo"] or not r["marca"]:
                    raise Rejeitada("tipo_veiculo ou marca vazio")
                veiculo = (id_lote, id_, id_veiculo, r["tipo_veiculo"], r["marca"],
                           ano_fabricacao(r["ano_fabricacao_veiculo"]))
                if id_veiculo in veiculos and veiculos[id_veiculo][1] != id_:
                    raise Rejeitada(f"id_veiculo {id_veiculo} em duas ocorrências")
            pessoa = None
            if pesid != 0:
                if pesid in pessoas:
                    raise Rejeitada(f"pesid repetido: {pesid}")
                envolvido, estado = r["tipo_envolvido"], r["estado_fisico"]
                if envolvido not in ENVOLVIDOS:
                    raise Rejeitada(f"tipo_envolvido inválido: {envolvido!r}")
                if estado not in ESTADOS:
                    raise Rejeitada(f"estado_fisico inválido: {estado!r}")
                if (id_veiculo == 0) != (envolvido in SEM_VEICULO):
                    raise Rejeitada(f"{envolvido} com id_veiculo = {id_veiculo}")
                if not r["sexo"]:
                    raise Rejeitada("sexo vazio")
                pessoa = (id_lote, pesid, id_, id_veiculo or None, envolvido, estado,
                          idade(r["idade"]), r["sexo"])
        except Rejeitada as e:
            rejeitar(resumo, arq, n, valores, str(e))
            continue
        # O veículo se repete em cada pessoa dele; os atributos são os mesmos (docs/modelagem-origem.md).
        if veiculo:
            veiculos.setdefault(id_veiculo, veiculo)
        if pessoa:
            pessoas[pesid] = pessoa
    copiar(conn, "veiculo", VEICULO_COLS, veiculos.values())
    copiar(conn, "pessoa", PESSOA_COLS, pessoas.values())
    resumo.veiculos, resumo.pessoas = len(veiculos), len(pessoas)

    copiar(conn, "linha_rejeitada", ("id_lote", "dataset", "numero_linha", "linha_bruta", "motivo"),
           ((id_lote, *r) for r in resumo.rejeitadas))
    for a in arqs.values():
        conn.execute(
            "UPDATE lote_arquivo SET linhas_lidas = %s, linhas_rejeitadas = %s WHERE id_lote = %s AND dataset = %s",
            (a.lidas, a.rejeitadas, id_lote, a.dataset))
    conn.execute(
        "UPDATE lote_carga SET status = 'concluido', finalizado_em = now() WHERE id_lote = %s", (id_lote,))
    return resumo


def copiar(conn: psycopg.Connection, tabela: str, colunas: tuple[str, ...], linhas) -> None:
    with conn.cursor().copy(f"COPY {tabela} ({', '.join(colunas)}) FROM STDIN") as copy:
        for linha in linhas:
            copy.write_row(linha)


def ja_carregado(conn: psycopg.Connection, ano: int, arqs: dict[str, Arquivo]) -> bool:
    """O lote vigente do ano já tem exatamente estes arquivos (mesmo SHA-256)?"""
    carregados = dict(conn.execute(
        """SELECT a.dataset, a.sha256 FROM lote_vigente v
           JOIN lote_arquivo a USING (id_lote) WHERE v.ano = %s""", (ano,)).fetchall())
    return carregados == {d: a.sha256 for d, a in arqs.items()}


def main() -> int:
    por_ano = arquivos_do_recorte()
    inicio = time.monotonic()
    falhas = 0
    with psycopg.connect() as conn:
        for ano in YEARS:
            arqs = por_ano[ano]
            if ja_carregado(conn, ano, arqs):
                log(f"  {ano}: já carregado com os mesmos arquivos (SHA-256); nada a fazer")
                continue
            t0 = time.monotonic()
            try:
                with conn.transaction():
                    r = carregar_ano(conn, ano, arqs)
            except Exception as e:  # o ano inteiro é desfeito; registra a tentativa que falhou
                falhas += 1
                log(f"  {ano}: FALHOU ({e.__class__.__name__}: {e})")
                conn.execute(
                    "INSERT INTO lote_carga (ano, status, finalizado_em) VALUES (%s, 'falhou', now())", (ano,))
                conn.commit()
                continue
            conn.commit()
            rej = {d: a.rejeitadas for d, a in arqs.items()}
            log(f"  {ano}: {r.ocorrencias:>6} ocorrências, {r.veiculos:>6} veículos, {r.pessoas:>6} pessoas, "
                f"rejeitadas {rej['ocorrencia']}+{rej['pessoa']}, coordenadas NULL {r.coordenadas_nulas} "
                f"({time.monotonic() - t0:.0f} s)")
    log(f"\ncarga terminada em {time.monotonic() - inicio:.0f} s, {falhas} ano(s) com falha")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
