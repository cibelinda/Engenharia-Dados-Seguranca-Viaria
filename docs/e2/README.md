# E2 — Ingestão em lote e captura de mudanças

Enunciado: [e2.md](https://github.com/UnB-BD2/PlanoEnsino/blob/main/_entregas/e2.md).
Prazo: 13/10/2026.

## Como dividimos

Cada parte é independente: cada pessoa cria a branch a partir da `main`, mexe **só nos
arquivos da sua parte**, abre o PR e pede revisão. Nenhum PR depende de outro.

| Parte | Issue | Quem | Arquivos que só ela mexe |
|---|---|---|---|
| Ingestão em lote | #31 | Ana | `compose/lote.yml`, `blackspot/ingestao_lote.py`, `tests/test_ingestao_lote.py`, [`docs/e2/lote.md`](lote.md) |
| Captura de mudanças (CDC) | #32 | Cibelly | `compose/cdc.yml`, `blackspot/cdc/`, `tests/test_cdc.py`, [`docs/e2/cdc.md`](cdc.md) |
| ADR 0004, medição e diário | #33 | Maria | `docs/adr/0004-*.md`, `bench/medicao_e2.py`, `bench/resultados/medicao_e2.json`, `diario-de-bordo.md` |

Arquivos compartilhados (`docker-compose.yml`, `requirements.txt`, `README.md`,
`_config.yml`) **não devem ser editados** nos PRs das partes: o que era comum já está na
`main`. Se faltar algo comum, avise no grupo antes de mexer.

No `AI-USAGE.md`, cada uma preenche só a própria entrada, que já está reservada no fim do
arquivo.

## O que já está pronto na `main`

- **PostgreSQL com `wal_level=logical`**, que o Debezium precisa para ler o WAL.
- **Volume `lakehouse`**, a camada analítica. Nos containers, ele fica em `/app/lake`; a
  pasta já existe na imagem com o dono certo, e o serviço `tests` a monta só para leitura.
- **`compose/lote.yml` e `compose/cdc.yml`**, incluídos no `docker-compose.yml`. Começam
  vazios; cada parte coloca ali os seus serviços. Um `docker compose up` sobe tudo junto.
- **Bibliotecas** no `requirements.txt`: `deltalake` (tabelas Delta em Python, sem Spark),
  `pyarrow` (Parquet), `confluent-kafka` (cliente do Redpanda/Kafka) e `duckdb` (consultas em
  Parquet, para conferir e medir).

## Contrato entre as partes

| Item | Valor combinado |
|---|---|
| Formato analítico | **Parquet** com tabela **Delta**, compressão `zstd` (o ADR justifica) |
| Tabelas do lote | `/app/lake/lote/ocorrencia`, `/app/lake/lote/veiculo`, `/app/lake/lote/pessoa` |
| Tabelas do CDC | `/app/lake/cdc/<tabela>` (ex.: `/app/lake/cdc/ocorrencia`) |
| Partição | por `ano` do evento (`ocorrido_em`); veículo e pessoa herdam o ano da ocorrência |
| Fonte do lote | as views `ocorrencia_vigente`, `veiculo_vigente` e `pessoa_vigente` |
| Fonte do CDC | o WAL das tabelas `lote_carga`, `ocorrencia`, `veiculo` e `pessoa` |
| Conexão com o banco | as mesmas variáveis do `load`: `PGHOST=db`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` |
| Volume nos `compose/*.yml` | declarar `volumes: { lakehouse: }` no próprio arquivo; o Compose junta com o principal |

Os serviços dos arquivos em `compose/` não herdam o bloco `x-app` do arquivo principal:
cada um declara `build: ..` e `image: blackspot-app:local`.

## Checklist de aceite da E2

| Item | Parte |
|---|---|
| Ingestão em lote da fonte pública, idempotente e reexecutável | Lote |
| Fluxo de mudanças a partir do OLTP (CDC) | CDC |
| Camada analítica em formato aberto (Parquet e Delta) | Lote e CDC |
| Semântica de entrega declarada e **demonstrada** (reprocessar o consumidor) | CDC (fluxo) e Lote (reexecução) |
| Tratamento explícito de dado atrasado e de reprocessamento de janela | Lote |
| Serialização e compressão justificadas pelo padrão de acesso | ADR |
| 1 ADR sobre o mecanismo de ingestão, com a opção nula | ADR |
| Diário de bordo das Semanas 7 a 10 | Diário |

**Sem MinIO:** as imagens da edição comunitária do MinIO deixaram de ser publicadas (o
`docker pull` de `minio/minio` e de `quay.io/minio/minio` é recusado), e o checklist pede
formato aberto, não armazenamento de objetos. As tabelas ficam no volume `lakehouse`; o ADR
registra isso.
