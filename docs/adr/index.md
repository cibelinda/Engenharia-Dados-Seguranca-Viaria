---
title: Decisões (ADRs)
nav_order: 5
has_children: true
has_toc: false
nav_exclude: false
---

# Decisões de arquitetura (ADRs)

Cada ADR registra uma decisão: o contexto, as alternativas, o que foi medido, o que se ganha e o
que se perde, e quando revisar.

| ADR | Decisão | Situação |
|---|---|---|
| [0001](0001-modelo-normalizado-insert-only-versionado-por-lote.md) | Origem normalizada e insert-only, versionada por lote de carga | Aceito; revisado em 13/10 e em 23/11/2026 |
| [0002](0002-banco-espacial-postgis.md) | Banco espacial: PostgreSQL com PostGIS | Aceito (correção da E1); gatilhos relidos em 23/11/2026 |
| [0003](0003-dataset-completo-br-brasil-e-bat.md) | Dataset completo da PRF, BR-Brasil e BAT no mesmo esquema | Aceito (correção da E1); gatilhos relidos em 23/11/2026 |
| [0004](0004-ingestao-por-lote-incremental-em-delta.md) | Camada analítica alimentada por lote incremental por ano, em Delta com zstd; CDC como trilha de mudanças | Aceito (E2); **um gatilho disparou** em 23/11/2026, decisão mantida |
| [0005](0005-dbt-e-dagster-em-vez-de-cron-com-sql.md) | Transformação em dbt e orquestração em Dagster, em vez de `cron` com scripts SQL | Aceito (E3); gatilhos relidos em 23/11/2026 |
| [0006](0006-trechos-criticos-entregues-por-csv-agendado.md) | Trechos críticos entregues à PRF de cada UF por CSV agendado, em vez de tabela ou API | Proposto (E4) |

## Revisão do portfólio (E4, 23/11/2026)

Cada ADR tem, no fim, uma seção "Revisão de 2026-11-23" com os gatilhos relidos e medidos. Resumo:

| ADR | Gatilho | O que aconteceu |
|---|---|---|
| 0001 | Tamanho, latência, consumidor rápido, republicações | Nenhum de custo disparou (origem com 2,8 GB, Q2 em 5,0 s). O painel surgiu, mas lê os marts. **A comparação das republicações (#7) nunca foi feita.** |
| 0002 | Análise espacial lenta; malha de rodovia | Não. As fontes novas (município, relevo) eram polígonos e entraram com índice GiST. |
| 0003 | Quebra 2016/2017; BR-Brasil republicado | Não. 36 trechos do top 50 continuam de 2016 para 2017, contra 35 a 41 nos outros anos. |
| 0004 | Consumidor que não lê Delta | **Disparou:** nenhum consumidor da E3 e da E4 lê o Delta. Decisão mantida; a saída fica para a retrospectiva. |
| 0005 | Build lento; mais de uma máquina | Não, mas o `dbt build` dobrou em três semanas (~2 min). |
