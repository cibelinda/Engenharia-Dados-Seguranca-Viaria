# Base do IBGE e município

Issue #42. A ideia: ligar cada acidente da PRF a um município do IBGE, para responder também
**qual município é mais perigoso**, em acidentes graves por 100 mil habitantes.

## De onde vêm os dados

Três APIs públicas do IBGE, baixadas pelo serviço `ingestao-ibge`
([`blackspot/ibge/ingestao.py`](../../blackspot/ibge/ingestao.py)) e gravadas no schema `ibge`
do banco ([`V0013__ibge.sql`](../../db/migrations/V0013__ibge.sql)):

| Tabela | O que tem | Linhas |
|---|---|---|
| `ibge.municipio` | Código, nome e UF de cada município | 5.571 |
| `ibge.populacao` | População por município e ano: estimativas anuais e os censos de 2010 e 2022 | 133.614 (24 anos) |
| `ibge.malha_municipal` | O contorno de cada município no mapa | 5.570 |

- A ingestão roda no `docker compose up`, leva cerca de 1 a 2 minutos e **pode rodar de novo sem
  duplicar**: ela troca o conteúdo das tabelas pelo que o IBGE publica hoje (testado: as mesmas
  contagens na segunda vez).
- O IBGE não tem estimativa de população para **2007 e 2023**. Nesses anos, o ranking usa a
  população do ano mais próximo.

## Como cada acidente encontra o seu município

Modelo `int_ocorrencia_municipio` (uma linha por acidente). Três formas, nesta ordem:

1. **Pela coordenada** (2017 em diante): o ponto do acidente cai dentro do contorno de qual
   município. Usa o PostGIS.
2. **Pelo nome**: o nome do município escrito pela PRF, sem acento, sem apóstrofo e em
   maiúsculas, igual ao do IBGE na mesma UF. É o caminho de 2007–2016, que não tem coordenada.
3. **Pelo nome antigo**: municípios que **mudaram de nome**. A PRF escreveu o nome da época, e
   o IBGE só publica o atual (ex.: Embu virou Embu das Artes, Parati virou Paraty). Esses casos
   ficam numa tabela pequena e fixa, [`municipio_nome_antigo.csv`](../../dbt/seeds/municipio_nome_antigo.csv),
   com 21 nomes, e cada código foi conferido no IBGE.

| Período | Pela coordenada | Pelo nome | Pelo nome antigo | Sem município |
|---|---|---|---|---|
| 2007–2016 | — | 1.552.262 | 9.889 | **14** |
| 2017–2026 | 680.172 | 1.247 | — | **0** |

Só **14 de 2,2 milhões** de acidentes ficaram sem município: 12 vêm sem UF na PRF, e 2 vêm com a
UF errada (ex.: Nova Serrana, que é de MG, marcada como PB).

Em 46.815 acidentes de 2017 em diante (6,9%), o município da coordenada e o do nome escrito pela
PRF não batem: é comum em acidente na divisa entre municípios. Nesses casos vale a coordenada.

## As tabelas para consumo

| Tabela | Uma linha é | Para quê |
|---|---|---|
| `dim_municipio` | um município **em uma versão** | Guarda o histórico: se o nome ou a UF mudam, a versão antiga continua, com `valido_de` e `valido_ate` |
| `mart_risco_municipio_ano` | um município em um ano | Acidentes, acidentes graves, mortos, população e **graves por 100 mil habitantes**, com a posição no ranking |

A posição pela taxa só vale para municípios com **pelo menos 10 acidentes graves** no ano: abaixo
disso, um único acidente numa cidade pequena distorce o ranking.

### O histórico do município (dimensão de variação lenta)

O `dim_municipio` vem de um **snapshot** do dbt (uma "foto" da tabela de municípios a cada
execução, que só cria uma versão nova quando o nome ou a UF mudam). Teste feito num banco de
teste, trocando o nome de Paraty:

| Nome | Válido de | Válido até | Atual |
|---|---|---|---|
| Paraty | 28/10 15:13 | 28/10 15:17 | não |
| Paraty (nome novo de teste) | 28/10 15:17 | — | sim |

O nome antigo não se perde: ele ganha a data em que deixou de valer. Rodar de novo sem mudança no
IBGE não cria versão nova.

## Testes

Rodam no `docker compose run --rm dbt build`. Os que mais importam:

| Teste | O que pega |
|---|---|
| `municipio_acidente_ligado_uma_vez` | Acidente ligado a dois municípios |
| `municipio_um_atual_por_municipio` | Município com mais de uma versão "atual" no histórico |
| `municipio_uma_linha_por_ano` | Município repetido no mesmo ano do ranking |
| `municipio_volume_graves_bate_com_origem` | Acidente grave que sumiu ou foi contado duas vezes |
| `municipio_ligacao_minima` | Ano com mais de 0,5% de acidentes sem município |
| `municipio_some_entre_anos` | Número de municípios com acidente que muda mais de 15% de um ano para o outro |
| `municipio_taxa_valida` | População zero ou mais graves do que acidentes |

Mais os testes padrão do dbt: código único, UF válida e ligação entre as tabelas. **39 itens
passando** no `dbt build`.

## Como rodar

```bash
docker compose up --build -d          # sobe tudo, inclusive a ingestão do IBGE
docker compose wait load              # espera a carga da PRF
docker compose run --rm dbt build     # cria as tabelas e roda os testes (~1 min)
```
