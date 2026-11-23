"""Medição do ADR 0006: como os trechos críticos chegam à PRF de cada UF.

Uso, dentro do container da orquestração, com o banco carregado e o dbt construído:
    docker compose run --rm -v ./orquestracao/medicao:/app/orquestracao/medicao \
        orquestracao python -m orquestracao.medicao.medicao_adr0006

Três opções, com o nosso volume (140 trechos críticos, 21 UFs):

A. CSV agendado, empurrado (a opção nula): o Dagster gera um CSV por UF numa pasta que a PRF
   lê. Mede o tempo de gerar e publicar tudo, o tamanho e o tempo de o consumidor abrir o
   arquivo da UF dele.
B. Tabela no banco, puxada: a aplicação da PRF consulta o banco a cada uso, com a mesma
   consulta do ETL filtrada pela UF. Mede a consulta abrindo conexão nova (como um script que
   roda e termina) e reaproveitando a conexão (como uma aplicação que fica no ar).
C. API, puxada: um serviço HTTP na frente do banco devolve o JSON da UF. Mede a resposta e a
   memória do serviço. O servidor é o da biblioteca padrão do Python, então o número é o piso
   do custo de uma API, e não o de um framework.

E o que acontece com o destino fora do ar:
- em A, a pasta de destino sem permissão de escrita: o tempo até o ETL falhar e se a geração
  anterior continua legível;
- em B e C, o banco fora do alcance: o tempo até o consumidor desistir (PGCONNECT_TIMEOUT).

Os tempos são de dentro da mesma rede Docker que o banco: o consumidor real estaria mais longe,
e as latências de B e C seriam maiores. Grava o resultado em JSON ao lado deste script.
"""

from __future__ import annotations

import csv
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from orquestracao import etl_reverso

SAIDA = Path(__file__).with_name("medicao_adr0006.json")
RODADAS = int(os.environ.get("RODADAS", "30"))
UF = os.environ.get("UF_MEDIDA", "MG")
PORTA_API = 8765

CONSULTA_UF = etl_reverso.CONSULTA.replace("where p.anos_no_top_50 >= 1",
                                           "where p.anos_no_top_50 >= 1 and p.uf = %s")


def ms(segundos: float) -> float:
    return round(segundos * 1000, 2)


def resumo(amostras: list[float]) -> dict:
    amostras = sorted(amostras)
    return {"mediana_ms": ms(statistics.median(amostras)),
            "p95_ms": ms(amostras[int(0.95 * (len(amostras) - 1))]),
            "min_ms": ms(amostras[0]), "rodadas": len(amostras)}


def cronometrar(funcao, rodadas: int = RODADAS) -> list[float]:
    tempos = []
    for _ in range(rodadas):
        t0 = time.perf_counter()
        funcao()
        tempos.append(time.perf_counter() - t0)
    return tempos


# --- A: CSV agendado -------------------------------------------------------------------


def medir_csv() -> dict:
    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta)
        contador = iter(range(10**6))
        inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def gerar_e_publicar():
            # Uma geração nova a cada rodada (um segundo diferente no nome), como se o dado
            # tivesse mudado: é o custo da execução que de fato escreve.
            arquivos = etl_reverso.montar(etl_reverso.consultar())
            gerado = inicio + timedelta(seconds=next(contador))
            for nome in list(arquivos):
                arquivos[nome] += b" "  # força hash diferente, senão a geração é mantida
            etl_reverso.publicar(arquivos, destino, gerado)

        geracao = cronometrar(gerar_e_publicar, rodadas=min(RODADAS, 20))
        so_consulta = cronometrar(etl_reverso.consultar)
        sem_mudanca_arquivos = etl_reverso.montar(etl_reverso.consultar())
        etl_reverso.publicar(sem_mudanca_arquivos, destino, datetime.now(timezone.utc))
        sem_mudanca = cronometrar(lambda: etl_reverso.publicar(
            etl_reverso.montar(etl_reverso.consultar()), destino, datetime.now(timezone.utc)))

        atual = destino / "atual"
        arquivo_uf = atual / f"trechos_criticos_{UF}.csv"

        def consumidor_le():
            with open(arquivo_uf, encoding="utf-8-sig", newline="") as f:
                return list(csv.DictReader(f, delimiter=";"))

        leitura = cronometrar(consumidor_le, rodadas=RODADAS * 10)
        tamanhos = {p.name: p.stat().st_size for p in atual.iterdir()}
        linhas_uf = len(consumidor_le())

        # Destino fora do ar: tira a permissão de escrita da pasta e roda de novo.
        os.chmod(destino, 0o555)
        try:
            t0 = time.perf_counter()
            try:
                etl_reverso.publicar(etl_reverso.montar(etl_reverso.consultar()), destino,
                                     datetime.now(timezone.utc))
                falhou, erro = False, ""
            except RuntimeError as e:
                falhou, erro = True, str(e)
            ate_falhar = time.perf_counter() - t0
            anterior_legivel = len(consumidor_le()) == linhas_uf
        finally:
            os.chmod(destino, 0o755)

    return {
        "gerar_e_publicar_21_ufs": resumo(geracao),
        "so_a_consulta": resumo(so_consulta),
        "execucao_sem_mudanca": resumo(sem_mudanca),
        "consumidor_abre_csv_da_uf": resumo(leitura),
        "linhas_csv_da_uf": linhas_uf,
        "bytes_total_geracao": sum(tamanhos.values()),
        "bytes_csv_da_uf": tamanhos[f"trechos_criticos_{UF}.csv"],
        "arquivos_por_geracao": len(tamanhos),
        "destino_fora_do_ar": {"etl_falhou": falhou, "erro": erro, "ms_ate_falhar": ms(ate_falhar),
                               "geracao_anterior_continua_legivel": anterior_legivel},
    }


# --- B: tabela no banco, o consumidor puxa ---------------------------------------------


def medir_tabela() -> dict:
    def conexao_nova():
        with psycopg.connect() as conn:
            return conn.execute(CONSULTA_UF, (UF,)).fetchall()

    with psycopg.connect() as conn:
        def conexao_aberta():
            return conn.execute(CONSULTA_UF, (UF,)).fetchall()
        aberta = cronometrar(conexao_aberta)
        linhas = len(conexao_aberta())
    nova = cronometrar(conexao_nova)
    return {"consulta_da_uf_conexao_nova": resumo(nova),
            "consulta_da_uf_conexao_aberta": resumo(aberta),
            "linhas_da_uf": linhas,
            "banco_fora_do_ar": banco_fora_do_ar()}


def banco_fora_do_ar() -> dict:
    """O consumidor tenta o banco num endereço que não responde (porta fechada num IP que não
    existe na rede), com o timeout de conexão de 3 s."""
    env = {**os.environ, "PGHOST": "10.255.255.1", "PGCONNECT_TIMEOUT": "3"}
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "-c", "import psycopg; psycopg.connect()"],
                       env=env, capture_output=True, text=True)
    return {"consumidor_recebe_erro": r.returncode != 0, "ms_ate_desistir": ms(time.perf_counter() - t0),
            "o_que_o_consumidor_tem": "nada: sem banco, não há lista"}


# --- C: API, o consumidor puxa ---------------------------------------------------------

SERVIDOR = r'''
import json, sys, psycopg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
consulta = sys.argv[2]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        uf = parse_qs(urlparse(self.path).query).get("uf", [""])[0]
        with psycopg.connect() as conn:
            cur = conn.execute(consulta, (uf,))
            nomes = [c.name for c in cur.description]
            corpo = json.dumps([dict(zip(nomes, l)) for l in cur.fetchall()], default=str).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo))); self.end_headers(); self.wfile.write(corpo)
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
'''


def rss_kib(pid: int) -> int:
    for linha in Path(f"/proc/{pid}/status").read_text().splitlines():
        if linha.startswith("VmRSS:"):
            return int(linha.split()[1])
    return -1


def medir_api() -> dict:
    proc = subprocess.Popen([sys.executable, "-c", SERVIDOR, str(PORTA_API), CONSULTA_UF])
    url = f"http://127.0.0.1:{PORTA_API}/trechos?uf={UF}"
    try:
        t0 = time.perf_counter()
        while True:
            try:
                urllib.request.urlopen(url, timeout=2).read()
                break
            except OSError:
                if time.perf_counter() - t0 > 20:
                    raise
                time.sleep(0.1)
        subida = time.perf_counter() - t0
        requisicao = cronometrar(lambda: urllib.request.urlopen(url, timeout=5).read())
        corpo = urllib.request.urlopen(url, timeout=5).read()
        memoria = rss_kib(proc.pid)
    finally:
        proc.terminate()
        proc.wait()
    return {"requisicao_da_uf": resumo(requisicao), "bytes_resposta": len(corpo),
            "linhas_da_uf": len(json.loads(corpo)), "ms_ate_responder_ao_subir": ms(subida),
            "memoria_servico_kib": memoria,
            "banco_fora_do_ar": "igual a B: a API depende do banco a cada requisição"}


def main() -> int:
    resultado = {
        "medido_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "uf_medida": UF,
        "rodadas": RODADAS,
        "trechos_criticos": len(etl_reverso.consultar()),
        "A_csv_agendado": medir_csv(),
        "B_tabela_no_banco": medir_tabela(),
        "C_api": medir_api(),
        "memoria_do_processo_de_medicao_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
