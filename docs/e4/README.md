# E4 — Plataforma completa, governada e defendida

Enunciado: [e4.md](https://github.com/UnB-BD2/PlanoEnsino/blob/main/_entregas/e4.md).
Prazo: 24/11/2026 (defesa na Semana 16).

## Como dividimos

Como na E2 e na E3: cada parte é independente. Cada pessoa cria a branch a partir da
`chore/e4-base` enquanto a base não for mergeada (depois, a partir da `main`), mexe
**só nos arquivos da sua parte**, abre o PR e pede revisão. Nenhum PR depende de outro: as
partes se encontram pelos **nomes combinados** abaixo, e não pelo código umas das outras.

| Parte | Issue | Quem | Arquivos que só ela mexe |
|---|---|---|---|
| LGPD e controle de acesso | #52 | Ana | `db/migrations/V0020`–`V0029`, `compose/painel.yml`, `painel/`, [`docs/e4/lgpd.md`](lgpd.md), [`docs/e4/acesso.md`](acesso.md) |
| Métricas, catálogo e linhagem | #53 | Cibelly | `dbt/models/marts/trecho/`, `dbt/models/metricas/`, `dbt/models/exposures.yml`, descrições nos `.yml` dos modelos e das fontes, testes `dbt/tests/trecho_*` e `dbt/tests/metrica_*`, [`docs/e4/metricas.md`](metricas.md), [`docs/e4/linhagem.md`](linhagem.md) |
| ETL reverso, ADR 0006 e revisão dos ADRs | #54 | Maria | `orquestracao/`, `compose/orquestracao.yml`, [`docs/e4/etl-reverso.md`](etl-reverso.md), `docs/adr/0006-*.md`, status e gatilhos dos ADRs `0001`–`0005`, `docs/adr/index.md`, `diario-de-bordo.md` |

Arquivos compartilhados (`docker-compose.yml`, `requirements.txt`, `dbt/dbt_project.yml`,
`dbt/profiles.yml`, `README.md`) **não devem ser editados** nos PRs das partes. Se faltar algo
comum, avise no grupo antes de mexer. Biblioteca nova (ex.: `dbt-metricflow` para a camada
semântica): avise no grupo, e uma pessoa só acrescenta.

No `AI-USAGE.md`, cada uma preenche só a própria entrada, reservada no fim do arquivo.

## O que já está pronto na `main`

- Tudo da E3 (tag `e3`): os marts `mart_risco_trecho_ano` e `mart_risco_municipio_ano`, o
  painel, o Dagster com a esteira agendada e a freshness.
- Teste do zero num clone novo da `main`: 2.249.767 acidentes carregados, `dbt build` com 79 de
  79 passando, painel e Dagster no ar, em cerca de 13 minutos.

## Contrato entre as partes

| Nome | Dono | O que é | Granularidade (o que é uma linha) |
|---|---|---|---|
| `mart_persistencia_trecho` | Cibelly | Em quantos anos cada trecho ficou entre os 50 mais graves: `chave_trecho`, `br`, `uf`, `km_inicio`, `anos_no_top_50`, `graves_no_total` | uma linha por trecho |
| Métricas | Cibelly | Definição única de `graves`, `graves_por_100_mil` e `anos_no_top_50`, com descrição e fórmula, no dbt | — |
| Exposure `painel` | Cibelly | O painel no fim da linhagem do dbt (lê os marts de trecho e de município) | — |
| Exposure `etl_reverso_trechos_criticos` | Cibelly | O ETL reverso no fim da linhagem do dbt | — |
| Asset `etl_reverso_trechos_criticos` | Maria | Saída dos trechos críticos, agendada no Dagster. Formato e destino decididos no ADR 0006 | uma linha por trecho crítico |
| `painel_leitor` | Ana | Papel do Postgres com acesso só de leitura aos marts, usado pelo painel | — |
| Papéis com recorte | Ana | Papéis com acesso só a uma parte das linhas (ex.: uma UF) ou sem as colunas de `pessoa` | — |
| Comandos | todos | `docker compose up --build -d` e `docker compose run --rm dbt build`, como na E3 | — |

- **"Grave"** continua `mortos > 0 or feridos_graves > 0`, e **trecho** continua BR + UF + faixa
  de 10 km. A definição muda de lugar (vai para a camada de métricas), e não de valor.
- **"Top 50"**: `posicao <= 50` na `mart_risco_trecho_ano`, ano a ano, com `br <> 0`.
- **O painel e o ETL reverso leem só tabelas de `analitico_marts`.** Nenhum dos dois calcula
  métrica por conta própria: se precisar de um número novo, ele entra no dbt.
- **Enquanto a parte de outra pessoa não estiver na `main`**, cada uma lê o que já existe
  (ex.: o ETL reverso pode começar pela `mart_risco_trecho_ano`) e troca depois.
- **Migrações:** só a parte de acesso cria migrações (`V0020`–`V0029`). O dbt recria as tabelas
  a cada execução, e o acesso dado com `GRANT` precisa continuar valendo depois disso.

## Checklist de aceite da E4

| Item | Parte |
|---|---|
| Painel analítico (da E3) e camada semântica com cada métrica definida num lugar só | Métricas |
| Um caminho de ETL reverso, dizendo quem consome e o que faz com o dado | ETL reverso |
| Catálogo e linhagem da fonte pública até o consumo | Métricas e linhagem |
| Análise de LGPD: dado pessoal, base legal, retenção, descarte e reidentificação | LGPD |
| Controle de acesso demonstrado num recorte de linha ou de coluna, com privilégio mínimo | Acesso |
| ADR 0006 sobre como o dado é disponibilizado, com medição | ADR 0006 |
| Portfólio dos ADRs com os gatilhos de revisão relidos | Revisão dos ADRs |
| Defesa: 20 minutos para banca técnica e de gestão | todas |
