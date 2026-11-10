# Camada de métricas

Parte da E4 da issue #53. O contrato entre as partes está no [README.md](README.md); o catálogo
e a linhagem, em [`linhagem.md`](linhagem.md).

```bash
docker compose run --rm dbt build      # modelos, métricas e testes
```

## O problema

Até a E3, a regra de cada número estava escrita em mais de um lugar. "Grave"
(`mortos > 0 or feridos_graves > 0`) estava no `fct_ocorrencia` e, de novo, no
`mart_risco_municipio_ano`. E a resposta da segunda metade da pergunta de gestão, "os trechos se
mantêm de um ano para o outro?", nem estava no dbt: o painel fazia o próprio `rank()` e contava os
anos no top 50 sozinho. Se alguém mudasse a regra num lugar, os números deixariam de bater sem
nenhum teste falhar, e o ETL reverso (#54) teria de copiar a conta do painel.

## As três métricas

| Métrica | O que é | Fórmula | Onde aparece |
|---|---|---|---|
| `graves` | Acidentes com ao menos um morto ou um ferido grave | `count(acidente) where mortos > 0 or feridos_graves > 0` | `fct_ocorrencia.grave`, `graves` nos dois marts de risco |
| `graves_por_100_mil` | Acidentes graves do município no ano por 100 mil habitantes | `round(graves * 100000 / populacao, 2)` | `mart_risco_municipio_ano.graves_por_100_mil` |
| `anos_no_top_50` | Em quantos anos o trecho ficou entre os 50 com mais graves do ano | `count(ano) where posicao <= 50`, por trecho | `mart_risco_trecho_ano.no_top_50`, `mart_persistencia_trecho.anos_no_top_50` |

As definições **mudaram de lugar, e não de valor** (regra do contrato): "grave" continua sendo
morto ou ferido grave, e não a `classificacao_acidente` da PRF; trecho continua BR + UF + faixa de
10 km; o top 50 é `posicao <= 50` na `mart_risco_trecho_ano`, ano a ano.

## Onde cada coisa fica

Cada métrica tem **uma** regra, **uma** descrição e **uma** forma de agregar, e cada uma dessas
três coisas mora num lugar só:

| O quê | Onde | Para quê |
|---|---|---|
| A **regra**, em SQL | [`dbt/macros/metricas.sql`](../../dbt/macros/metricas.sql): `metrica_grave`, `metrica_graves_por_100_mil`, `metrica_no_top_50` | Os modelos chamam a macro, e não repetem a regra. Mudar a regra é mudar uma linha, e o `dbt build` reconstrói tudo o que depende dela |
| A **descrição** e a fórmula | [`dbt/models/metricas/metricas.md`](../../dbt/models/metricas/metricas.md), em blocos `{% docs %}` | As colunas dos marts e as métricas usam `doc('metrica_graves')`: o catálogo diz a mesma coisa em todo lugar |
| A **forma de agregar** | [`dbt/models/metricas/_metricas.yml`](../../dbt/models/metricas/_metricas.yml): `semantic_models` e `metrics` | Como somar a métrica por qualquer recorte (ano, UF, trecho, município), na especificação do MetricFlow |

A camada semântica **não repete a regra**. Ela só soma as colunas que a macro produziu: a medida
`graves` é a soma de `grave` no fato, e a medida `anos_no_top_50` é a soma de `no_top_50` na
`mart_risco_trecho_ano`. A única fórmula que aparece duas vezes é a da taxa, porque a métrica
derivada `graves_por_100_mil` precisa refazer a divisão para qualquer agrupamento (por UF, por
exemplo), e não só por município e ano. Um teste confere que as duas dão o mesmo número.

### Por que macros e `semantic_models`, e não só o MetricFlow

A especificação do MetricFlow (`semantic_models` e `metrics`) é lida pelo próprio dbt-core, sem
biblioteca nova. O `dbt parse`, que roda no começo de todo `dbt build`, **valida** a camada
semântica: uma métrica que aponta para uma medida que não existe faz o build falhar (testado). As
métricas também aparecem no `dbt docs`, com a descrição, a fórmula e o grafo de linhagem.

Para *consultar* uma métrica pelo MetricFlow (`mf query --metrics anos_no_top_50 --group-by
trecho`), seria preciso o `dbt-metricflow` na imagem. A base pede para combinar biblioteca nova no
grupo, e nem o painel nem o ETL reverso precisam dele: os dois leem tabelas de `analitico_marts`
(contrato). Por isso o número que eles leem é **materializado** pelo dbt, nas colunas que a macro
produz, e a camada semântica fica como a definição documentada, validada e testada.

## `mart_persistencia_trecho`

**Uma linha por trecho**: todos os 7.544 trechos da `dim_trecho`. O trecho que nunca ficou no top 50
tem `anos_no_top_50 = 0`.

| Coluna | O que é |
|---|---|
| `chave_trecho`, `br`, `uf`, `km_inicio`, `km_fim`, `rotulo` | O trecho, como na `dim_trecho` |
| `anos_no_top_50` | A métrica: em quantos anos o trecho ficou entre os 50 mais graves |
| `graves_no_total` | Graves somados **nos anos em que o trecho ficou no top 50** (é o número que o painel mostrava). 0 quando o trecho nunca ficou no top |
| `primeiro_ano_no_top_50`, `ultimo_ano_no_top_50` | O primeiro e o último ano no top (NULL se nunca ficou) |

Decisões:

- **O ano corrente, parcial, entra na conta**, como no painel da E3. O ranking é feito dentro do
  ano, então mesmo um ano com 8 meses tem os seus 50 piores trechos. A `mart_risco_trecho_ano`
  marca o ano parcial com `ano_completo = false`, para quem quiser tirá-lo.
- **Empate conta.** A `posicao` é um `rank()`: dois trechos empatados na 50ª posição ficam os dois
  no top. Por isso um ano pode ter mais de 50 trechos no top 50.
- **`graves_no_total` segue o painel**, e não "graves em todos os anos". É o critério de
  desempate da lista do painel, e mudar o significado quebraria a regra "muda de lugar, e não de
  valor".

## O que a tabela mostra

Medido em 2026-11-10, com os 20 anos carregados (2007 a 2026, este último até o mês anterior):

- **142 trechos**, de 7.544, já ficaram ao menos um ano no top 50. Cada ano tem de 50 a 55 trechos
  no top (por causa dos empates), e a soma de `anos_no_top_50` é 1.037.
- **6 trechos ficaram no top 50 em todos os 20 anos**, e outros 41 ficaram em 10 a 19 anos. A
  resposta à segunda metade da pergunta é **sim**: os pontos negros se mantêm.

| Anos no top 50 | Trechos |
|---|---|
| 0 | 7.402 |
| 1 | 33 |
| 2 a 4 | 34 |
| 5 a 9 | 28 |
| 10 a 19 | 41 |
| 20 (todos) | 6 |

Os mais persistentes:

| Trecho | Anos no top 50 | Graves nesses anos |
|---|---|---|
| BR-101/SC km 200–210 | 20 | 2.121 |
| BR-101/SC km 210–220 | 20 | 1.762 |
| BR-316/PI km 0–10 | 20 | 1.089 |
| BR-381/MG km 480–490 | 20 | 1.061 |
| BR-040/MG km 520–530 | 20 | 994 |
| BR-277/PR km 0–10 | 20 | 986 |
| BR-101/ES km 260–270 | 19 | 1.866 |
| BR-153/GO km 500–510 | 19 | 1.113 |


## Testes

Os testes `metrica_*` provam que **o número do mart é o número da definição**. Os `trecho_*`
novos conferem a coerência da tabela nova.

| Teste | O que confere |
|---|---|
| `metrica_anos_no_top_50_bate` | Trecho a trecho, `anos_no_top_50` e `graves_no_total` da `mart_persistencia_trecho` são iguais à métrica da camada semântica (soma de `no_top_50`) e à regra do contrato escrita à mão (`posicao <= 50`). Nenhum trecho sobra nem falta |
| `metrica_anos_no_top_50_bate_com_painel` | A consulta que o painel da E3 fazia sozinho, copiada como estava e sem o `LIMIT 20`, dá os mesmos números da tabela nova, em todos os trechos que já ficaram no top. É a prova de que a métrica mudou de lugar e não de valor |
| `metrica_graves_bate` | `grave` segue a regra do contrato em cada acidente; os `graves` da `mart_risco_trecho_ano` (trecho e ano) e da `mart_risco_municipio_ano` (município e ano) são a métrica recontada a partir do fato e da origem |
| `metrica_graves_por_100_mil_bate` | A taxa de cada município e ano é a fórmula da métrica derivada, com duas casas |
| `trecho_persistencia_coerente` | `anos_no_top_50` entre 0 e o número de anos; primeiro e último ano no top só quando há ano no top; cada ano no top tem ao menos um grave; cada ano da série tem ao menos 50 trechos no top |
| contrato do modelo e genéricos | `mart_persistencia_trecho` com o contrato aplicado (nome e tipo de cada coluna), `chave_trecho` única, não nula e ligada à `dim_trecho` |

O `dbt build` passa com 91 de 91 (eram 79 na E3; os 2 NO-OP são as exposures). Cada teste novo
foi conferido quebrando de propósito o que ele protege, reconstruindo só os marts afetados, e
depois desfazendo:

| O que foi quebrado | Testes que falharam |
|---|---|
| Top 50 virou top 49 na macro `metrica_top_n` | `metrica_anos_no_top_50_bate` e `metrica_anos_no_top_50_bate_com_painel` (25 trechos cada) |
| "Grave" virou só `mortos > 0`, e a taxa virou por 10 mil | `metrica_graves_bate` (30.357 linhas), `metrica_graves_por_100_mil_bate` (27.264) e o `municipio_volume_graves_bate_com_origem` da E3 (20 anos) |
| `graves_no_total` somando todos os anos, e não só os anos no top | `metrica_anos_no_top_50_bate` (6.889), `metrica_anos_no_top_50_bate_com_painel` (136) e `trecho_persistencia_coerente` (6.757) |

Um teste que mudar uma regra de propósito, e não por engano, vai falhar também: é o aviso de que a
definição mudou de valor, e de que o contrato da E4 (e esta página) precisa mudar junto.
