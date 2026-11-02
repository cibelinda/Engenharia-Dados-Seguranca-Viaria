---
title: "ADR 0005 · Transformação e orquestração"
parent: "Decisões (ADRs)"
nav_order: 5
nav_exclude: false
---

# ADR 0005: Transformar com dbt e orquestrar com Dagster, em vez de `cron` com scripts SQL

- **Status:** proposto (para revisão da Squad no PR da #44)
- **Data:** 2026-11-02
- **Decisores:** Ana Luiza Komatsu, Cibelly Lourenço, Maria Clara Sena
- **Issue:** #44 (modelos na #42 e na #43)

## Contexto

A E3 transforma a origem (PostgreSQL, E1) em tabelas de consumo que respondem à pergunta de
gestão, testa essas tabelas e põe tudo para rodar sozinho. Este ADR decide **com que ferramenta
as transformações são escritas e com que ferramenta a esteira é agendada**.

O que pesa na decisão:

- **Duas fontes:** a PRF (BR-Brasil 2007–2016 e BAT 2017 em diante, 2.243.584 ocorrências) e o
  IBGE (5.571 municípios, população por ano e malha municipal). As duas chegam por processos
  diferentes e são independentes até o modelo que liga o acidente ao município.
- **A origem muda pouco e em bloco:** a PRF publica uma vez por mês e regrava o ano inteiro. A
  carga é insert-only, e cada republicação vira um lote novo (ADR 0001). Desde a E1, o esquema da
  origem só ganhou colunas (`V0009`–`V0012`), e a E2 não precisou de nada além disso (ADR 0004).
- **As transformações têm camadas e dependências:** 10 views de staging, uma ligação
  acidente → município, uma dimensão com histórico (`dim_municipio`, variação lenta), o fato e as
  dimensões da #43 e as duas tabelas de consumo. A E3 pede testes de esquema, volume, unicidade,
  integridade referencial e distribuição.
- **A esteira tem cinco etapas** (download, carga, Delta da E2, IBGE, transformação) e precisa
  de agendamento, dependências, *retry*, *backfill* e uma métrica de freshness.

Restrições: custo zero; tudo no Docker Compose de uma máquina; equipe de três pessoas, com SQL e
Python. O dbt já estava na base comum da E3 (PR #46), escolhido antes deste ADR; aqui ele é
comparado com a opção nula.

## Alternativas

### A. Opção nula: `cron` com scripts SQL

Um `crontab` que chama, todo dia, um script de shell: os comandos da carga em sequência e, para
transformar, arquivos `.sql` com `CREATE TABLE ... AS` rodados pelo `psql`, em ordem fixa.

**A favor:** é a mais simples de operar. O `crond` ocupa **660 KiB** de memória, não tem
interface nem banco próprio, e qualquer pessoa da equipe lê um script de shell. Tudo o que a E3
pede **dá para fazer** assim:

- **Dependências:** a ordem das linhas do script, e `&` com `wait` para o IBGE em paralelo;
- **Retry:** um laço `for tentativa in 1 2 3; do ... && break; sleep 30; done` em volta de
  cada comando;
- **Backfill:** um parâmetro `--ano` no script;
- **Uma execução por vez:** `flock`;
- **Freshness:** uma consulta a mais no fim do script, com o horário gravado numa tabela.

**Contra:** cada uma dessas peças é código nosso, sem teste, e o que acontece fica espalhado em
arquivos de log. Não há registro de qual etapa falhou em qual tentativa, de quais anos já foram
reprocessados nem de como a freshness variou ao longo dos dias. No SQL, a ordem dos arquivos é
mantida à mão (um modelo novo no lugar errado lê a versão antiga de outro); os testes viram
consultas soltas sem relatório; e o histórico da `dim_municipio` precisaria de um `MERGE`
escrito à mão, que é exatamente onde o erro silencioso da variação lenta aparece.

### B. dbt para transformar

Modelos em SQL com `ref()`, que dá a ordem; materialização por camada (view, table) em schemas
separados; testes declarados em YAML; `snapshot` para a variação lenta.

**A favor:** a ordem sai das próprias referências entre os modelos. Os 24 testes de dados da
#42 cabem em YAML e SQL curtos, e o `dbt build` para no primeiro teste que falha, antes de
construir o que depende dele. O histórico do município é um `snapshot` de 9 linhas.

**Contra:** é uma dependência a mais, com custo fixo por execução (ler e compilar o projeto
inteiro antes de mandar SQL ao banco). A versão também precisa de atenção: a restrição do
`dbt-postgres 1.11.0` (`dbt-core>=1.8.0rc1`) deixa o `pip` instalar uma versão beta, a
`1.13.0b1`, e foi ela que rodou todas as medições abaixo.

### C. Dagster para orquestrar

Cada etapa é um *asset* com as dependências declaradas; *retry* por política; jobs
particionados por ano para o *backfill*; *asset checks* para a freshness; fila de execuções; e
uma interface com o histórico de tudo. Roda num container (`dagster dev`: servidor web e daemon
num processo só), com o histórico em SQLite num volume.

### D. Airflow para orquestrar

O mesmo papel de C, com DAGs de tarefas. É o orquestrador mais usado, mas o modelo é de tarefas,
e não de dados: a freshness e o "o que esta tabela tem agora" são coisas que se constroem por
fora.

SQLMesh, a outra ferramenta de transformação citada no enunciado, não foi medida: o dbt já estava
na base comum (PR #46), e as partes da #42 e da #43 foram escritas sobre ele.

## Medição

Medido em 2026-11-02, numa máquina só, com o banco carregado com os 20 anos e as tabelas do IBGE.

### O custo do dbt sobre o SQL puro

Script: [`orquestracao/medicao/medicao_adr0005.py`](../../orquestracao/medicao/medicao_adr0005.py).
Resultado: [`medicao_adr0005.json`](../../orquestracao/medicao/medicao_adr0005.json). O projeto
medido é o da `main` mais a #42: 13 modelos, 1 seed, 1 snapshot e 24 testes (39 nós), em 4
threads. O dbt registra o tempo do SQL de cada nó.

| | 3 rodadas | Mediana |
|---|---|---|
| `dbt build` inteiro | 54,4 / 52,1 / 51,2 s | **52,1 s** |
| SQL dos modelos, seed e snapshot (somado) | 50,5 / 48,3 / 47,6 s | 48,3 s |
| SQL dos testes (somado) | 6,3 / 5,6 / 6,1 s | 6,1 s |
| `dbt parse` sem cache (ler e compilar o projeto) | 5,19 / 5,16 / 5,18 s | **5,2 s** |

O SQL é o mesmo que um script rodaria. O que a opção nula economiza é o custo fixo do dbt antes
do primeiro comando ao banco: **5,2 s por execução, 10% do build**, numa esteira que roda uma vez
por dia. O modelo mais caro, a ligação acidente → município (28 s, busca espacial em 2,2 milhões
de pontos), custaria o mesmo nas duas.

### O custo do orquestrador

Cada orquestrador parado, sem nenhuma execução, depois de 60 s no ar. O Dagster é a imagem do
serviço `orquestracao`; o Airflow é a imagem oficial *slim* 3.3.2 com Python 3.10, em
`airflow standalone` (o equivalente ao `dagster dev`), sem DAGs nem as bibliotecas do projeto.

| | `cron` (BusyBox) | Dagster 1.13.28 | Airflow 3.3.2 |
|---|---|---|---|
| Memória parado | **660 KiB** | 481 MiB | 966 MiB |
| Processos | 1 | 70 | 58 |
| Do `docker run` até a interface responder | — | **7,2 s** | 15,5 s |
| Imagem | — | 1,41 GB (a do projeto, 1,23 GB, + 180 MB) | 1,10 GB, ainda sem as bibliotecas do projeto |

### A esteira no Dagster

O grafo e as demonstrações estão em [`docs/e3/orquestracao.md`](../e3/orquestracao.md).

| | Resultado |
|---|---|
| Primeira execução (1 ano republicado, 80 partições Delta gravadas do zero) | 151 s |
| Execução com o banco derrubado no meio do `dbt build` | 166 s, com a nova tentativa 30 s depois da falha, sem intervenção |
| Execução com a API do IBGE fora do ar | falha depois de 3 tentativas (362 s); a cadeia da PRF termina, e o dbt não roda |
| Backfill de 2015 e 2016 | 96 s e 91 s, uma execução por ano, totais iguais antes e depois |
| Tempo entre uma etapa e a seguinte | 1 a 3 s |

## Decisão

1. **Transformação em dbt (B).** São 5,2 s por execução, e em troca a ordem das transformações
   sai das referências, os testes param a esteira antes de uma tabela de consumo errada, e o
   histórico da `dim_municipio` é um `snapshot` em vez de um `MERGE` escrito à mão.
2. **Orquestração em Dagster (C).** Ele cobre, sem código nosso, o que a E3 pede e o `cron`
   obrigaria a escrever: retry por etapa, backfill particionado com o registro de cada ano,
   freshness com histórico e uma fila que impede duas execuções juntas. Usa metade da memória do
   Airflow e sobe na metade do tempo. A orientação a dados (*assets*) combina com o que a esteira
   produz: tabelas, e não tarefas.
3. **A opção nula foi descartada pelo registro, e não pelo desempenho.** O `cron` faria o mesmo
   trabalho com 660 KiB em vez de 481 MiB, e o retry, o backfill e a freshness caberiam em algumas
   dezenas de linhas de shell. O que falta nele é ver o que aconteceu: qual etapa falhou, em qual
   tentativa, que anos foram reprocessados, quando, e como a idade das tabelas variou.
   **Com uma pessoa só e sem precisar mostrar o backfill e o retry, o `cron` bastaria.**

## Consequências

**O que ganhamos**

- Retry, backfill e freshness demonstrados, com o histórico de cada execução na interface.
- Um modelo novo entra na ordem certa sozinho, pelo `ref()`, e é testado no mesmo `dbt build`.
- As dependências são as reais: o IBGE roda em paralelo com a PRF, e o Delta da E2 não espera o
  dbt. Uma falha no IBGE não impede o Delta de ser atualizado.

**O que perdemos**

- **481 MiB de memória** e um serviço a mais no compose, com estado próprio (o histórico, no
  volume `orquestracao`).
- **5,2 s por execução** para o dbt ler o projeto, e uma dependência que precisa ter a versão
  fixada: sem fixar o `dbt-core`, o `pip` instala uma versão beta.
- **O backfill não é incremental na transformação:** cada ano reprocessado roda o `dbt build`
  inteiro (~1 min). Para tornar incremental, os modelos teriam de ser particionados por ano.
- **`dagster dev` não é para produção:** servidor e daemon num processo, histórico em SQLite.
  Serve para uma máquina; com mais de uma, seriam dois serviços e o histórico no PostgreSQL.

**Quando revisar**

- Se a esteira precisar rodar em mais de uma máquina ou com mais de uma execução ao mesmo tempo.
- Se o `dbt build` passar de alguns minutos: aí vale tornar os modelos grandes incrementais, ou
  particionar a transformação por ano junto com o backfill.
- Se a fonte passar a publicar com mais frequência que uma vez por dia: o agendamento diário e o
  SLA de 26 h deixam de servir.
