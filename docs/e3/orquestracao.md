# Orquestração, freshness e SLA

Issue #44. Orquestrador: [Dagster](https://dagster.io/) 1.13 (a escolha está no
[ADR 0005](../adr/0005-dbt-e-dagster-em-vez-de-cron-com-sql.md)). Código em
[`orquestracao/definitions.py`](../../orquestracao/definitions.py), serviço `orquestracao` em
[`compose/orquestracao.yml`](../../compose/orquestracao.yml). Contrato da E3 em [README.md](README.md).

## Como rodar

Sobe com o resto da esteira:

```bash
docker compose up --build -d
```

A interface abre em **http://localhost:3000** (para outra porta, use `ORQUESTRACAO_PORT`). Os dois
agendamentos já começam ligados. Para disparar na hora, sem esperar o horário:

```bash
# o grafo inteiro, pela fila (como o agendamento faz)
docker compose exec orquestracao dagster job launch -m orquestracao.definitions -j esteira

# backfill: reprocessar 2015 e 2016
docker compose exec orquestracao dagster job backfill -m orquestracao.definitions \
  -j reprocessar_ano --from 2015 --to 2016 --noprompt
```

Pela interface: *Jobs → esteira → Launchpad*, e *Jobs → reprocessar_ano → Partitions → Launch
backfill*.

A primeira carga continua sendo a do `docker compose up` (serviços `download` e `load`). O
orquestrador só espera as migrações e cuida das execuções seguintes. O histórico das execuções
fica no volume `orquestracao`.

## O grafo

```
arquivos_prf ──► origem_prf ──┬──► lake_lote
                              └──► camada_analitica ◄── base_ibge
                                   (dbt build)            │
                                         └── check: freshness_sla
```

| Etapa (asset) | Comando (o mesmo do serviço no compose) | Depende de |
|---|---|---|
| `arquivos_prf` | `python -m blackspot.download --force --year <ano corrente> --year <anterior>` e depois `python -m blackspot.download` | — |
| `origem_prf` | `python -m blackspot.load` | `arquivos_prf` |
| `lake_lote` | `python -m blackspot.ingestao_lote` (camada Delta da E2) | `origem_prf` |
| `base_ibge` | `python -m blackspot.ibge.ingestao` (serviço `ingestao-ibge`, #42) | — |
| `camada_analitica` | `dbt build` (modelos, snapshot, seed e testes) | `origem_prf`, `base_ibge` |

- **Dependências de verdade, e não uma fila única:** o dbt lê o PostgreSQL, e não o Delta, por
  isso espera a carga e o IBGE, mas não espera o `lake_lote`. O IBGE não depende da PRF e roda em
  paralelo com ela. Se o IBGE falhar, o Delta ainda é atualizado; o dbt não roda.
- **Por que baixar de novo o ano corrente e o anterior:** a PRF regrava os arquivos no mesmo
  endereço, e o download normal só baixa o que falta, então sozinho ele nunca veria uma
  republicação. A carga decide pelo SHA-256 se algo mudou. Na primeira execução, isso pegou uma
  republicação de verdade: 3 arquivos diferentes da referência, e um ano carregado de novo.
- **Uma execução por vez** (`run_queue.max_concurrent_runs: 1` em
  [`dagster.yaml`](../../orquestracao/dagster.yaml)): todas escrevem no mesmo banco e no mesmo
  volume. Se um agendamento cai durante outra execução, ele espera na fila.
- Cada etapa roda como processo à parte, e cada linha que ela imprime vai para o log do Dagster.

### Agendamentos

| Job | Quando | O quê |
|---|---|---|
| `esteira` | todo dia às 03:00 (Brasília) | o grafo inteiro, mais a verificação de freshness |
| `verificar_freshness` | de hora em hora, aos 15 min | só a verificação de freshness, sem reconstruir nada |
| `reprocessar_ano` | sob demanda | backfill, particionado por ano (2007–2026, lidos do `sources.yaml`) |

A PRF publica uma vez por mês, então rodar todo dia é folgado. Quando nada mudou, a carga e o
Delta não gravam nada, e a esteira leva o tempo do download do ano corrente, do IBGE e do dbt.

## Retry

Toda etapa tenta de novo **até 3 vezes**, esperando 30 s, 90 s e 210 s (backoff exponencial).
Foi testado derrubando uma dependência de propósito, de dois jeitos. Horários de Brasília, em
02/11/2026, num banco carregado com os 20 anos.

### 1. O banco cai no meio do `dbt build` e volta

`docker stop` no PostgreSQL 6 s depois de o `dbt build` começar, e `docker start` 20 s depois:

| Hora | O que aconteceu |
|---|---|
| 12:10:29 | `camada_analitica` começa (`dbt build`) |
| 12:10:35 | banco parado: `server closed the connection unexpectedly`, `the database system is shutting down` |
| 12:10:45 | o dbt termina com erro; **a etapa fica marcada para nova tentativa** (`STEP_UP_FOR_RETRY`) |
| 12:10:55 | banco religado |
| 12:11:17 | nova tentativa, 30 s depois |
| 12:12:08 | `Done. PASS=39 WARN=0 ERROR=0`; a execução termina com sucesso (166 s no total) |

Nada foi refeito à mão, e as etapas que já tinham terminado (download, carga, Delta, IBGE) não
rodaram de novo.

### 2. A API do IBGE some e não volta

Os endereços do IBGE foram apontados para `127.0.0.1`, só no container da orquestração:

| Hora | O que aconteceu |
|---|---|
| 12:12:55 | `base_ibge` começa e falha 6 s depois (conexão recusada) |
| 12:13:32, 12:15:10, 12:18:48 | as 3 novas tentativas, 30 s, 90 s e 210 s depois de cada falha; todas falham |
| 12:18:55 | `Exceeded max_retries of 3`: a etapa falha de vez |
| — | a cadeia da PRF **terminou normalmente** em paralelo (`arquivos_prf`, `origem_prf`, `lake_lote`) |
| — | `camada_analitica` **não rodou**, porque uma dependência falhou; as tabelas de consumo ficaram como estavam |

A execução termina como falha (362 s), visível na interface. A verificação de freshness das
12:15 esperou na fila e rodou às 12:18:59, logo depois. Se o IBGE continuasse fora, a idade das
tabelas de consumo passaria do SLA em 26 h, e a verificação de hora em hora falharia com ERROR.

## Backfill

O job `reprocessar_ano` é particionado por ano. Para cada ano pedido:

1. `recarregar_ano`: carrega o ano de novo, **mesmo que os arquivos não tenham mudado**
   ([`orquestracao/recarregar.py`](../../orquestracao/recarregar.py), que chama a mesma
   `carregar_ano` da carga). Com `rebaixar: true` na configuração, baixa o ano de novo antes;
2. `atualizar_lote`: a ingestão em lote vê que o lote vigente do ano mudou e reescreve só a
   partição dele;
3. `reconstruir_camada`: `dbt build`.

É o que se faz quando muda uma regra de conversão da carga e os anos antigos precisam ser
reprocessados com os mesmos arquivos. A carga normal não faz isso, porque pula o ano cujo SHA-256
não mudou. Como a origem é insert-only (ADR 0001), recarregar cria um **lote novo**, que vira o
vigente, e o anterior continua no banco.

**Executado** com 2015 e 2016 (`--from 2015 --to 2016`): duas execuções, uma por ano, uma depois
da outra pela fila.

| | 2015 | 2016 |
|---|---|---|
| Lote vigente, antes → depois | 9 → **22** | 10 → **23** |
| Lotes do ano no banco | 1 → 2 | 1 → 2 |
| Ocorrências vigentes, antes = depois | 122.158 | 96.362 |
| Recarga do ano | 16 s | 14 s |
| Execução inteira (carga, Delta e dbt) | 96 s | 91 s |
| Partição Delta da ocorrência | `id_lote` 9 → 22, 122.158 linhas | `id_lote` 10 → 23, 96.362 linhas |
| `mart_risco_municipio_ano`: graves no ano, antes = depois | 21.852 | 21.007 |

A tabela Delta da ocorrência passou da versão 19 para a 21: uma escrita por ano, e as versões
antigas continuam acessíveis pela viagem no tempo. Os 39 testes do dbt passaram nas duas
execuções. Os totais iguais antes e depois mostram que reprocessar não duplica nada.

## Freshness e SLA

**Tabelas de consumo:** as duas que o painel lê, `mart_risco_trecho_ano` (#43) e
`mart_risco_municipio_ano` (#42), em `analitico_marts`.

**Métrica (freshness):** a **idade** das tabelas de consumo, em horas desde o último `dbt build`
que terminou sem erro, pela esteira ou por um backfill.

**SLA: idade de no máximo 26 h.** A esteira roda uma vez por dia; as 2 h a mais cobrem as novas
tentativas de uma etapa que falhou (até 5,5 min) e uma execução que ficou na fila. O valor é
configurável em `ORQUESTRACAO_SLA_HORAS`.

A verificação é um *asset check* do Dagster (`freshness_sla`, em
[`orquestracao/freshness.py`](../../orquestracao/freshness.py)). Ela roda no fim de cada `esteira`
e de hora em hora pelo job `verificar_freshness`, e o resultado de cada uma fica no histórico.
Além da idade, ela registra o que ajuda a explicar um atraso:

| Campo | O que é |
|---|---|
| `idade_h` | a métrica: horas desde o último `dbt build` sem erro |
| `carga_pendente_h` | há quanto tempo existe no banco uma carga concluída que ainda não chegou às tabelas de consumo (0 = nenhuma) |
| `ultima_verificacao_prf_h` | há quanto tempo a esteira conferiu os arquivos da PRF |
| `dado_mais_recente` | o acidente mais recente no banco. Depende de quando a PRF publica, e não da esteira, por isso fica fora do SLA |
| `tabelas` | linhas de cada tabela de consumo, ou "não existe" |

| Resultado | Quando |
|---|---|
| Passou | idade dentro do SLA e as duas tabelas existem |
| **ERROR** | idade acima do SLA, ou nenhum `dbt build` terminou ainda |
| WARN | dentro do prazo, mas uma tabela de consumo não existe |

Medido em 02/11/2026, logo depois da esteira: idade de 0 h, nenhuma carga pendente, acidente mais
recente em 30/09/2026 23:30, `mart_risco_municipio_ano` com 36.454 linhas. O resultado foi
**WARN**, porque a `mart_risco_trecho_ano` (#43) ainda não estava na `main`. Para ver o ERROR,
a verificação rodou com `ORQUESTRACAO_SLA_HORAS=0.005` (18 s): `fora do SLA: idade 0.01 h >
0.005 h`.

## Limitações

- **O Dagster roda com `dagster dev`**: o servidor web e o daemon dos agendamentos ficam num
  processo só, com o histórico em SQLite. Serve para uma máquina; em produção, seriam dois
  serviços e o histórico no PostgreSQL.
- **O backfill reconstrói a camada inteira a cada ano**: o `dbt build` não é particionado. Um
  backfill de 20 anos levaria ~20 × 1,5 min. Para a pergunta de gestão (anual, com publicação
  mensal), não faz falta.
- **O SLA mede a esteira, e não a PRF.** Se a PRF parar de publicar, a idade continua dentro do
  prazo; só `dado_mais_recente` mostra isso.
- Sem alerta para fora da interface (e-mail, chat): uma falha aparece no Dagster, e só.
