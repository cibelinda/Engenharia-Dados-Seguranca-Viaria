# Ingestão em lote

Issue #31. Código em [`blackspot/ingestao_lote.py`](../../blackspot/ingestao_lote.py), serviço
`ingestao-lote` em [`compose/lote.yml`](../../compose/lote.yml), testes em
[`tests/test_ingestao_lote.py`](../../tests/test_ingestao_lote.py). Contrato da E2 em
[README.md](README.md).

## O que faz

Lê a **versão vigente** do banco (as views `*_vigente`) e grava uma **tabela Delta** para cada
uma em `/app/lake/lote/`, no volume `lakehouse`, particionada pelo **ano do acidente**. Números
medidos com os 20 anos (BR-Brasil e BAT, 2007–2026):

| Tabela | Linhas | Partições | Tamanho em Parquet (zstd) |
|---|---|---|---|
| `ocorrencia` | 2.243.584 | 20 | 52,9 MB |
| `veiculo` | 4.008.904 | 20 | 31,8 MB |
| `pessoa` | 4.998.779 | 20 | 47,1 MB |
| `ocorrencia_causa` | 934.079 | 10 (só BAT) | 3,2 MB |
| `ocorrencia_tipo` | 1.051.668 | 10 (só BAT) | 3,3 MB |
| **Total** | | | **138 MB** |

As mesmas cinco tabelas ocupam **2,7 GB** no PostgreSQL (com índices). As linhas batem com as
views vigentes, ano a ano (teste `test_contagens_por_ano_iguais_as_views_vigentes`).

Detalhes:

- **Ano:** só a ocorrência tem data; veículo, pessoa, causas e tipos recebem o ano da ocorrência.
- **Geometria:** a coluna `geom` (PostGIS) é gravada em **WKB** (`ST_AsBinary`), o formato de
  geometria do GeoParquet. Qualquer leitor recria o ponto, e `latitude` e `longitude` também
  estão na tabela.
- **Hora de processamento:** cada linha leva `processado_em`, a hora em que esta ingestão a
  gravou. Na E1 só havia hora do evento e hora da ingestão no banco.
- **Causas e tipos do BR-Brasil:** o BR-Brasil não tem esses arquivos, então essas duas tabelas
  só têm os anos do BAT. A ingestão não grava partição vazia.

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
| Primeira (banco recém-carregado, 20 anos) | 80 | 94 s |
| Segunda, sem mudança na origem | 0 (80 sem mudança) | 10 s |

Se a ingestão cair no meio, a próxima execução pula as partições que já estão com o lote
vigente e refaz só as que faltaram.

A leitura inteira acontece numa única transação `REPEATABLE READ`: todas as tabelas e todos os
anos saem do **mesmo retrato** do banco, mesmo que uma carga termine no meio da ingestão. Sem
isso, a ocorrência e a pessoa de um ano poderiam sair de lotes diferentes.

**Semântica de entrega do lote:** cada versão (lote) de um ano chega à camada analítica
**exatamente uma vez**. A reexecução é segura porque a escrita é por substituição da partição,
e não por acréscimo.

## Dado atrasado e reprocessamento de janela

A PRF republica anos já fechados: 2024 foi regravado em 23/09/2026, quase dois anos depois.
Esse é o nosso **dado atrasado**: um evento de 2024 que chega em 2026.

- A partição é pelo **ano do evento** (`ocorrido_em`), e não pelo dia da ingestão. O dado
  atrasado cai na janela certa: a republicação de 2024 vai para a partição `ano=2024`.
- A carga cria um **lote novo** para o ano, que vira o vigente. A ingestão vê o lote diferente
  e **reescreve só aquela partição**: é o reprocessamento da janela.
- A versão anterior **não se perde**: fica no histórico da tabela Delta e pode ser lida com
  `DeltaTable(caminho, version=N)` (viagem no tempo).

**Demonstração** (republicação de 2024 simulada num banco de teste com os 20 anos, com o
município de uma ocorrência alterado):

| | Resultado |
|---|---|
| Partições reescritas | 5 (as de 2024, uma por tabela) em 50 s |
| Partições intocadas | 75 |
| Total de ocorrências | 2.243.584 antes e depois: sem duplicar |
| Arquivos na partição de 2024 | 1 |
| Versão atual da tabela | município revisado, `id_lote` novo |
| Versão anterior (viagem no tempo) | município original (`TANGUA`), `id_lote` antigo |

O teste `test_republicacao_reescreve_so_a_particao_do_ano` repete isso com uma tabela pequena.

## Mudança de esquema na origem

Se uma view ganhar uma coluna (como aconteceu com `nacionalidade` na migração `V0010`), uma
tabela Delta já existente recusaria a escrita com esquema diferente (`SchemaMismatchError`). A
ingestão grava com `schema_mode="merge"`: a coluna nova entra na tabela, e as partições antigas
ficam com ela vazia até serem reescritas. O teste `test_coluna_nova_na_origem_entra_na_tabela`
cobre isso. A escolha entre Delta e Iceberg, e o que cada um garante na evolução de esquema,
fica no ADR 0004.

## Arquivos e compressão

- **Um arquivo Parquet por partição** em cada execução, e não um por linha ou por lote pequeno,
  o que evita o problema dos arquivos pequenos.
- **zstd** no lugar do snappy, que é o padrão: a leitura da pergunta de gestão agrega poucas
  colunas sobre o recorte inteiro. A comparação medida entre as compressões fica no ADR 0004.

## Testes

[`tests/test_ingestao_lote.py`](../../tests/test_ingestao_lote.py), rodando com
`docker compose run --rm tests` depois do `docker compose up`:

- a regra de reescrita (pula o mesmo lote, reescreve no lote novo);
- a republicação reescreve só a partição do ano, e a versão antiga continua no histórico;
- uma coluna nova na origem entra na tabela;
- zstd e um arquivo por partição;
- nas tabelas gravadas: contagens por ano iguais às views vigentes, cada partição só com o lote
  vigente e nenhuma linha duplicada **pela chave primária do banco** (que começa por `id_lote`,
  porque a PRF reusa IDs entre o BR-Brasil e o BAT).

Se as tabelas do lote não existirem (o `docker compose up` não rodou), os testes que dependem
delas são pulados, com o motivo.

## Limites

- Um ano que deixe de existir no banco não é apagado do Delta: no recorte, todo ano tem sempre
  um lote vigente.
- O histórico do Delta cresce a cada republicação (cerca de 7 MB por ano republicado, somando as
  cinco tabelas). Um `VACUUM` com retenção limpa versões antigas, mas acaba com a viagem no tempo
  delas; por isso não é rodado automaticamente.
