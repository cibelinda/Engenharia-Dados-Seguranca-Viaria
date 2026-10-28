# E3 — Camada analítica transformada, testada e orquestrada

Enunciado: [e3.md](https://github.com/UnB-BD2/PlanoEnsino/blob/main/_entregas/e3.md).
Prazo: 03/11/2026.

## Como dividimos

Como na E2: cada parte é independente. Cada pessoa cria a branch a partir da `chore/e3-base`
enquanto a base não for mergeada (depois, a partir da `main`), mexe
**só nos arquivos da sua parte**, abre o PR e pede revisão. Nenhum PR depende de outro: as
partes se encontram pelos **nomes combinados** abaixo, e não pelo código umas das outras.

| Parte | Issue | Quem | Arquivos que só ela mexe |
|---|---|---|---|
| Base do IBGE e município | #42 | Ana | `compose/ibge.yml`, `blackspot/ibge/`, `db/migrations/V0013`–`V0019`, `dbt/models/staging/ibge/`, `dbt/models/intermediate/municipio/`, `dbt/models/marts/municipio/`, `dbt/snapshots/`, testes `dbt/tests/municipio_*`, [`docs/e3/ibge.md`](ibge.md) |
| Modelo dimensional, testes e consulta otimizada | #43 | Cibelly | `dbt/models/staging/stg_*.sql` e `_origem__*.yml`, `dbt/models/marts/trecho/`, testes `dbt/tests/trecho_*`, [`docs/e3/dbt.md`](dbt.md), `docs/e3/explain/` |
| Orquestração, freshness, ADR 0005 e diário | #44 | Maria | `compose/orquestracao.yml`, `orquestracao/`, [`docs/e3/orquestracao.md`](orquestracao.md), `docs/adr/0005-*.md`, `diario-de-bordo.md` |
| Painel | #45 | Ana | `compose/painel.yml`, `painel/`, [`docs/e3/painel.md`](painel.md) |

Arquivos compartilhados (`docker-compose.yml`, `requirements.txt`, `dbt/dbt_project.yml`,
`dbt/profiles.yml`, `README.md`) **não devem ser editados** nos PRs das partes. Se faltar algo
comum, avise no grupo antes de mexer. Biblioteca nova: avise no grupo, e uma pessoa só
acrescenta.

No `AI-USAGE.md`, cada uma preenche só a própria entrada, reservada no fim do arquivo.

## O que já está pronto na `main`

- **dbt** (`dbt-postgres`) na imagem e o serviço `dbt` em `compose/dbt.yml`, fora do `up`:
  `docker compose run --rm dbt build`. O projeto está em `dbt/`, com as camadas `staging`,
  `intermediate` e `marts`, cada uma num schema do PostgreSQL (`analitico_staging`,
  `analitico_intermediate`, `analitico_marts`, `analitico_snapshots`).
- **As views de staging** (uma por tabela de origem, versão vigente): `stg_lote`,
  `stg_ocorrencia`, `stg_veiculo`, `stg_pessoa`, `stg_ocorrencia_causa`, `stg_ocorrencia_tipo`,
  `stg_causa`, `stg_tipo`. Hoje só repetem a origem; a limpeza é da Cibelly, **sem mudar o nome
  das colunas**.
- **Arquivos vazios** `compose/ibge.yml`, `compose/orquestracao.yml` e `compose/painel.yml`, já
  incluídos no `docker-compose.yml`.

## Contrato entre as partes

| Nome | Dono | O que é | Granularidade (o que é uma linha) |
|---|---|---|---|
| `ibge.*` (schema no Postgres) | Ana | Dados brutos do IBGE: municípios, população por ano, malha municipal | — |
| `dim_municipio` | Ana | Dimensão de município **com histórico** (variação lenta): `cod_municipio`, `nome`, `uf`, `valido_de`, `valido_ate`, `atual` | uma linha por município **por versão** |
| `int_ocorrencia_municipio` | Ana | Ligação acidente → município: `id_lote`, `id`, `cod_municipio`, `metodo` (`coordenada` ou `nome`) | uma linha por acidente |
| `mart_risco_municipio_ano` | Ana | Resposta "município mais perigoso": acidentes graves, população e taxa por 100 mil habitantes | uma linha por município por ano |
| `fct_ocorrencia` | Cibelly | Fato do acidente, com as chaves das dimensões | uma linha por acidente |
| `dim_trecho`, `dim_tempo`, `dim_causa` | Cibelly | Dimensões do acidente | uma linha por trecho / dia / causa |
| `mart_risco_trecho_ano` | Cibelly | Resposta da pergunta de gestão: acidentes graves por trecho de 10 km e ano, com a posição no ranking | uma linha por trecho por ano |
| Comandos | todos | `docker compose run --rm dbt build`; o serviço de ingestão do IBGE é `ingestao-ibge` | — |

- **Chave do acidente:** `(id_lote, id)`, a mesma do banco.
- **"Grave":** `mortos > 0 or feridos_graves > 0`, como no resto do projeto.
- **Trecho:** BR + UF + faixa de 10 km (`floor(km / 10) * 10`); `br = 0` fica fora do ranking.
- **Sem pacotes do dbt:** testes com os genéricos do dbt (`unique`, `not_null`, `relationships`,
  `accepted_values`) e testes singulares em SQL. Unicidade de chave composta vai como teste
  singular. Ver o comentário em `dbt/dbt_project.yml`.
- **Migrações:** só a parte do IBGE cria migrações (`V0013`–`V0019`). Para índice em tabela do
  dbt, use a configuração `indexes` do próprio modelo, e não migração.
- **O painel lê só** `mart_risco_trecho_ano` e `mart_risco_municipio_ano`.

## Checklist de aceite da E3

| Item | Parte |
|---|---|
| Modelo com fato e dimensão, granularidade declarada e uma dimensão de variação lenta | dbt (fato e dimensões) e IBGE (`dim_municipio`) |
| Transformações em dbt, em camadas | dbt e IBGE |
| Testes de dados: esquema, volume, unicidade, integridade referencial e distribuição | dbt e IBGE |
| Orquestração agendada com dependências, retry e backfill demonstrado | Orquestração |
| Uma consulta otimizada com `EXPLAIN (ANALYZE, BUFFERS)` antes e depois | dbt |
| Métrica de freshness e SLA para uma tabela de consumo | Orquestração |
| 1 ADR sobre modelagem analítica ou ferramenta de transformação | ADR 0005 |
| Painel respondendo à pergunta de gestão | Painel |
