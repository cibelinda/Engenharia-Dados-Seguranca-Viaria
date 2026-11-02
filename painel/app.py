"""Painel da E3 (issue #45): responde à pergunta de gestão do BlackSpot.

Lê só as duas tabelas finais do dbt, no schema analitico_marts:
- mart_risco_trecho_ano (issue #43): acidentes graves por trecho de 10 km e ano;
- mart_risco_municipio_ano (issue #42): acidentes graves por município e ano.

Se uma delas ainda não existir (o `dbt build` não rodou), a seção mostra um aviso.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import psycopg
import streamlit as st

SCHEMA = "analitico_marts"
TOP_N = 50  # o "top" usado para medir se um trecho se mantém entre os mais graves

st.set_page_config(page_title="BlackSpot", layout="wide")


@st.cache_data(ttl=300)
def consultar(sql: str, params: tuple = ()) -> pd.DataFrame:
    with psycopg.connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        colunas = [c.name for c in cur.description]
        linhas = [[float(v) if isinstance(v, Decimal) else v for v in linha] for linha in cur.fetchall()]
        return pd.DataFrame(linhas, columns=colunas)


@st.cache_data(ttl=300)
def colunas_da_tabela(tabela: str) -> list[str]:
    df = consultar(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
        (SCHEMA, tabela))
    return df["column_name"].tolist()


st.title("BlackSpot: onde estão os pontos negros das rodovias federais")
st.markdown(
    "> **Pergunta de gestão:** quais trechos de 10 km das rodovias federais concentraram mais "
    "acidentes com mortos ou feridos graves, e esses trechos se mantêm de um ano para o outro?")
st.caption("Dados abertos da PRF (2007–2026) e do IBGE. Acidente grave = com morto ou ferido grave.")

aba_trechos, aba_municipios = st.tabs(["Trechos mais graves", "Municípios mais perigosos"])

# --- Trechos ----------------------------------------------------------------------
with aba_trechos:
    esperadas = {"br", "uf", "km_inicio", "ano", "graves"}
    colunas = set(colunas_da_tabela("mart_risco_trecho_ano"))
    if not colunas:
        st.info("A tabela de trechos (`mart_risco_trecho_ano`, issue #43) ainda não foi criada. "
                "Rode `docker compose run --rm dbt build` depois que ela entrar na `main`.")
    elif not esperadas <= colunas:
        st.warning(f"A tabela de trechos não tem as colunas esperadas {sorted(esperadas)}; "
                   f"tem {sorted(colunas)}.")
    else:
        anos = consultar(f"SELECT DISTINCT ano FROM {SCHEMA}.mart_risco_trecho_ano ORDER BY ano")["ano"].tolist()
        ano = st.selectbox("Ano", anos, index=len(anos) - 2 if len(anos) > 1 else 0, key="ano_trecho")

        st.subheader(f"Os 20 trechos com mais acidentes graves em {ano}")
        top = consultar(
            f"""SELECT br, uf, km_inicio, graves FROM {SCHEMA}.mart_risco_trecho_ano
                WHERE ano = %s AND br <> 0 ORDER BY graves DESC LIMIT 20""", (ano,))
        top["trecho"] = ("BR-" + top["br"].astype(int).astype(str).str.zfill(3) + "/" + top["uf"] + " km "
                         + top["km_inicio"].astype(int).astype(str) + "–"
                         + (top["km_inicio"].astype(int) + 10).astype(str))
        st.bar_chart(top.set_index("trecho")["graves"], horizontal=True)

        st.subheader(f"Os trechos que se mantêm: em quantos anos ficaram entre os {TOP_N} mais graves")
        persistencia = consultar(
            f"""WITH ranking AS (
                    SELECT br, uf, km_inicio, ano, graves,
                           rank() OVER (PARTITION BY ano ORDER BY graves DESC) AS posicao
                    FROM {SCHEMA}.mart_risco_trecho_ano WHERE br <> 0)
                SELECT br, uf, km_inicio, count(*) AS anos_no_top, sum(graves) AS graves_no_total
                FROM ranking WHERE posicao <= %s
                GROUP BY 1, 2, 3 ORDER BY anos_no_top DESC, graves_no_total DESC LIMIT 20""", (TOP_N,))
        persistencia["trecho"] = ("BR-" + persistencia["br"].astype(int).astype(str).str.zfill(3) + "/" + persistencia["uf"]
                                  + " km " + persistencia["km_inicio"].astype(int).astype(str))
        st.dataframe(persistencia[["trecho", "anos_no_top", "graves_no_total"]],
                     hide_index=True, width="stretch")
        st.caption("Um trecho que aparece no topo em muitos anos é um ponto negro de verdade, "
                   "e não azar de um ano isolado.")

# --- Municípios -------------------------------------------------------------------
with aba_municipios:
    if not colunas_da_tabela("mart_risco_municipio_ano"):
        st.info("A tabela de municípios (`mart_risco_municipio_ano`, issue #42) ainda não foi "
                "criada. Rode `docker compose run --rm dbt build`.")
    else:
        anos = consultar(f"SELECT DISTINCT ano FROM {SCHEMA}.mart_risco_municipio_ano ORDER BY ano")["ano"].tolist()
        ano = st.selectbox("Ano", anos, index=len(anos) - 2 if len(anos) > 1 else 0, key="ano_mun")
        minimo = st.slider("Mínimo de acidentes graves no ano (evita distorção em cidade pequena)",
                           1, 50, 10)

        st.subheader(f"Municípios com mais acidentes graves por 100 mil habitantes em {ano}")
        taxa = consultar(
            f"""SELECT nome || ' (' || uf || ')' AS municipio, graves, populacao, graves_por_100_mil
                FROM {SCHEMA}.mart_risco_municipio_ano
                WHERE ano = %s AND graves >= %s
                ORDER BY graves_por_100_mil DESC LIMIT 20""", (ano, minimo))
        st.bar_chart(taxa.set_index("municipio")["graves_por_100_mil"], horizontal=True)
        st.dataframe(taxa, hide_index=True, width="stretch")

        st.subheader(f"Municípios com mais acidentes graves em número absoluto em {ano}")
        absoluto = consultar(
            f"""SELECT nome || ' (' || uf || ')' AS municipio, graves, mortos
                FROM {SCHEMA}.mart_risco_municipio_ano
                WHERE ano = %s ORDER BY graves DESC LIMIT 20""", (ano,))
        st.dataframe(absoluto, hide_index=True, width="stretch")
        st.caption("A população de 2007 e 2023 é a do ano mais próximo: o IBGE não publica estimativa "
                   "para esses anos.")
