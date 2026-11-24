"""Painel da E3 (issue #45): responde à pergunta de gestão do BlackSpot.

Lê só tabelas de consumo do dbt, no schema analitico_marts, e não calcula métrica nenhuma
por conta própria (contrato da E4, docs/e4/README.md):
- mart_risco_trecho_ano (issue #43): acidentes graves por trecho de 10 km e ano;
- mart_persistencia_trecho (issue #53): em quantos anos cada trecho ficou entre os 50 mais graves;
- mart_risco_municipio_ano (issue #42): acidentes graves por município e ano;
- mapa_trecho, mapa_acidente_grave e mapa_municipio (issue #57): onde ficam no mapa;
- mart_perfil_trecho, mart_perfil_comparacao (issue #58), dim_trecho_relevo e
  mart_relevo_comparacao (issue #59): a ficha do trecho, se já existirem.

Conecta com o papel painel_leitor, que só lê analitico_marts (issue #52, docs/e4/acesso.md).
Se uma tabela ainda não existir (o `dbt build` não rodou), a seção mostra um aviso.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pandas as pd
import psycopg
import pydeck as pdk
import streamlit as st

SCHEMA = "analitico_marts"

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

aba_mapa, aba_trechos, aba_municipios = st.tabs(
    ["Mapa dos pontos negros", "Trechos mais graves", "Municípios mais perigosos"])


def existe(tabela: str) -> bool:
    return bool(colunas_da_tabela(tabela))


# Cores do mapa. Só apresentação: os números vêm prontos das tabelas do dbt.
VERMELHO = [200, 30, 30]
ESCALA_TAXA = [  # graves por 100 mil habitantes -> cor do município
    (25, [254, 229, 217]), (50, [252, 174, 145]), (100, [251, 106, 74]),
    (200, [222, 45, 38]), (float("inf"), [165, 15, 21])]


def cor_da_taxa(taxa: float | None) -> list[int]:
    if taxa is None or pd.isna(taxa):
        return [200, 200, 200, 60]
    for limite, cor in ESCALA_TAXA:
        if taxa < limite:
            return cor + [150]
    return ESCALA_TAXA[-1][1] + [150]


def cor_da_persistencia(anos: float | None, maximo: int) -> list[int]:
    """Do amarelo (poucos anos no top 50) ao vermelho escuro (todos os anos)."""
    if anos is None or pd.isna(anos) or anos == 0:
        return [120, 120, 120, 140]
    f = min(anos / maximo, 1.0)
    return [int(255 - 90 * f), int(200 * (1 - f)), int(40 * (1 - f)), 220]


def poligonos(geojson: str) -> list:
    g = json.loads(geojson)
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    return []


# --- Mapa -------------------------------------------------------------------------
with aba_mapa:
    if not existe("mapa_trecho"):
        st.info("As tabelas do mapa (`mapa_trecho`, `mapa_acidente_grave` e `mapa_municipio`, "
                "issue #57) ainda não foram criadas. Rode `docker compose run --rm dbt build`.")
    else:
        anos = consultar(f"SELECT DISTINCT ano FROM {SCHEMA}.mart_risco_trecho_ano ORDER BY ano")["ano"].tolist()
        ufs = consultar(f"SELECT DISTINCT uf FROM {SCHEMA}.mapa_trecho ORDER BY uf")["uf"].tolist()
        c_ano, c_uf, c_camadas = st.columns([1, 1, 2])
        ano = c_ano.selectbox("Ano", anos, index=len(anos) - 2 if len(anos) > 1 else 0, key="ano_mapa")
        uf = c_uf.selectbox("UF", ["Brasil"] + ufs, key="uf_mapa")
        with c_camadas:
            ver_densidade = st.checkbox("Densidade dos acidentes graves", value=True, key="densidade")
            ver_municipios = st.checkbox("Municípios por graves a cada 100 mil habitantes",
                                         value=False, key="municipios")
        todas = uf == "Brasil"

        tem_persistencia = existe("mart_persistencia_trecho")
        trechos = consultar(
            f"""SELECT m.chave_trecho, m.rotulo, m.longitude, m.latitude, a.graves, a.mortos
                    {", p.anos_no_top_50" if tem_persistencia else ""}
                FROM {SCHEMA}.mapa_trecho m
                JOIN {SCHEMA}.mart_risco_trecho_ano a ON a.chave_trecho = m.chave_trecho AND a.ano = %s
                {f"LEFT JOIN {SCHEMA}.mart_persistencia_trecho p ON p.chave_trecho = m.chave_trecho"
                 if tem_persistencia else ""}
                WHERE a.graves > 0 AND (%s OR m.uf = %s)""", (ano, todas, uf))

        camadas = []
        if ver_municipios and existe("mapa_municipio"):
            mun = consultar(
                f"""SELECT m.nome, m.uf, m.geojson, a.graves, a.graves_por_100_mil, a.posicao_taxa
                    FROM {SCHEMA}.mapa_municipio m
                    LEFT JOIN {SCHEMA}.mart_risco_municipio_ano a
                           ON a.cod_municipio = m.cod_municipio AND a.ano = %s
                    WHERE %s OR m.uf = %s""", (ano, todas, uf))
            linhas = []
            for r in mun.itertuples():
                # A taxa só vale com 10 ou mais graves no ano (posicao_taxa não nula, E3).
                taxa = r.graves_por_100_mil if pd.notna(r.posicao_taxa) else None
                texto = (f"{r.nome} ({r.uf}): {r.graves_por_100_mil:.1f} graves por 100 mil hab."
                         if taxa is not None else f"{r.nome} ({r.uf}): menos de 10 graves no ano")
                for p in poligonos(r.geojson):
                    linhas.append({"poligono": p, "cor": cor_da_taxa(taxa), "texto": texto})
            camadas.append(pdk.Layer(
                "PolygonLayer", linhas, get_polygon="poligono", get_fill_color="cor",
                get_line_color=[255, 255, 255, 80], line_width_min_pixels=0.5, pickable=True))
        elif ver_municipios:
            st.info("A tabela `mapa_municipio` ainda não foi criada.")

        if ver_densidade:
            if ano < 2017:
                st.caption(f"Densidade: a PRF só publica a coordenada do acidente desde 2017, e o ano "
                           f"escolhido é {ano}.")
            else:
                pontos = consultar(
                    f"""SELECT longitude, latitude FROM {SCHEMA}.mapa_acidente_grave
                        WHERE ano = %s AND (%s OR uf = %s)""", (ano, todas, uf))
                camadas.append(pdk.Layer(
                    "HeatmapLayer", pontos, get_position=["longitude", "latitude"],
                    radius_pixels=25, intensity=1, threshold=0.05, opacity=0.6))

        if not trechos.empty:
            maximo = int(trechos["anos_no_top_50"].max()) if tem_persistencia else 1
            trechos["cor"] = [cor_da_persistencia(a, maximo) if tem_persistencia else VERMELHO + [200]
                              for a in (trechos["anos_no_top_50"] if tem_persistencia
                                        else [None] * len(trechos))]
            trechos["raio"] = trechos["graves"].astype(float) ** 0.5 * 1500
            trechos["texto"] = [
                f"{r.rotulo}: {int(r.graves)} graves e {int(r.mortos)} mortos em {ano}"
                + (f"; {int(r.anos_no_top_50)} anos no top 50" if tem_persistencia else "")
                for r in trechos.itertuples()]
            camadas.append(pdk.Layer(
                "ScatterplotLayer", trechos, get_position=["longitude", "latitude"],
                get_radius="raio", get_fill_color="cor", radius_min_pixels=2, radius_max_pixels=30,
                stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=0.5, pickable=True))

        if todas or trechos.empty:
            vista = pdk.ViewState(latitude=-14.5, longitude=-52.0, zoom=3.4)
        else:
            vista = pdk.ViewState(latitude=float(trechos["latitude"].mean()),
                                  longitude=float(trechos["longitude"].mean()), zoom=5.6)
        st.pydeck_chart(pdk.Deck(layers=camadas, initial_view_state=vista, map_provider="carto",
                                 map_style="light", tooltip={"text": "{texto}"}),
                        height=560)

        legenda = ["**Círculos:** os trechos de 10 km com acidente grave no ano; o tamanho é o "
                   "número de graves no ano."]
        if tem_persistencia:
            legenda.append("**Cor do círculo:** em quantos anos o trecho ficou entre os 50 mais "
                           "graves do país, do amarelo (poucos) ao vermelho escuro (todos).")
        if ver_densidade:
            legenda.append("**Mancha:** onde os acidentes graves do ano se concentram.")
        if ver_municipios:
            legenda.append("**Municípios:** graves por 100 mil habitantes no ano, do mais claro "
                           "(menos de 25) ao mais escuro (200 ou mais); cinza = menos de 10 "
                           "graves no ano, quando a taxa não é comparável.")
        st.markdown("  \n".join(legenda))
        st.caption("A coordenada do acidente só existe desde 2017 (sistema BAT da PRF). De 2019 a "
                   "2024, metade das coordenadas é um ponto padrão da PRF, e não o local do "
                   "acidente: esses pontos ficam fora do mapa. Por isso, o lugar de cada trecho é "
                   "o centro dos acidentes com coordenada confiável.")

        # --- Ficha do trecho ------------------------------------------------------------
        st.subheader("Ficha do trecho")
        if trechos.empty:
            st.info("Nenhum trecho com acidente grave nesse ano e UF.")
        else:
            ordem = trechos.sort_values("graves", ascending=False)
            escolha = st.selectbox("Trecho (do mais grave para o menos grave no ano)",
                                   ordem["rotulo"].tolist(), key="trecho_ficha")
            t = ordem[ordem["rotulo"] == escolha].iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Acidentes graves em {ano}", int(t["graves"]))
            c2.metric(f"Mortos em {ano}", int(t["mortos"]))
            if tem_persistencia:
                c3.metric("Anos entre os 50 mais graves", int(t["anos_no_top_50"] or 0))

            col_perfil, col_relevo = st.columns(2)
            with col_perfil:
                st.markdown("**Perfil dos acidentes graves** (issue #58)")
                if existe("mart_perfil_trecho"):
                    perfil = consultar(f"SELECT * FROM {SCHEMA}.mart_perfil_trecho WHERE chave_trecho = %s",
                                       (t["chave_trecho"],))
                    if perfil.empty:
                        st.caption("Sem perfil para este trecho.")
                    else:
                        st.dataframe(perfil.drop(columns=["chave_trecho"]).T.rename(columns={0: "valor"}),
                                     width="stretch")
                else:
                    st.info("A tabela `mart_perfil_trecho` ainda não foi criada.")
            with col_relevo:
                st.markdown("**Relevo** (issue #59)")
                if existe("dim_trecho_relevo"):
                    relevo = consultar(
                        f"""SELECT tipo_relevo, unidade_relevo, regiao_relevo, dominio_relevo
                            FROM {SCHEMA}.dim_trecho_relevo WHERE chave_trecho = %s""",
                        (t["chave_trecho"],))
                    if relevo.empty:
                        st.caption("Sem relevo para este trecho.")
                    else:
                        st.dataframe(relevo.T.rename(columns={0: "valor"}), width="stretch")
                else:
                    st.info("A tabela `dim_trecho_relevo` ainda não foi criada.")

        # --- Pontos negros x demais trechos ---------------------------------------------
        st.subheader("O que os pontos negros têm de diferente")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Perfil dos acidentes graves** (issue #58)")
            if existe("mart_perfil_comparacao"):
                comp = consultar(f"""SELECT atributo, pct_pontos_negros, pct_demais_trechos
                                     FROM {SCHEMA}.mart_perfil_comparacao ORDER BY atributo""")
                st.bar_chart(comp.set_index("atributo")[["pct_pontos_negros", "pct_demais_trechos"]],
                             horizontal=True, stack=False)
            else:
                st.info("A tabela `mart_perfil_comparacao` ainda não foi criada.")
        with col_b:
            st.markdown("**Relevo** (issue #59)")
            if existe("mart_relevo_comparacao"):
                comp = consultar(f"""SELECT tipo_relevo, pct_pontos_negros, pct_demais_trechos
                                     FROM {SCHEMA}.mart_relevo_comparacao
                                     ORDER BY pct_pontos_negros DESC""")
                st.bar_chart(comp.set_index("tipo_relevo")[["pct_pontos_negros", "pct_demais_trechos"]],
                             horizontal=True, stack=False)
                st.caption("% dos pontos negros em cada relevo, contra % dos demais trechos. É "
                           "comparação, e não causa.")
            else:
                st.info("A tabela `mart_relevo_comparacao` ainda não foi criada.")


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

        st.subheader("Os trechos que se mantêm: em quantos anos ficaram entre os 50 mais graves")
        if not colunas_da_tabela("mart_persistencia_trecho"):
            st.info("A tabela de persistência (`mart_persistencia_trecho`, issue #53) ainda não "
                    "foi criada. Rode `docker compose run --rm dbt build` depois que ela entrar "
                    "na `main`.")
        else:
            persistencia = consultar(
                f"""SELECT br, uf, km_inicio, anos_no_top_50, graves_no_total
                    FROM {SCHEMA}.mart_persistencia_trecho
                    WHERE br <> 0 AND anos_no_top_50 > 0
                    ORDER BY anos_no_top_50 DESC, graves_no_total DESC LIMIT 20""")
            persistencia["trecho"] = ("BR-" + persistencia["br"].astype(int).astype(str).str.zfill(3)
                                      + "/" + persistencia["uf"] + " km "
                                      + persistencia["km_inicio"].astype(int).astype(str))
            st.dataframe(persistencia[["trecho", "anos_no_top_50", "graves_no_total"]],
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
