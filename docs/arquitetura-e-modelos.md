---
title: Arquitetura e modelos
nav_order: 4
nav_exclude: false
---

# Arquitetura e modelos de dados

Os diagramas desta página saem do que está implementado: o
[`docker-compose.yml`](../docker-compose.yml) e as migrações em
[`db/migrations/`](../db/migrations/V0001__lote_carga.sql). O raciocínio por trás do modelo
está em [Modelagem da origem](modelagem-origem.md) e nos ADRs
[0001](adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md) (histórico),
[0002](adr/0002-banco-espacial-postgis.md) (PostGIS) e
[0003](adr/0003-dataset-completo-br-brasil-e-bat.md) (dataset completo).

1. TOC
{:toc}

---

## Arquitetura e pipeline

Um `docker compose up` sobe quatro serviços. `migrate` e `download` rodam em paralelo, e
`load` só começa quando os dois terminam sem erro.

```mermaid
flowchart LR
    PRF[("Google Drive da PRF<br/>ZIPs com CSV")]
    subgraph compose["docker compose up"]
        direction LR
        DL["download<br/>baixa os 50 arquivos e confere o SHA-256<br/>(sources.yaml)"]
        MIG["migrate<br/>Flyway aplica V0001–V0012"]
        LOAD["load<br/>carga ano a ano (2007–2026),<br/>BR-Brasil e BAT, com COPY"]
        TESTS["tests<br/>testes de esquema e de dados (sob demanda)"]
    end
    RAW[("volume rawdata<br/>50 ZIPs")]
    subgraph pg["PostgreSQL 18.6 + PostGIS 3.6"]
        direction TB
        TAB["tabelas<br/>ocorrencia (com geom), veiculo, pessoa,<br/>ocorrencia_causa, ocorrencia_tipo,<br/>lote_carga, lote_arquivo, linha_rejeitada"]
        VIEW["views *_vigente<br/>versão mais recente de cada ano"]
        TAB --> VIEW
    end
    Q["consultas da<br/>pergunta de gestão"]

    PRF --> DL --> RAW --> LOAD
    MIG --> TAB
    LOAD --> TAB
    VIEW --> Q
    TESTS -.confere.-> pg
```

**Ordem dos serviços** (`depends_on` do compose):

```mermaid
flowchart LR
    db["db<br/>(PostgreSQL)"] -- saudável --> migrate
    migrate -- terminou --> load
    download -- terminou --> load
    load -- terminou --> tests
```

**Onde a E1 fica no ciclo de vida do dado:**

```mermaid
flowchart LR
    E1["<b>E1 — fonte transacional</b><br/>este banco, insert-only por lote"]
    E2["E2 — ingestão<br/>lote × captura de mudanças"]
    E3["E3 — transformação<br/>modelo analítico"]
    E4["E4 — disponibilização<br/>para o gestor"]
    E1 --> E2 --> E3 --> E4
    style E1 stroke-width:3px
```

As republicações da PRF, guardadas como lotes novos, são o material da E2.

---

## Modelo conceitual

As ideias do domínio e como se relacionam, sem detalhe de banco. Um acidente envolve
veículos e pessoas; uma pessoa pode estar num veículo ou não (pedestre, testemunha,
cavaleiro); cada acidente pertence a uma versão (lote) carregada da PRF.

```mermaid
erDiagram
    LOTE_DE_CARGA ||--|{ ARQUIVO_DA_PRF : "traz"
    LOTE_DE_CARGA ||--o{ ACIDENTE : "versiona"
    ACIDENTE ||--o{ VEICULO : "envolve"
    ACIDENTE ||--o{ PESSOA : "envolve"
    VEICULO |o--o{ PESSOA : "transporta"
    CAUSA |o--o{ ACIDENTE : "explica (principal)"
    ACIDENTE }o--o{ CAUSA : "tem todas as causas (BAT)"
    TIPO_DE_ACIDENTE |o--o{ ACIDENTE : "classifica (ordem 1)"
    ACIDENTE }o--o{ TIPO_DE_ACIDENTE : "tem a sequência de tipos (BAT)"
    ARQUIVO_DA_PRF ||--o{ LINHA_REJEITADA : "tem"
```

Cada lote é de um ano e, portanto, de um dos dois sistemas de registro da PRF: BR-Brasil
(2007–2016) ou BAT (2017+). O acidente tem um **lugar**: o trecho (BR, UF e km) nos dois
sistemas e, no BAT, também o ponto (latitude e longitude).

Como ler: `||` é "exatamente um", `|o` é "zero ou um", `o{` é "zero ou muitos" e `|{` é
"um ou muitos". Por exemplo, uma pessoa está em **zero ou um** veículo, e um veículo
transporta **zero ou muitas** pessoas.

---

## Modelo lógico

As tabelas, as colunas e as chaves, ainda sem os tipos do PostgreSQL. **PK** é a chave
primária (identifica a linha) e **FK** a chave estrangeira (liga a outra tabela). Toda chave de
dado começa por `id_lote`, porque a mesma linha da PRF pode existir em várias versões.

```mermaid
erDiagram
    lote_carga ||--|{ lote_arquivo : "1 lote, 2 ou 3 arquivos"
    lote_carga ||--o{ ocorrencia : "id_lote, ano"
    ocorrencia ||--o{ veiculo : "id_lote, id"
    ocorrencia ||--o{ pessoa : "id_lote, id"
    veiculo |o--o{ pessoa : "id_lote, id, id_veiculo"
    causa_acidente |o--o{ ocorrencia : "id_causa"
    tipo_acidente |o--o{ ocorrencia : "id_tipo"
    ocorrencia ||--o{ ocorrencia_causa : "id_lote, id"
    causa_acidente ||--o{ ocorrencia_causa : "id_causa"
    ocorrencia ||--o{ ocorrencia_tipo : "id_lote, id"
    tipo_acidente ||--o{ ocorrencia_tipo : "id_tipo"
    lote_arquivo ||--o{ linha_rejeitada : "id_lote, dataset"

    lote_carga {
        inteiro id_lote PK
        inteiro ano
        texto sistema "br_brasil ou bat, derivado do ano"
        texto status "em_carga, concluido ou falhou"
        datahora iniciado_em
        datahora finalizado_em
    }
    lote_arquivo {
        inteiro id_lote PK, FK
        texto dataset PK "ocorrencia, pessoa ou pessoa_todas_causas"
        texto chave_manifesto
        texto arquivo
        texto sha256
        inteiro tamanho_bytes
        datahora drive_last_modified
        inteiro linhas_lidas
        inteiro linhas_rejeitadas
    }
    causa_acidente {
        inteiro id_causa PK
        texto descricao
    }
    tipo_acidente {
        inteiro id_tipo PK
        texto descricao
    }
    ocorrencia {
        inteiro id_lote PK, FK
        inteiro id PK "id do acidente na PRF"
        datahora ocorrido_em
        inteiro ano FK "derivado de ocorrido_em"
        texto uf
        inteiro br
        decimal km
        texto municipio
        decimal latitude "só BAT"
        decimal longitude "só BAT"
        ponto geom "derivado de latitude e longitude"
        inteiro id_causa FK
        inteiro id_tipo FK
        texto classificacao_acidente
        texto fase_dia
        texto sentido_via
        texto condicao_meteorologica
        texto tipo_pista
        lista tracado_via
        booleano uso_solo_urbano
        inteiro pessoas
        inteiro mortos
        inteiro feridos_leves
        inteiro feridos_graves
        inteiro feridos
        inteiro ilesos
        inteiro ignorados
        inteiro veiculos
        texto regional
        texto delegacia
        texto uop
    }
    veiculo {
        inteiro id_lote PK, FK
        inteiro id PK, FK
        inteiro id_veiculo PK
        texto tipo_veiculo
        texto marca
        inteiro ano_fabricacao
    }
    pessoa {
        inteiro id_lote PK, FK
        inteiro pesid PK
        inteiro id FK
        inteiro id_veiculo FK "vazio para pedestre, testemunha, cavaleiro"
        texto tipo_envolvido
        texto estado_fisico
        inteiro idade
        texto sexo
        texto nacionalidade "só BR-Brasil"
        texto naturalidade "só BR-Brasil"
    }
    ocorrencia_causa {
        inteiro id_lote PK, FK
        inteiro id PK, FK
        inteiro id_causa PK, FK
        booleano causa_principal
    }
    ocorrencia_tipo {
        inteiro id_lote PK, FK
        inteiro id PK, FK
        inteiro ordem PK
        inteiro id_tipo FK
    }
    linha_rejeitada {
        inteiro id_rejeicao PK
        inteiro id_lote FK
        texto dataset FK
        inteiro numero_linha
        texto linha_bruta
        texto motivo
    }
```

Decisões de normalização (detalhes em [Modelagem da origem](modelagem-origem.md)):

- O arquivo de pessoa da PRF mistura duas coisas: com `pesid = 0` a linha é um **veículo sem
  pessoa**, e com `id_veiculo = 0` é uma **pessoa sem veículo**. Por isso viram duas tabelas.
- Os dados do acidente, que se repetem em cada linha de pessoa, ficam só em `ocorrencia`.
- Causa e tipo de acidente viram tabelas de domínio, porque se repetem em 2,2 milhões de linhas.
- **Desnormalização proposital:** as contagens (`mortos`, `feridos_graves`...) ficam em
  `ocorrencia`, mesmo sendo deriváveis de `pessoa`, porque são o filtro da pergunta de gestão.
- O arquivo de todas as causas e tipos (BAT) repete causas e tipos para cada pessoa, mas o
  conteúdo é de nível de acidente: vira `ocorrencia_causa` e `ocorrencia_tipo`.
- Os dois sistemas ficam nas mesmas tabelas, com o vocabulário de cada um; o sistema está no lote.

---

## Modelo físico

O que existe no PostgreSQL com PostGIS, com os tipos, as restrições, os índices e as views.

```mermaid
erDiagram
    lote_carga ||--|{ lote_arquivo : ""
    lote_carga ||--o{ ocorrencia : ""
    ocorrencia ||--o{ veiculo : ""
    ocorrencia ||--o{ pessoa : ""
    veiculo |o--o{ pessoa : ""
    causa_acidente |o--o{ ocorrencia : ""
    tipo_acidente |o--o{ ocorrencia : ""
    ocorrencia ||--o{ ocorrencia_causa : ""
    ocorrencia ||--o{ ocorrencia_tipo : ""
    lote_arquivo ||--o{ linha_rejeitada : ""

    lote_carga {
        integer id_lote PK "identity"
        smallint ano "2007 ou mais"
        text sistema "gerada do ano"
        text status "default em_carga"
        timestamptz iniciado_em "default now()"
        timestamptz finalizado_em "nulo enquanto em_carga"
    }
    lote_arquivo {
        integer id_lote PK, FK
        text dataset PK
        text chave_manifesto
        text arquivo
        char sha256 "char(64), hexadecimal"
        bigint tamanho_bytes "maior que 0"
        timestamptz drive_last_modified
        integer linhas_lidas
        integer linhas_rejeitadas "até linhas_lidas"
    }
    causa_acidente {
        smallint id_causa PK "identity"
        text descricao UK
    }
    tipo_acidente {
        smallint id_tipo PK "identity"
        text descricao UK
    }
    ocorrencia {
        integer id_lote PK, FK
        bigint id PK "maior que 0"
        timestamp ocorrido_em "sem fuso"
        smallint ano FK "gerada de ocorrido_em"
        char uf "char(2), 27 UFs, ou nulo"
        smallint br "0 a 999, ou nulo"
        numeric km "numeric(6,1), 0 ou mais, ou nulo"
        text municipio
        numeric latitude "numeric(12,10), nula se inválida ou BR-Brasil"
        numeric longitude "numeric(13,10), nula se inválida ou BR-Brasil"
        geometry geom "Point, SRID 4674, gerada"
        smallint id_causa FK "nulo se não informado"
        smallint id_tipo FK "nulo se não informado"
        text classificacao_acidente "4 valores ou nulo"
        text tracado_via "text[], lista"
        boolean uso_solo_urbano
        smallint mortos "0 ou mais"
        smallint feridos_graves "0 ou mais"
        smallint feridos "leves mais graves"
    }
    veiculo {
        integer id_lote PK, FK
        bigint id PK, FK
        bigint id_veiculo PK "UK com id_lote"
        text tipo_veiculo
        text marca
        smallint ano_fabricacao "1900 ou mais, ou nulo"
    }
    pessoa {
        integer id_lote PK, FK
        bigint pesid PK "maior que 0"
        bigint id FK
        bigint id_veiculo FK "nulo sem veículo"
        text tipo_envolvido "10 valores, dois sistemas"
        text estado_fisico "9 valores, dois sistemas, ou nulo"
        smallint idade "nula se desconhecida"
        text sexo "nulo se ausente"
        text nacionalidade "só BR-Brasil"
        text naturalidade "só BR-Brasil"
    }
    ocorrencia_causa {
        integer id_lote PK, FK
        bigint id PK, FK
        smallint id_causa PK, FK
        boolean causa_principal "uma por ocorrência"
    }
    ocorrencia_tipo {
        integer id_lote PK, FK
        bigint id PK, FK
        smallint ordem PK "1 ou mais"
        smallint id_tipo FK
    }
    linha_rejeitada {
        bigint id_rejeicao PK "identity"
        integer id_lote FK
        text dataset FK
        integer numero_linha "UK com lote e dataset"
        text linha_bruta
        text motivo
    }
```

Em `ocorrencia`, o diagrama mostra só as colunas com restrição. As demais (`fase_dia`,
`sentido_via`, `condicao_meteorologica`, `tipo_pista`, `pessoas`, `feridos_leves`, `ilesos`,
`ignorados`, `veiculos`, `regional`, `delegacia`, `uop`) estão no modelo lógico e em
[`V0003__ocorrencia.sql`](../db/migrations/V0003__ocorrencia.sql).

**Restrições que vão além das colunas:**

| Tabela | Restrição | Garante |
|---|---|---|
| `lote_carga` | índice único parcial em `ano` com `status = 'em_carga'` | no máximo uma carga em andamento por ano |
| `ocorrencia` | FK `(id_lote, ano)` → `lote_carga` | o acidente é do ano do lote que o carregou |
| `ocorrencia` | `(latitude IS NULL) = (longitude IS NULL)` | coordenada completa ou nenhuma |
| `ocorrencia` | `feridos = feridos_leves + feridos_graves` | contagens coerentes |
| `veiculo` | `UNIQUE (id_lote, id_veiculo)` | um veículo não aparece em dois acidentes |
| `pessoa` | FK `(id_lote, id, id_veiculo)` → `veiculo` | o veículo da pessoa é do mesmo acidente |
| `ocorrencia_causa` | índice único parcial em `(id_lote, id)` com `causa_principal` | no máximo uma causa principal por acidente |

A regra "`id_veiculo` nulo ⇔ pedestre, testemunha ou cavaleiro" era um CHECK na E1. Ela não vale
no BR-Brasil (53 passageiros e 38 condutores sem veículo), então saiu do banco
(`V0010`) e continua sendo exigida pela carga para o BAT.

**Índices** (além dos das PKs):

| Índice | Colunas | Para quê |
|---|---|---|
| `ocorrencia_grave_trecho_idx` | `(id_lote, br, uf, km)`, parcial: só acidentes graves | ranking de trechos graves por ano |
| `ocorrencia_trecho_idx` | `(br, uf, km)` | detalhe de um trecho |
| `pessoa_ocorrencia_veiculo_idx` | `(id_lote, id, id_veiculo)` | as duas FKs de pessoa |
| `ocorrencia_geom_idx` | GiST em `geom`, parcial: só com ponto | contém/intersecta: polígonos (município, trecho), caixas |
| `ocorrencia_geog_idx` | GiST em `geom::geography`, parcial | distância em metros: "acidentes graves a menos de 2 km" (46 ms, contra 608 ms sem índice; ADR 0002) |

**Views** (tabelas virtuais, só leitura):

| View | Mostra |
|---|---|
| `lote_vigente` | o maior lote concluído de cada ano |
| `ocorrencia_vigente`, `veiculo_vigente`, `pessoa_vigente`, `ocorrencia_causa_vigente`, `ocorrencia_tipo_vigente` | só as linhas do lote vigente; é o que as consultas usam |

**Carimbos de tempo:** `ocorrido_em` é `timestamp` **sem fuso** (hora local do acidente; a PRF
não informa o fuso), e os de ingestão são `timestamptz` (com fuso). Os tipos são diferentes de
propósito, para a hora do acidente não ser comparada com a hora da carga.
