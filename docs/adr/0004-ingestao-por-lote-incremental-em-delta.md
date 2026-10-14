---
title: "ADR 0004 · Mecanismo de ingestão"
parent: "Decisões (ADRs)"
nav_order: 4
nav_exclude: false
---

# ADR 0004: Alimentar a camada analítica por lote incremental, por ano, em Delta com zstd

- **Status:** proposto (para revisão da Squad no PR da #33)
- **Data:** 2026-10-13
- **Decisores:** Ana Luiza Komatsu, Cibelly Lourenço, Maria Clara Sena
- **Issue:** #33 (lote na #31, CDC na #32)

## Contexto

A E2 leva o dado do PostgreSQL (OLTP da E1) para uma camada analítica em formato aberto, por
dois caminhos: lote e captura de mudanças (CDC). Este ADR decide **qual mecanismo alimenta a
camada analítica**, em que formato de tabela e com que compressão.

Carga, com os números do dataset completo
([caracterização](../caracterizacao-da-carga.md), [ADR 0001](0001-modelo-normalizado-insert-only-versionado-por-lote.md)):

- **Volume:** 2.243.584 ocorrências, 4.008.904 veículos, 4.998.779 pessoas, 934.079 causas e
  1.051.668 tipos na versão vigente (20 anos). O banco ocupa 2,6 GB.
- **Escrita na origem:** a PRF publica **uma vez por mês** e regrava o ano inteiro, sem versão.
  O banco é insert-only (ADR 0001): uma republicação não faz `UPDATE` nem `DELETE`, ela insere o
  ano inteiro num lote novo, numa única transação. A de 2024 são **627.797 linhas**. Não há
  escrita linha a linha.
- **Leitura analítica:** agregação de poucas colunas por trecho e ano sobre todo o histórico
  (Q1 e Q2 da pergunta de gestão). Sem acesso por chave e sem tempo real.
- **Latência tolerada: meses.** A pergunta é anual, e a fonte muda uma vez por mês.

Restrições: custo zero; tudo no Docker Compose de uma máquina; equipe de três pessoas, com SQL e
Python e sem experiência de operar Kafka; **formato aberto é requisito** da disciplina; o
armazenamento de objetos ficou de fora porque as imagens do MinIO deixaram de ser publicadas (o
`docker pull` de `minio/minio` e de `quay.io/minio/minio` é recusado). A camada analítica fica no
volume `lakehouse` do Docker.

## Alternativas

### A. Opção nula: recarga periódica completa

Agendar a cópia inteira da versão vigente, a cada mês ou a cada carga. Há duas variantes:

- **A1, dentro do banco:** `CREATE TABLE ... AS SELECT` (ou `INSERT ... SELECT`) das cinco views
  vigentes num schema analítico.
- **A2, em formato aberto:** reescrever as cinco tabelas Delta inteiras, todas as partições.

**A favor:** é a mais simples. Não há estado a controlar, e cada execução produz a camada inteira
a partir da origem. A1 é a mais rápida (11 s). Com a fonte mudando uma vez por mês, uma recarga
agendada logo depois da carga **já atende a latência tolerada com folga**.

**Contra:** A1 não é formato aberto (a camada fica presa ao PostgreSQL) e ocupa 1,4 GB, contra
132 MB em Parquet. A2 reescreve os 20 anos para mudar um, e cada execução acrescenta uma cópia
inteira (~132 MB) ao histórico do Delta.

### B. Lote incremental por partição (ano)

O serviço `ingestao-lote` ([`docs/e2/lote.md`](../e2/lote.md)): para cada tabela e cada ano,
compara o `id_lote` gravado na partição com o lote vigente do ano. Reescreve **só as partições
cujo lote mudou**, com `overwrite` + `predicate` (uma transação do Delta), e roda depois da carga.

**A favor:** tem a mesma simplicidade operacional de A (um processo Python, sem serviço a mais) e
reescreve só o ano republicado. É idempotente por construção: rodar de novo não grava nada. O
dado atrasado cai na partição do ano do evento.

**Contra:** só enxerga mudanças que criam um lote novo (ver "O que perdemos").

### C. CDC: Debezium lendo o WAL, Redpanda, consumidor gravando Delta

A parte da #32 ([`docs/e2/cdc.md`](../e2/cdc.md)). Cada `INSERT` confirmado no banco vira um
evento, e o consumidor o aplica na camada analítica.

**A favor:** é a menor latência possível, de segundos depois do commit. Pega **qualquer** mudança
no banco, inclusive uma correção manual que não passa pela carga.

**Contra:** são três serviços a mais para operar (Redpanda, Kafka Connect com Debezium e o
consumidor), com estado próprio: offsets, slot de replicação e tópicos. Um slot de replicação
parado faz o PostgreSQL reter WAL até o disco encher. E o ganho de latência não tem uso aqui: a
origem só muda quando a carga mensal termina, e então chega em bloco, com **627.797 eventos** numa
transação para republicar um ano.

## Medição

Script: [`bench/medicao_e2.py`](../../bench/medicao_e2.py). Resultado:
[`bench/resultados/medicao_e2.json`](../../bench/resultados/medicao_e2.json). Roda sobre o banco
carregado com os 20 anos, numa pasta temporária, sem tocar nas tabelas do serviço
`ingestao-lote`. Para B, o script usa as funções de `blackspot/ingestao_lote.py`.

```bash
docker compose up --build -d && docker compose wait load
docker compose run --rm --no-deps -v ./bench:/app/bench ingestao-lote sh -c \
  "pip install --user -q 'pyiceberg[sql-sqlite]==0.12.0' && python bench/medicao_e2.py"
```

Medido em 2026-10-13: PostgreSQL 18.6, deltalake 1.6.6, pyarrow 25.0.1, DuckDB 1.5.6, pyiceberg
0.12.0, numa máquina só.

### Mecanismo

| | A1: recarga no banco | A2: recarga completa em Delta | B: incremental por ano | C: CDC |
|---|---|---|---|---|
| Tempo por execução, nada mudou | 11,0 s (mediana de 3) | 82–86 s | **7,0 s**, 0 partições gravadas | sem eventos |
| Tempo para republicar 2024 | 11,0 s (tudo de novo) | 82–86 s (tudo de novo) | **3,3 s**, 5 partições, 627.797 linhas | 627.797 eventos |
| Tamanho da camada | 1.446 MB | 132 MB, 80 arquivos | 132 MB, 80 arquivos | — |
| Histórico acrescentado por republicação | nenhum (sobrescreve) | ~132 MB | **6,3 MB** | — |
| Formato aberto | não | sim | sim | sim |
| Serviços a operar | 0 (o próprio banco) | 1 processo | 1 processo | +3, com estado |
| Latência, da carga até a camada | até o próximo agendamento | até o próximo agendamento + 85 s | **3–7 s depois da carga** | segundos, ver [`cdc.md`](../e2/cdc.md) (#32) |

A latência medida do CDC fica no `docs/e2/cdc.md`, da #32.

### Compressão

Ocorrência e pessoa em Parquet particionado por ano (20 arquivos por tabela). Leitura com DuckDB,
mediana de 5 execuções depois de uma de aquecimento. A Q1 é a de `bench/medicao_adr.py`.

| Codec | Ocorrência | Pessoa | Q1 na ocorrência, mediana (mín.–máx.) | Ler 2024 inteiro |
|---|---|---|---|---|
| sem compressão | 85,9 MB | 128,9 MB | 118 ms (112–134) | 43 ms |
| snappy (padrão) | 68,6 MB | 84,0 MB | 106 ms (100–145) | 43 ms |
| **zstd nível 3** | **54,5 MB** | **53,4 MB** | 122 ms (110–155) | 47 ms |

Numa rodada anterior do mesmo script, a Q1 deu 105 / 119 / 140 ms. A diferença de leitura entre os codecs fica
dentro do ruído entre rodadas, e a escrita leva menos de 1 s em todos.

### Delta × Iceberg

| Critério | Delta (deltalake 1.6.6) | Iceberg (pyiceberg 0.12.0) |
|---|---|---|
| Ocorrência, zstd, particionada por ano | 54,5 MB | 52,4 MB, escrita em 1,0 s |
| Q1 lida pelo DuckDB, sem o motor que escreveu | 108 ms (`delta_scan`) | 79 ms (`iceberg_scan`) |
| Adicionar coluna | sim (`schema_mode="merge"`) | sim |
| Renomear coluna | **não** existe no deltalake | sim, por ID de campo, sem reescrever |
| Remover coluna | **não** existe no deltalake | sim |
| Alargar int32 → int64 | **não**: a escrita passa e a coluna continua int32, sem aviso | sim |
| Precisa de catálogo | não: a pasta é a tabela | sim (aqui, SQLite; em produção, REST, Hive ou Glue) |
| Já implementado e testado na E2 | sim (#31) | não |

## Decisão

1. **Mecanismo: B, lote incremental por ano**, como caminho que alimenta a camada analítica. Ele
   tem a simplicidade da opção nula e reescreve só o que mudou: 3,3 s e 6,3 MB por republicação,
   contra 85 s e 132 MB da recarga completa.

   A opção nula foi descartada por pouco, e não por desempenho. A1 é a mais rápida, mas não é
   formato aberto. A2 resolveria o domínio com uma latência aceitável (85 s depois de uma carga
   mensal), mas acumula uma cópia inteira no histórico a cada execução. **Se B não existisse, A2
   bastaria.**
2. **O CDC (C) é a trilha de mudanças, e não o caminho principal.** Ele existe para pegar o que B
   não vê: a mudança que não cria lote novo. Com a fonte mudando uma vez por mês, a latência de
   segundos não compra nada para a pergunta de gestão.
3. **Formato: Delta**, porque não precisa de catálogo (a pasta é a tabela, num volume do Docker,
   sem serviço a mais), o DuckDB lê sem o motor que escreveu, e já está implementado e testado.

   O critério de evolução de esquema favorece o Iceberg, e isso foi pesado. As mudanças de esquema
   que chegam à camada analítica são as **nossas** migrações das views vigentes, e até aqui elas
   só acrescentaram colunas (`V0009`–`V0012`), o que o Delta faz. Para renomear, remover ou
   alargar, a saída é reescrever a tabela inteira: 85 s.
4. **Compressão: zstd nível 3.** A leitura é por agregação de poucas colunas sobre todo o
   histórico, e o tempo de leitura medido não distingue os codecs. O que distingue é o tamanho:
   21% menor que o snappy na ocorrência e 36% na pessoa, a tabela maior.
5. **Particionamento por ano do evento**, um arquivo por partição. São 80 arquivos para as cinco
   tabelas, e cada republicação substitui um arquivo por tabela, em vez de acrescentar arquivos
   pequenos.

**Semântica de entrega de B: exatamente uma vez por lote.** Cada versão (lote) de um ano chega à
camada uma vez. Reexecutar não duplica, porque a escrita substitui a partição e não acrescenta.
Isso foi demonstrado no `lote.md`: a republicação simulada de 2024 reescreveu 5 partições e deixou
o total igual. A do CDC está no `cdc.md` (#32).

**Dado atrasado:** a republicação de um ano fechado (2024, regravado em 23/09/2026) entra na
partição do ano do evento, e não na do dia da ingestão. A versão anterior continua acessível pela
viagem no tempo do Delta.

## Consequências

**O que ganhamos**

- Uma republicação custa 3,3 s e 6,3 MB na camada analítica, em vez de 85 s e 132 MB.
- A camada inteira tem 132 MB em Parquet, contra 2,6 GB do banco, e qualquer leitor de Delta ou
  de Parquet a lê sem o PostgreSQL (o DuckDB faz a Q1 em ~0,1 s; no banco, ela leva 2,4 s pelo
  ADR 0001).
- Nenhum serviço novo para manter o caminho principal: B é um processo que roda e termina.

**O que perdemos**

- **B só enxerga mudanças que criam lote novo.** Um `UPDATE` ou `DELETE` direto no banco, fora da
  carga, não muda o `id_lote` vigente do ano, e B não reescreve a partição. A camada fica
  desatualizada sem aviso até a próxima republicação daquele ano. Quem cobre isso é o CDC.
- **Evolução de esquema no Delta, pelo deltalake:** renomear e remover coluna não existem, e
  alargar o tipo falha **em silêncio**: a escrita passa, e a coluna continua com o tipo antigo. O
  que acontece com um valor que não cabe no tipo antigo não foi testado. Uma migração que alargue
  uma coluna das views vigentes precisa vir acompanhada de uma reescrita completa da tabela.
- **zstd não acelera a leitura:** em troca do tamanho, a Q1 ficou de 4% a 34% mais lenta que sem
  compressão, conforme a rodada (de 4 a 35 ms).
- **Sem armazenamento de objetos:** a camada fica num volume local. Nenhum leitor fora da máquina
  a acessa, e não testamos o Delta sobre S3.
- **O histórico do Delta cresce 6,3 MB por republicação.** `VACUUM` libera o espaço, mas apaga a
  viagem no tempo das versões antigas. Por isso não é rodado automaticamente.

**O que se torna irreversível**

- Pouco. A camada analítica é derivada: a fonte da verdade continua no PostgreSQL insert-only
  (ADR 0001), e a camada inteira é refeita em 85 s. Trocar Delta por Iceberg, mudar a partição ou
  trocar o codec custa uma reescrita completa e a troca de `blackspot/ingestao_lote.py` e dos
  testes da #31.
- O que não volta é a **viagem no tempo** do Delta. As versões antigas da camada só existem no
  histórico do Delta e somem com um `VACUUM` ou com a troca de formato. O banco continua guardando
  cada lote, então o dado não se perde, só o atalho para lê-lo na camada.

## Gatilho de revisão

- **A fonte passar a mudar com frequência menor que um dia** (por exemplo, a PRF publicar
  diariamente) ou a Squad passar a corrigir linhas direto no banco: o CDC vira o caminho
  principal.
- **Uma migração precisar renomear, remover ou alargar coluna** numa view vigente: reavaliar o
  Iceberg, ou registrar a reescrita completa como parte da migração.
- **A republicação de um ano em B passar de 60 s**, ou a recarga completa passar de 10 min: rever
  a partição por ano (hoje 3,3 s e 85 s).
- **A Q1 lida do Parquet passar de 1 s** (hoje ~0,1 s): rever codec e nível do zstd.
- **Um consumidor da camada (E3 ou E4) não ler Delta:** rever o formato.
