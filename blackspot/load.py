"""Carga dos arquivos da PRF no esquema da origem (issue #4; dataset completo, ADR 0003).

Uso:
    python -m blackspot.load

Carrega o dataset completo da PRF (BR-Brasil 2007–2016 e BAT 2017 em diante, ver
docs/pergunta-e-recorte.md), um ANO por vez. Cada ano vira um lote (lote_carga),
com os arquivos do ano (lote_arquivo): ocorrência e pessoa sempre, e, no BAT,
também o de todas as causas e tipos. É o insert-only versionado por lote de
docs/modelagem-origem.md.

Os dois sistemas publicam em formatos diferentes (docs/fontes/README.md): o
separador (`,` ou `;`) é detectado pelo cabeçalho de cada arquivo, a data é lida em
qualquer um dos três formatos usados pela PRF, o decimal pode vir com ponto ou com
vírgula, e o BR-Brasil marca ausência com `(null)` e completa textos com espaços.

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

# Dataset completo (docs/pergunta-e-recorte.md): todos os anos do sources.yaml. Todo ano
# tem ocorrência e pessoa; o de todas as causas e tipos só existe no BAT.
DATASETS = ("ocorrencia", "pessoa")
TODAS_CAUSAS = "pessoa_todas_causas"

UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split())
CLASSIFICACOES = {"Sem Vítimas", "Com Vítimas Feridas", "Com Vítimas Fatais", "Ignorado"}
ENVOLVIDOS = {"Condutor", "Passageiro", "Pedestre", "Testemunha", "Cavaleiro",
              "Vítima", "Autor", "Ciclista", "Proprietário de Carga", "Proprietário da CNH"}
SEM_VEICULO = {"Pedestre", "Testemunha", "Cavaleiro"}  # regra do BAT; não vale no BR-Brasil
ESTADOS = {"Ileso", "Lesões Leves", "Lesões Graves", "Óbito", "Não Informado",  # BAT
           "Ferido Leve", "Ferido Grave", "Morto", "Ignorado"}                  # BR-Brasil
USO_SOLO = {"Sim": True, "Urbano": True, "Não": False, "Rural": False}
AUSENTE = {"", "NA", "N/A", "(null)"}
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
PESSOA_COLS = ("id_lote", "pesid", "id", "id_veiculo", "tipo_envolvido", "estado_fisico", "idade", "sexo",
               "nacionalidade", "naturalidade")


class Rejeitada(Exception):
    """Registro que não cabe no esquema; a mensagem é o motivo."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- arquivos -----------------------------------------------------------------


@dataclass
class Arquivo:
    dataset: str
    sistema: str
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


def arquivos_por_ano() -> dict[int, dict[str, Arquivo]]:
    """Todos os arquivos do sources.yaml, por ano."""
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    report = {}
    if (RAW_DIR / REPORT).exists():
        report = {r["key"]: r for r in json.loads((RAW_DIR / REPORT).read_text(encoding="utf-8"))["results"]}
    por_ano: dict[int, dict[str, Arquivo]] = {}
    for e in manifest["files"]:
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
            e["dataset"], e["system"], e["key"], path, sha, path.stat().st_size, modificado)
    faltando = [y for y, arqs in por_ano.items() if not set(DATASETS) <= set(arqs)]
    if faltando:
        raise SystemExit(f"sources.yaml sem ocorrência e pessoa para: {sorted(faltando)}")
    return dict(sorted(por_ano.items()))


def registros(path: Path):
    """(número do registro a partir de 1, dict da linha, valores brutos).

    O separador sai do cabeçalho: o arquivo de pessoa de 2007–2015 usa `,`, e todos os
    outros, `;`. Os valores do dict vêm sem espaços nas pontas (o BR-Brasil completa
    textos com espaços, ex.: 'Ileso       ').
    """
    with zipfile.ZipFile(path) as zf:
        membros = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if len(membros) != 1:
            raise RuntimeError(f"{path.name}: esperado 1 CSV, encontrado(s) {len(membros)}")
        with zf.open(membros[0]) as raw:
            texto = io.TextIOWrapper(raw, encoding=ENCODING, newline="")
            primeira = texto.readline().rstrip("\r\n")
            separador = ";" if primeira.count(";") >= primeira.count(",") else ","
            cabecalho = next(csv.reader([primeira], delimiter=separador))
            for n, valores in enumerate(csv.reader(texto, delimiter=separador), start=1):
                if len(valores) != len(cabecalho):
                    yield n, None, valores
                    continue
                yield n, dict(zip(cabecalho, map(str.strip, valores))), valores


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


def data_hora(data: str, horario: str) -> datetime:
    """data_inversa + horario (hh:mm:ss), em qualquer um dos formatos de data da PRF.

    O formato sai da posição dos separadores, sem tentar um strptime por formato: a
    carga converte 2,2 milhões de datas.
    """
    try:
        if len(data) == 10 and data[4] == "-" and data[7] == "-":          # aaaa-mm-dd
            a, m, d = int(data[:4]), int(data[5:7]), int(data[8:])
        elif len(data) == 10 and data[2] == "/" and data[5] == "/":        # dd/mm/aaaa
            d, m, a = int(data[:2]), int(data[3:5]), int(data[6:])
        elif len(data) == 8 and data[2] == "/" and data[5] == "/":         # dd/mm/aa
            d, m, a = int(data[:2]), int(data[3:5]), 2000 + int(data[6:])
        else:
            raise ValueError
        h, mi, s = horario.split(":")
        return datetime(a, m, d, int(h), int(mi), int(s))
    except ValueError:
        raise Rejeitada(f"data/horário inválidos: {data!r} {horario!r}") from None


def km(valor: str) -> tuple[str | None, bool]:
    """(km com uma casa, anulado?). Ausente fica NULL; negativo vira NULL e é contado."""
    if valor.strip() in AUSENTE:
        return None, False
    n = decimal(valor)
    if n is None:
        raise Rejeitada(f"km inválido: {valor!r}")
    if n < 0:
        return None, True
    return f"{n:.1f}", False


def ano_fabricacao(valor: str, ano: int) -> int | None:
    """0 é sentinela de desconhecido na fonte. Um ano depois do ano do arquivo + 1 (modelo
    do ano seguinte) também é desconhecido: o BR-Brasil tem 9999, 2222, 7788..."""
    if valor.strip() in AUSENTE:
        return None
    n = inteiro(valor, "ano_fabricacao_veiculo")
    if n == 0 or n > ano + 1:
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
    causas: int = 0
    tipos: int = 0
    coordenadas_nulas: int = 0
    km_nulos: int = 0
    rejeitadas: list[tuple] = field(default_factory=list)


def rejeitar(resumo: Resumo, arq: Arquivo, n: int, valores: list[str], motivo: str) -> None:
    arq.rejeitadas += 1
    resumo.rejeitadas.append((arq.dataset, n, linha_bruta(valores), motivo))


def converter_ocorrencia(r: dict, id_lote: int, ano: int, causas: Dominio, tipos: Dominio, resumo: Resumo) -> tuple:
    id_ = inteiro(r["id"], "id")
    if id_ <= 0:
        raise Rejeitada(f"id não positivo: {r['id']!r}")
    ocorrido_em = data_hora(r["data_inversa"], r["horario"])
    if ocorrido_em.year != ano:
        raise Rejeitada(f"data fora do ano do arquivo: {r['data_inversa']}")
    # uf, br e km: ausentes em poucas ocorrências do BR-Brasil, que entram sem trecho.
    uf = ausente(r["uf"])
    if uf is not None and uf not in UFS:
        raise Rejeitada(f"uf inválida: {uf!r}")
    br = None if ausente(r["br"]) is None else inteiro(r["br"], "br")
    if br is not None and not 0 <= br <= 999:
        raise Rejeitada(f"br fora de 0–999: {br}")
    km_, anulado = km(r["km"])
    resumo.km_nulos += anulado
    if not r["municipio"]:
        raise Rejeitada("municipio vazio")
    # Coordenadas só existem no BAT (2017+).
    lat, lon, anulada = None, None, False
    if "latitude" in r:
        lat, lon, anulada = coordenadas(r["latitude"], r["longitude"])
    resumo.coordenadas_nulas += anulada
    classificacao = ausente(r["classificacao_acidente"])
    if classificacao is not None and classificacao not in CLASSIFICACOES:
        raise Rejeitada(f"classificacao_acidente inválida: {classificacao!r}")
    uso_solo = ausente(r["uso_solo"])
    if uso_solo is not None and uso_solo not in USO_SOLO:
        raise Rejeitada(f"uso_solo inválido: {uso_solo!r}")
    tracado = ausente(r["tracado_via"])
    tracado = [t for t in tracado.split(";") if t] if tracado else None
    n = {c: inteiro(r[c], c) for c in CONTAGENS}
    if any(v < 0 for v in n.values()):
        raise Rejeitada("contagem negativa")
    if n["feridos"] != n["feridos_leves"] + n["feridos_graves"]:
        raise Rejeitada("feridos diferente de feridos_leves + feridos_graves")
    causa, tipo = ausente(r["causa_acidente"]), ausente(r["tipo_acidente"])
    return (
        id_lote, id_, ocorrido_em, uf, br, km_, r["municipio"], lat, lon,
        causas.id(causa) if causa else None, tipos.id(tipo) if tipo else None, classificacao,
        ausente(r["fase_dia"]), ausente(r["sentido_via"]), ausente(r["condicao_metereologica"]),
        ausente(r["tipo_pista"]), tracado,
        None if uso_solo is None else USO_SOLO[uso_solo], *(n[c] for c in CONTAGENS),
        ausente(r.get("regional", "")), ausente(r.get("delegacia", "")), ausente(r.get("uop", "")),
    )


def id_veiculo(valor: str) -> int:
    """0 = sem veículo. O BAT usa 0; o BR-Brasil usa (null) ou NA."""
    return 0 if valor.strip() in AUSENTE else inteiro(valor, "id_veiculo")


def carregar_ano(conn: psycopg.Connection, ano: int, arqs: dict[str, Arquivo]) -> Resumo:
    """Carrega um ano inteiro numa transação. Se algo falhar, nada do ano fica gravado."""
    resumo = Resumo()
    bat = arqs["ocorrencia"].sistema == "bat"
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
            if r is None:
                raise Rejeitada("número de colunas diferente do cabeçalho")
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
            if r is None:
                raise Rejeitada("número de colunas diferente do cabeçalho")
            id_ = inteiro(r["id"], "id")
            pesid = inteiro(r["pesid"], "pesid")
            veic = id_veiculo(r["id_veiculo"])
            if pesid == 0 and veic == 0:
                raise Rejeitada("pesid = 0 e id_veiculo = 0: nem pessoa nem veículo")
            if id_ not in ids:
                raise Rejeitada(f"sem ocorrência carregada: id {id_}")
            veiculo = None
            if veic != 0:
                veiculo = (id_lote, id_, veic, ausente(r["tipo_veiculo"]), ausente(r["marca"]),
                           ano_fabricacao(r["ano_fabricacao_veiculo"], ano))
                if veic in veiculos and veiculos[veic][1] != id_:
                    raise Rejeitada(f"id_veiculo {veic} em duas ocorrências")
            pessoa = None
            if pesid != 0:
                if pesid in pessoas:
                    raise Rejeitada(f"pesid repetido: {pesid}")
                envolvido, estado = r["tipo_envolvido"], ausente(r["estado_fisico"])
                if envolvido not in ENVOLVIDOS:
                    raise Rejeitada(f"tipo_envolvido inválido: {envolvido!r}")
                if estado is not None and estado not in ESTADOS:
                    raise Rejeitada(f"estado_fisico inválido: {estado!r}")
                # Só no BAT a ausência de veículo corresponde exatamente ao tipo de envolvido.
                if bat and (veic == 0) != (envolvido in SEM_VEICULO):
                    raise Rejeitada(f"{envolvido} com id_veiculo = {veic}")
                pessoa = (id_lote, pesid, id_, veic or None, envolvido, estado, idade(r["idade"]),
                          ausente(r["sexo"]), ausente(r.get("nacionalidade", "")),
                          ausente(r.get("naturalidade", "")))
        except Rejeitada as e:
            rejeitar(resumo, arq, n, valores, str(e))
            continue
        # O veículo se repete em cada pessoa dele; os atributos são os mesmos (docs/modelagem-origem.md).
        if veiculo:
            veiculos.setdefault(veic, veiculo)
        if pessoa:
            pessoas[pesid] = pessoa
    copiar(conn, "veiculo", VEICULO_COLS, veiculos.values())
    copiar(conn, "pessoa", PESSOA_COLS, pessoas.values())
    resumo.veiculos, resumo.pessoas = len(veiculos), len(pessoas)

    # Todas as causas e tipos (só BAT). Uma linha por pessoa x causa x tipo; o que é novo
    # está no nível da ocorrência (V0011), então cada causa e cada tipo entram uma vez.
    if TODAS_CAUSAS in arqs:
        arq = arqs[TODAS_CAUSAS]
        oc_causas: dict[tuple[int, int], bool] = {}
        oc_tipos: dict[tuple[int, int], int] = {}
        principal: dict[int, int] = {}
        for n, r, valores in registros(arq.path):
            arq.lidas += 1
            try:
                if r is None:
                    raise Rejeitada("número de colunas diferente do cabeçalho")
                id_ = inteiro(r["id"], "id")
                if id_ not in ids:
                    raise Rejeitada(f"sem ocorrência carregada: id {id_}")
                causa, tipo = ausente(r["causa_acidente"]), ausente(r["tipo_acidente"])
                if causa is None:
                    raise Rejeitada("causa_acidente vazia")
                if r["causa_principal"] not in ("Sim", "Não"):
                    raise Rejeitada(f"causa_principal inválida: {r['causa_principal']!r}")
                eh_principal = r["causa_principal"] == "Sim"
                id_causa = causas.id(causa)
                if oc_causas.get((id_, id_causa), eh_principal) != eh_principal:
                    raise Rejeitada(f"causa {causa!r} principal e não principal no id {id_}")
                if eh_principal and principal.get(id_, id_causa) != id_causa:
                    raise Rejeitada(f"duas causas principais no id {id_}")
                id_tipo = None
                if tipo is not None:
                    ordem = inteiro(r["ordem_tipo_acidente"], "ordem_tipo_acidente")
                    if ordem < 1:
                        raise Rejeitada(f"ordem_tipo_acidente inválida: {ordem}")
                    id_tipo = tipos.id(tipo)
                    if oc_tipos.get((id_, ordem), id_tipo) != id_tipo:
                        raise Rejeitada(f"dois tipos na ordem {ordem} do id {id_}")
            except Rejeitada as e:
                rejeitar(resumo, arq, n, valores, str(e))
                continue
            oc_causas[(id_, id_causa)] = eh_principal
            if eh_principal:
                principal[id_] = id_causa
            if id_tipo is not None:
                oc_tipos[(id_, ordem)] = id_tipo
        copiar(conn, "ocorrencia_causa", ("id_lote", "id", "id_causa", "causa_principal"),
               ((id_lote, i, c, p) for (i, c), p in oc_causas.items()))
        copiar(conn, "ocorrencia_tipo", ("id_lote", "id", "ordem", "id_tipo"),
               ((id_lote, i, o, t) for (i, o), t in oc_tipos.items()))
        resumo.causas, resumo.tipos = len(oc_causas), len(oc_tipos)

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
    por_ano = arquivos_por_ano()
    inicio = time.monotonic()
    falhas = 0
    with psycopg.connect() as conn:
        for ano, arqs in por_ano.items():
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
            rej = "+".join(str(a.rejeitadas) for a in arqs.values())
            log(f"  {ano} ({arqs['ocorrencia'].sistema}): {r.ocorrencias:>6} ocorrências, "
                f"{r.veiculos:>6} veículos, {r.pessoas:>6} pessoas, {r.causas:>6} causas, {r.tipos:>6} tipos, "
                f"rejeitadas {rej}, coordenadas NULL {r.coordenadas_nulas}, km NULL {r.km_nulos} "
                f"({time.monotonic() - t0:.0f} s)")
    log(f"\ncarga terminada em {time.monotonic() - inicio:.0f} s, {falhas} ano(s) com falha")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
