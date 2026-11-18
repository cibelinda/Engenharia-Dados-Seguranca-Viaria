---
title: Pipeline e modelo
nav_order: 3
permalink: /pipeline/
---

# Pipeline e modelo

Tudo roda em contêineres, e um único `docker compose up` sobe a esteira. Cada serviço faz uma
coisa, e a ordem da primeira subida é declarada no próprio Compose: um serviço só começa quando os
que ele depende terminaram sem erro. Depois disso, o Dagster cuida das execuções seguintes
([Orquestração e painel](../orquestracao/)).

## Os serviços

```mermaid
flowchart LR
    subgraph origem["Fonte transacional"]
        direction TB
        DB[("db<br/>PostgreSQL + PostGIS")]
        MIG["migrate<br/>Flyway, 13 migrações"]
        IBGE["ingestao-ibge<br/>APIs do IBGE"]
        IBGE --> DB
        DL["download<br/>50 arquivos, SHA-256"]
        LOAD["load<br/>COPY, um lote por ano"]
        MIG --> LOAD
        DL --> LOAD
        LOAD --> DB
    end
    subgraph analitica["Camada analítica"]
        direction TB
        LOTE["ingestao-lote<br/>partições que mudaram"]
        CDC["connect · redpanda<br/>cdc-consumidor"]
        LAKE[("volume lakehouse<br/>tabelas Delta")]
        LOTE --> LAKE
        CDC --> LAKE
    end
    subgraph consumo["Modelo e consumo"]
        direction TB
        DBT["dbt<br/>staging → marts"]
        PAINEL["painel<br/>Streamlit"]
        DBT --> PAINEL
    end
    ORQ(["orquestracao<br/>Dagster, todo dia"])
    DB --> LOTE
    DB -- WAL --> CDC
    DB --> DBT
    ORQ -.-> origem
    ORQ -.-> LOTE
    ORQ -.-> DBT
```

| Etapa | O que faz |
|---|---|
| **Aquisição** | Baixa os arquivos da PRF em paralelo e confere o SHA-256 de cada um contra o manifesto. |
| **Esquema** | O Flyway aplica as migrações versionadas, em ordem; subir de novo só aplica as novas. |
| **Carga** | Um ano por vez, numa transação, com `COPY`. Trata os formatos dos dois sistemas; linha que não cabe vai para `linha_rejeitada` com o motivo (1.275 de 13,2 milhões). |
| **Base do IBGE** | Municípios, população por ano e malha municipal, das APIs públicas do IBGE. |
| **Camada analítica** | Lote incremental e captura de mudanças gravam tabelas Delta. [Detalhes](../camada-analitica/) |
| **Modelo analítico** | O dbt limpa, monta o fato e as dimensões e as tabelas de consumo, e testa tudo. [Detalhes](../modelo-analitico/) |
| **Orquestração** | O Dagster roda a esteira todo dia, com retry, backfill por ano e SLA de freshness. [Detalhes](../orquestracao/) |
| **Painel** | Streamlit sobre as duas tabelas de consumo: trechos e municípios mais graves. |
| **Testes** | 119 testes do pipeline (esquema, volume, reprocessamento, lote e CDC) e os testes de dados do dbt. |

## O modelo de dados

O arquivo de pessoas da PRF mistura acidente, veículo e pessoa numa mesma linha. No banco, cada
um vira uma tabela, ligada por chaves estrangeiras, e causas e tipos de acidente viram tabelas de
domínio.

```mermaid
erDiagram
    LOTE_CARGA ||--o{ OCORRENCIA : "versiona"
    OCORRENCIA ||--o{ VEICULO : "envolve"
    OCORRENCIA ||--o{ PESSOA : "envolve"
    VEICULO |o--o{ PESSOA : "transporta"
    OCORRENCIA ||--o{ OCORRENCIA_CAUSA : "tem"
    OCORRENCIA ||--o{ OCORRENCIA_TIPO : "tem"
    LOTE_CARGA {
        int id_lote PK
        int ano
        text sistema
        text status
    }
    OCORRENCIA {
        int id_lote PK
        bigint id PK
        timestamp ocorrido_em
        text uf
        int br
        numeric km
        geometry geom
        int mortos
        int feridos_graves
    }
    VEICULO {
        int id_lote PK
        bigint id PK
        bigint id_veiculo PK
        text tipo_veiculo
    }
    PESSOA {
        int id_lote PK
        bigint pesid PK
        bigint id FK
        text estado_fisico
        int idade
    }
```

Toda chave começa por `id_lote`: a mesma linha da PRF pode existir em várias versões, e os IDs
repetidos entre os dois sistemas não colidem, porque cada ano pertence a um só sistema.

## Histórico: nada é sobrescrito

Como a PRF regrava arquivos sem aviso, o banco é **insert-only, versionado por lote**. Cada carga
de um ano é um lote; uma republicação entra como um lote novo, e o anterior continua lá. As views
`*_vigente` mostram só a versão mais recente de cada ano, e é delas que as consultas leem.

```mermaid
flowchart LR
    A["2024 · lote antigo<br/>primeira publicação"]:::antigo --> B["2024 · lote novo<br/>republicação"]:::vigente
    B --> V["ocorrencia_vigente<br/>usa o lote novo"]
    classDef antigo fill:#f7f4fe,stroke:#b9b3c9,color:#6b6680
    classDef vigente fill:#ede7fb,stroke:#6b3fd4,color:#3b1f7a
```

Um ano só é recarregado quando o SHA-256 de algum arquivo dele muda. Rodar a carga de novo sem
arquivo novo leva segundos e não grava nada.

## O lugar de cada acidente

Desde 2017 todo acidente tem coordenada. A coluna `geom` é um ponto PostGIS gerado da latitude e
da longitude, no referencial oficial do Brasil (SIRGAS 2000), com índice espacial. A consulta típica
de ponto negro, "acidentes graves a menos de 2 km daqui", leva **46 ms com o índice, contra 608 ms**
calculando a distância à mão. Para os anos anteriores, o trecho (BR, UF e km) é o referencial.

## Três tempos em cada dado

| Tempo | Onde fica |
|---|---|
| **Evento:** quando o acidente aconteceu | `ocorrencia.ocorrido_em` |
| **Ingestão:** quando o lote foi carregado | `lote_carga.iniciado_em`, `finalizado_em` |
| **Processamento:** quando chegou à camada analítica | `processado_em` (lote) e `_gravado_em` (CDC) |
| **Consumo:** quando as tabelas de consumo foram reconstruídas | o último `dbt build` sem erro, medido pela freshness |
