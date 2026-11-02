"""Grafo agendado do BlackSpot no Dagster (E3, issue #44). Detalhes em docs/e3/orquestracao.md.

    arquivos_prf ──► origem_prf ──┬──► lake_lote
                                  └──► camada_analitica ◄── base_ibge
                                       (dbt build)

- `esteira`: o grafo inteiro, todo dia às 03:00 (horário de Brasília).
- `verificar_freshness`: só a verificação de freshness e SLA, de hora em hora.
- `reprocessar_ano`: backfill, particionado por ano. Recarrega o ano mesmo sem mudança nos
  arquivos e reconstrói o que depende dele.

Cada etapa roda o mesmo comando do serviço correspondente no compose (o contrato da E3), como
um processo à parte, e tenta de novo até 3 vezes se falhar, esperando 30 s, 90 s e 210 s
(backoff exponencial do Dagster: 30 × (2ⁿ − 1)).
"""

# Sem `from __future__ import annotations`: o Dagster lê as anotações (Config) em tempo de execução.
import os
import subprocess
from collections import deque
from datetime import date

import dagster as dg
import yaml

from orquestracao import freshness

APP = "/app"
DBT_DIR = "/app/dbt"

NOVAS_TENTATIVAS = dg.RetryPolicy(max_retries=3, delay=30, backoff=dg.Backoff.EXPONENTIAL)


def rodar(context, comando: list[str], cwd: str = APP) -> list[str]:
    """Roda o comando, manda cada linha da saída para o log do Dagster e falha se o código
    de saída não for 0. Devolve as últimas linhas, para o resumo da etapa."""
    context.log.info("$ " + " ".join(comando))
    ultimas: deque[str] = deque(maxlen=40)
    with subprocess.Popen(comando, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1) as proc:
        for linha in proc.stdout:
            linha = linha.rstrip()
            if linha:
                ultimas.append(linha)
                context.log.info(linha)
    if proc.returncode != 0:
        raise dg.Failure(
            description=f"`{' '.join(comando)}` saiu com código {proc.returncode}",
            metadata={"últimas linhas": dg.MetadataValue.md("```\n" + "\n".join(ultimas) + "\n```")})
    return list(ultimas)


def resumo(linhas: list[str], inicio: str) -> str:
    """A última linha da saída com `inicio` (o resumo que cada script imprime), a partir dele.
    O dbt põe o horário antes do texto."""
    return next((l[l.index(inicio):].strip() for l in reversed(linhas) if inicio in l), "")


def dbt_build(context) -> dict:
    linhas = rodar(context, ["dbt", "build", "--no-use-colors"], cwd=DBT_DIR)
    return {"dbt": dg.MetadataValue.text(resumo(linhas, "Done."))}


# --- o grafo diário -------------------------------------------------------------------


class ArquivosPrfConfig(dg.Config):
    # A PRF regrava os arquivos no mesmo endereço. O download normal só baixa o que falta,
    # então os anos que ainda mudam são baixados de novo a cada execução; a carga decide pelo
    # SHA-256 se algo mudou. Vazio = ano corrente e o anterior.
    anos_rebaixar: list[int] = []


@dg.asset(group_name="esteira", kinds={"python"}, retry_policy=NOVAS_TENTATIVAS,
          description="Arquivos da PRF no volume rawdata (serviço `download`).")
def arquivos_prf(context: dg.AssetExecutionContext, config: ArquivosPrfConfig) -> dg.MaterializeResult:
    anos = config.anos_rebaixar or [date.today().year, date.today().year - 1]
    comando = ["python", "-m", "blackspot.download", "--force"]
    for ano in anos:
        comando += ["--year", str(ano)]
    rodar(context, comando)
    linhas = rodar(context, ["python", "-m", "blackspot.download"])
    return dg.MaterializeResult(metadata={
        "anos baixados de novo": dg.MetadataValue.text(", ".join(map(str, anos))),
        "download": dg.MetadataValue.text(resumo(linhas, "resumo:")),
    })


@dg.asset(group_name="esteira", kinds={"python", "postgres"}, deps=[arquivos_prf],
          retry_policy=NOVAS_TENTATIVAS,
          description="Origem no PostgreSQL, versionada por lote (serviço `load`). "
                      "Só carrega de novo o ano cujo arquivo mudou.")
def origem_prf(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    linhas = rodar(context, ["python", "-m", "blackspot.load"])
    return dg.MaterializeResult(metadata={
        "carga": dg.MetadataValue.text(resumo(linhas, "carga terminada")),
        "anos carregados": len([l for l in linhas if "ocorrências," in l]),
    })


@dg.asset(group_name="esteira", kinds={"python", "delta"}, deps=[origem_prf],
          retry_policy=NOVAS_TENTATIVAS,
          description="Camada em Delta da E2 (serviço `ingestao-lote`). Só reescreve o ano "
                      "cujo lote vigente mudou.")
def lake_lote(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    linhas = rodar(context, ["python", "-m", "blackspot.ingestao_lote"])
    return dg.MaterializeResult(metadata={
        "lote": dg.MetadataValue.text(resumo(linhas, "ingestão em lote terminada"))})


@dg.asset(group_name="esteira", kinds={"python", "postgres"}, retry_policy=NOVAS_TENTATIVAS,
          description="Municípios, população e malha do IBGE no schema `ibge` "
                      "(serviço `ingestao-ibge`).")
def base_ibge(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    linhas = rodar(context, ["python", "-m", "blackspot.ibge.ingestao"])
    return dg.MaterializeResult(metadata={
        "ibge": dg.MetadataValue.text(resumo(linhas, "ingestão do IBGE terminada"))})


@dg.asset(group_name="esteira", kinds={"dbt", "postgres"}, deps=[origem_prf, base_ibge],
          retry_policy=NOVAS_TENTATIVAS,
          description="Modelos e testes do dbt (`dbt build`): staging, intermediate e as "
                      "tabelas de consumo em analitico_marts.")
def camada_analitica(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    return dg.MaterializeResult(metadata=dbt_build(context))


# --- freshness e SLA --------------------------------------------------------------------


@dg.asset_check(asset=camada_analitica, blocking=False,
                description=f"Idade das tabelas de consumo (horas desde o último dbt build "
                            f"sem erro). SLA: até {freshness.SLA_HORAS:g} h.")
def freshness_sla(context: dg.AssetCheckExecutionContext) -> dg.AssetCheckResult:
    def ultimo(chave: str):
        evento = context.instance.get_latest_materialization_event(dg.AssetKey(chave))
        return freshness.de_timestamp(evento.timestamp if evento else None)

    m = freshness.medir(ultimo("camada_analitica"), ultimo("arquivos_prf"))
    metadata = {
        "idade_h": m.idade_h if m.idade_h is not None else -1.0,
        "sla_h": freshness.SLA_HORAS,
        "carga_pendente_h": m.carga_pendente_h,
        "ultima_verificacao_prf_h": dg.MetadataValue.float(
            m.horas(m.ultima_verificacao_prf, m.agora) if m.ultima_verificacao_prf else -1.0),
        "ultimo_build": dg.MetadataValue.text(str(m.ultimo_build or "nunca")),
        "ultima_carga": dg.MetadataValue.text(str(m.ultima_carga or "nunca")),
        "dado_mais_recente": dg.MetadataValue.text(str(m.dado_mais_recente or "—")),
        "tabelas": dg.MetadataValue.json(
            {t: ("não existe" if n is None else f"{n} linhas") for t, n in m.tabelas.items()}),
    }
    if not m.dentro_do_sla:
        context.log.error(f"fora do SLA: idade {m.idade_h} h > {freshness.SLA_HORAS:g} h")
        return dg.AssetCheckResult(passed=False, severity=dg.AssetCheckSeverity.ERROR, metadata=metadata)
    if m.faltando:
        # Dentro do prazo, mas alguma tabela de consumo ainda não existe (a parte que a cria
        # não entrou na main, ou o modelo foi removido).
        context.log.warning(f"tabela(s) de consumo ausente(s): {', '.join(m.faltando)}")
        return dg.AssetCheckResult(passed=False, severity=dg.AssetCheckSeverity.WARN, metadata=metadata)
    return dg.AssetCheckResult(passed=True, metadata=metadata)


# --- backfill: reprocessar um ano ------------------------------------------------------


def anos_do_manifesto() -> list[str]:
    manifesto = yaml.safe_load(open(os.path.join(APP, "sources.yaml"), encoding="utf-8"))
    return [str(a) for a in sorted({e["year"] for e in manifesto["files"]})]


ANOS = dg.StaticPartitionsDefinition(anos_do_manifesto())


class ReprocessarConfig(dg.Config):
    # Baixar de novo os arquivos do ano antes de recarregar (senão usa os que já estão no volume).
    rebaixar: bool = False


@dg.op(retry_policy=NOVAS_TENTATIVAS)
def recarregar_ano(context: dg.OpExecutionContext, config: ReprocessarConfig) -> str:
    ano = context.partition_key
    if config.rebaixar:
        rodar(context, ["python", "-m", "blackspot.download", "--force", "--year", ano])
    rodar(context, ["python", "-m", "orquestracao.recarregar", ano])
    context.log_event(dg.AssetMaterialization(
        asset_key="origem_prf", description=f"backfill: {ano} recarregado"))
    return ano


@dg.op(retry_policy=NOVAS_TENTATIVAS)
def atualizar_lote(context: dg.OpExecutionContext, ano: str) -> str:
    linhas = rodar(context, ["python", "-m", "blackspot.ingestao_lote"])
    context.log_event(dg.AssetMaterialization(
        asset_key="lake_lote", description=f"backfill de {ano}: {resumo(linhas, 'ingestão em lote terminada')}"))
    return ano


@dg.op(retry_policy=NOVAS_TENTATIVAS)
def reconstruir_camada(context: dg.OpExecutionContext, ano: str) -> None:
    metadata = dbt_build(context)
    context.log_event(dg.AssetMaterialization(
        asset_key="camada_analitica", description=f"backfill de {ano}", metadata=metadata))


@dg.job(partitions_def=ANOS, description="Backfill: recarrega o ano da partição mesmo sem "
        "mudança nos arquivos (lote novo), reescreve a partição do ano na camada Delta e "
        "reconstrói a camada analítica.")
def reprocessar_ano():
    reconstruir_camada(atualizar_lote(recarregar_ano()))


# --- jobs e agendamentos ----------------------------------------------------------------

esteira = dg.define_asset_job(
    "esteira", selection=dg.AssetSelection.groups("esteira"),
    description="O grafo inteiro: PRF -> origem -> (Delta, dbt), IBGE -> dbt, e o freshness.")

verificar_freshness = dg.define_asset_job(
    "verificar_freshness", selection=dg.AssetSelection.checks(freshness_sla),
    description="Só a verificação de freshness e SLA, sem reconstruir nada.")

defs = dg.Definitions(
    assets=[arquivos_prf, origem_prf, lake_lote, base_ibge, camada_analitica],
    asset_checks=[freshness_sla],
    jobs=[esteira, verificar_freshness, reprocessar_ano],
    schedules=[
        dg.ScheduleDefinition(job=esteira, cron_schedule="0 3 * * *",
                              execution_timezone="America/Sao_Paulo",
                              default_status=dg.DefaultScheduleStatus.RUNNING),
        dg.ScheduleDefinition(job=verificar_freshness, cron_schedule="15 * * * *",
                              execution_timezone="America/Sao_Paulo",
                              default_status=dg.DefaultScheduleStatus.RUNNING),
    ],
)
