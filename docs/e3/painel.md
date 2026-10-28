# Painel

Issue #45. Um painel em [Streamlit](https://streamlit.io/) (uma página web feita em Python) que
responde à pergunta de gestão. Código em [`painel/app.py`](../../painel/app.py).

## Como abrir

```bash
docker compose up --build -d
docker compose run --rm dbt build    # cria as tabelas que o painel lê
```

Depois, abra **http://localhost:8501**. Se a porta estiver ocupada: `PAINEL_PORT=8502`.

## O que ele mostra

O painel lê só as duas tabelas finais do dbt, em `analitico_marts`.

**Aba "Trechos mais graves"** (lê `mart_risco_trecho_ano`, da issue #43):

| Gráfico | Responde |
|---|---|
| Os 20 trechos com mais acidentes graves no ano escolhido | Onde estão os pontos negros |
| Em quantos anos cada trecho ficou entre os 50 mais graves | **Se os trechos se mantêm de um ano para o outro**, a segunda metade da pergunta |

O painel espera nessa tabela as colunas `br`, `uf`, `km_inicio`, `ano` e `graves`. Enquanto ela
não existir, a aba mostra um aviso, e não um erro.

**Aba "Municípios mais perigosos"** (lê `mart_risco_municipio_ano`, da issue #42):

| Gráfico | Responde |
|---|---|
| Municípios com mais acidentes graves por 100 mil habitantes | Qual município é mais perigoso, levando em conta o tamanho da população |
| Municípios com mais acidentes graves em número absoluto | Onde há mais acidentes graves no total |

Um controle escolhe o mínimo de acidentes graves no ano (padrão: 10). Sem esse corte, uma cidade
de 2 mil habitantes com um único acidente grave aparece no topo do ranking.

## Como foi testado

- A página foi rodada sem navegador, com a ferramenta de teste do próprio Streamlit: nenhum erro,
  e a aba de municípios mostrou os rankings com os dados reais.
- A aba de trechos foi testada com uma tabela provisória no mesmo formato combinado, num banco de
  teste: os gráficos funcionaram, e a tabela foi apagada depois.
- O serviço sobe com o compose e a página responde (HTTP 200).
