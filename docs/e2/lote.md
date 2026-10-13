# Ingestão em lote

Issue #31. Código em [`blackspot/ingestao_lote.py`](../../blackspot/ingestao_lote.py), serviço
`ingestao-lote` em [`compose/lote.yml`](../../compose/lote.yml), testes em
[`tests/test_ingestao_lote.py`](../../tests/test_ingestao_lote.py). Contrato da E2 em
[README.md](README.md).

## O que faz

Lê a **versão vigente** do banco (views `ocorrencia_vigente`, `veiculo_vigente` e
`pessoa_vigente`) e grava três **tabelas Delta** em `/app/lake/lote/`, no volume `lakehouse`:

| Tabela | Partição | Linhas | Tamanho em Parquet (zstd) |
|---|---|---|---|
| `ocorrencia` | `ano` | 632.708 | 19,8 MB |
| `veiculo` | `ano` (da ocorrência) | 1.191.461 | 10,7 MB |
| `pessoa` | `ano` (da ocorrência) | 1.509.549 | 14,6 MB |

As três somam **45 MB**, contra 731 MB das mesmas tabelas no PostgreSQL (com índices).

Cada linha leva o `id_lote` de onde veio e uma coluna nova, **`processado_em`**: a **hora de
processamento**, que não existia na E1 (lá só havia hora do evento e hora da ingestão).

## Como rodar

Faz parte do `docker compose up`: o serviço roda depois da carga (`load`).

```bash
docker compose up --build -d
docker compose wait ingestao-lote
docker compose logs ingestao-lote --no-log-prefix | tail -3
```

Para rodar só a ingestão de novo: `docker compose run --rm --no-deps ingestao-lote`.

Ler uma tabela (exemplo, dentro do container):

```python
from deltalake import DeltaTable
DeltaTable("/app/lake/lote/ocorrencia").to_pyarrow_table(filters=[("ano", "=", 2024)])
```

## Idempotência: rodar de novo não duplica

Para cada tabela e cada ano, a ingestão compara o `id_lote` gravado na partição com o
**lote vigente** do ano no banco:

- **mesmo lote:** a partição é pulada, e nada é gravado;
- **lote diferente, ou partição vazia:** a partição inteira é **substituída** (overwrite com
  `predicate = "ano = N"`). É uma única transação do Delta: ou a partição nova entra inteira,
  ou nada muda.

| Execução | Partições gravadas | Tempo |
|---|---|---|
| Primeira (banco recém-carregado) | 27 (3 tabelas × 9 anos) | 46 s |
| Segunda, sem mudança na origem | 0 (27 sem mudança) | 2 s |

Se a ingestão cair no meio, a próxima execução pula as partições que já estão com o lote
vigente e refaz só as que faltaram.

**Semântica de entrega do lote:** cada versão (lote) de um ano chega à camada analítica
**exatamente uma vez**. A reexecução é segura porque a escrita é por substituição da partição,
e não por acréscimo.

## Dado atrasado e reprocessamento de janela

A PRF republica anos já fechados: 2024 foi regravado em 23/09/2026, quase dois anos depois.
Esse é o nosso **dado atrasado**: um evento de 2024 que chega em 2026.

- A partição é pelo **ano do evento** (`ocorrido_em`), e não pelo dia da ingestão. O dado
  atrasado cai na janela certa: a republicação de 2024 vai para a partição `ano=2024`.
- A carga da E1 cria um **lote novo** para o ano, que vira o vigente. A ingestão vê o lote
  diferente e **reescreve só aquela partição**: é o reprocessamento da janela.
- A versão anterior **não se perde**: fica no histórico da tabela Delta e pode ser lida com
  `DeltaTable(caminho, version=N)` (viagem no tempo).

**Demonstração** (republicação de 2020 simulada num banco de teste, com o município de uma
ocorrência alterado):

| | Resultado |
|---|---|
| Partições reescritas | 3 (as de 2020, uma por tabela) em 7 s |
| Partições intocadas | 24 |
| Total de linhas | 632.708 antes e depois: sem duplicar |
| Arquivos na partição de 2020 | 1 |
| Versão atual da tabela | município revisado, `id_lote` novo |
| Versão anterior (viagem no tempo) | município original, `id_lote` antigo |

O teste `test_republicacao_reescreve_so_a_particao_do_ano` repete isso com uma tabela pequena.

## Arquivos e compressão

- **Um arquivo Parquet por partição** em cada execução: são 9 arquivos por tabela, e não um por
  linha ou por lote pequeno, o que evita o problema dos arquivos pequenos.
- **zstd** no lugar do snappy, que é o padrão: a leitura da pergunta de gestão agrega poucas
  colunas sobre o recorte inteiro, e o zstd comprime mais com descompressão rápida. A
  comparação medida está no ADR 0002.

## Testes

[`tests/test_ingestao_lote.py`](../../tests/test_ingestao_lote.py), rodando com
`docker compose run --rm tests` depois do `docker compose up`:

- a regra de reescrita (pula o mesmo lote, reescreve no lote novo);
- a republicação reescreve só a partição do ano, e a versão antiga continua no histórico;
- zstd e um arquivo por partição;
- nas tabelas gravadas: contagens por ano iguais às views vigentes, cada partição só com o lote
  vigente, nenhuma linha duplicada.

Se as tabelas do lote não existirem (o `docker compose up` não rodou), os testes que dependem
delas são pulados, com o motivo.

## Limites

- Um ano que deixe de existir no banco não é apagado do Delta: no nosso recorte, todo ano tem
  sempre um lote vigente.
- O histórico do Delta cresce a cada republicação (cerca de 5 MB por ano republicado, somando as
  três tabelas). Um `VACUUM` com retenção limpa versões antigas, mas acaba com a viagem no tempo
  delas; por isso não é rodado automaticamente.
