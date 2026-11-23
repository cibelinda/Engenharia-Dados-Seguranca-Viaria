---
title: "ADR 0006 · Disponibilização e ETL reverso"
parent: "Decisões (ADRs)"
nav_order: 6
nav_exclude: false
---

# ADR 0006: Entregar os trechos críticos à PRF de cada UF por CSV agendado, e não por tabela ou API

- **Status:** proposto (para revisão da Squad no PR da #54)
- **Data:** 2026-11-23
- **Decisores:** Ana Luiza Komatsu, Cibelly Lourenço, Maria Clara Sena
- **Issue:** #54 (métricas na #53, acesso na #52)

## Contexto

A E4 pede que ao menos uma métrica tratada **volte a um sistema onde alguém age**. No BlackSpot,
quem age sobre um trecho perigoso de rodovia federal é a **superintendência da PRF em cada UF**:
ela decide, todo mês, onde pôr viatura, onde fazer operação de fiscalização e em que trechos
pedir ao DNIT radar ou obra. Hoje essa decisão é tomada com os dados que a própria
superintendência consegue consultar, ano a ano.

O que o BlackSpot sabe e ela não tem pronto: **quais trechos de 10 km ficam entre os mais graves
do país ano após ano** (`anos_no_top_50`, da #53), e não por azar de um ano. A pergunta deste ADR
é **como esse dado chega a ela**: em que formato, quem toma a iniciativa (empurrar ou puxar), com
que frequência e o que acontece quando o destino está fora do ar.

O que pesa na decisão:

- **O dado é pequeno e muda pouco.** São 140 trechos críticos (os que ficaram no top 50 em pelo
  menos um ano), de 1 a 18 por UF, num total de 17 KB. A PRF republica uma vez por mês, então a
  lista muda no máximo uma vez por mês.
- **Cada UF só precisa da própria lista.** Privilégio mínimo (#52): a superintendência de MG não
  precisa ver a lista de SP para fazer o seu trabalho.
- **O consumidor não é técnico.** Quem planeja a operação abre uma planilha, e não escreve SQL.
- **O ETL reverso não calcula métrica** (contrato da E4): lê as tabelas de `analitico_marts` e só
  escolhe colunas e separa por UF. A definição de `anos_no_top_50` fica na camada de métricas da
  #53, num lugar só.

Restrições: custo zero; tudo no Docker Compose de uma máquina; a esteira já roda no Dagster todo
dia às 03:00 (ADR 0005).

O painel (#52) é o outro consumo da E4, e lê direto do banco, com o papel `painel_leitor`: ele é
interativo, e cada filtro vira uma consulta. Este ADR trata só da entrega para quem age.

## Alternativas

### A. Opção nula: CSV agendado, empurrado para uma pasta compartilhada

O Dagster, depois do `dbt build`, gera **um CSV por UF** (`;` e UTF-8 com BOM, para abrir no
Excel em português sem configurar nada) e um `manifesto.json` com a data, as linhas e o SHA-256
de cada arquivo. A geração nova é escrita numa pasta própria, e só no fim o link `atual` passa a
apontar para ela. A superintendência abre `atual/trechos_criticos_MG.csv`.

**A favor:** o consumidor não depende do nosso banco estar no ar, nem de credencial, nem de rede
até ele. O que ele tem é um arquivo, que continua lá se a esteira falhar. O recorte por UF é o
próprio arquivo: a permissão da pasta compartilhada de cada UF decide quem lê.

**Contra:** o dado tem a idade da última geração (até 1 dia depois do `dbt build`, e até 1 mês
depois da PRF). Cada consumidor novo com outro recorte é mais um arquivo. Não há volta: a PRF não
consegue dizer pelo mesmo caminho "fizemos operação neste trecho".

### B. Tabela no banco, que o consumidor puxa

A aplicação da superintendência consulta o banco quando precisa, com a mesma consulta do ETL,
filtrada pela UF, e um papel com acesso só às linhas da UF (recorte de linha da #52).

**A favor:** o dado é sempre o do último `dbt build`. Nada é copiado.

**Contra:** o consumidor fica acoplado ao nosso banco: precisa de rede até ele, de credencial e de
uma aplicação que saiba consultar. Se o banco cai, ou se o `dbt build` está recriando a tabela,
ele fica sem lista. E a cada consumidor novo, um papel novo no banco que mais importa proteger.

### C. API, que o consumidor puxa

Um serviço HTTP na frente do banco devolve o JSON da UF (`GET /trechos?uf=MG`).

**A favor:** o consumidor não vê o banco, só a API; a API pode autenticar por UF e mudar por
dentro sem mudar o contrato.

**Contra:** é um serviço a mais para manter no ar, com porta, autenticação e versão. Ele depende
do banco a cada requisição, então herda a indisponibilidade de B.

## Medição

Medido em 2026-11-23, dentro do container da orquestração, na mesma rede Docker que o banco, com o
banco carregado com os 20 anos e o dbt construído (incluindo a `mart_persistencia_trecho` da #53).
Consumidor medido: MG, 18 trechos críticos. Script:
[`orquestracao/medicao/medicao_adr0006.py`](../../orquestracao/medicao/medicao_adr0006.py).
Resultado: [`medicao_adr0006.json`](../../orquestracao/medicao/medicao_adr0006.json).

### Custo de entregar

| | Mediana | p95 |
|---|---|---|
| **A.** gerar e publicar os 21 CSVs e o manifesto | **21,1 ms** | 23,7 ms |
| A. a mesma execução quando o dado não mudou (não escreve nada) | 20,3 ms | 22,9 ms |
| A. a consulta sozinha, sem escrever | 19,0 ms | 19,8 ms |
| A. o consumidor abrir e ler o CSV da UF | **0,16 ms** | 0,17 ms |
| **B.** a consulta da UF, abrindo conexão nova | **18,3 ms** | 18,9 ms |
| B. a consulta da UF, com a conexão já aberta | 2,8 ms | 3,6 ms |
| **C.** uma requisição à API da UF | **18,0 ms** | 18,5 ms |

| | A. CSV | B. Tabela | C. API |
|---|---|---|---|
| Tamanho do que chega à UF | 1.368 bytes (CSV) | 18 linhas | 5.850 bytes (JSON) |
| Tamanho de uma geração inteira | 17.605 bytes, 22 arquivos | — | — |
| Serviço a mais no ar | nenhum | nenhum (o banco já está) | **35 MiB** de memória (piso: servidor da biblioteca padrão do Python) |

**O desempenho não decide.** As três opções entregam a lista de uma UF em menos de 20 ms. O custo
de gerar o CSV é o custo da consulta mais 2 ms de escrita, uma vez por dia. Com 140 linhas, nada
aqui é caro.

### O destino fora do ar

| | O que foi feito | O que aconteceu |
|---|---|---|
| **A.** pasta de destino sem permissão de escrita | o ETL rodou contra ela | **falhou em 21 ms** com "destino fora do ar"; o Dagster tenta de novo em 30, 90 e 210 s (ADR 0005); **a geração anterior continuou legível** pelo consumidor, inteira |
| **B.** banco fora do alcance | o consumidor tentou conectar (timeout de 3 s) | **esperou 3,3 s e ficou sem nada** |
| **C.** banco fora do alcance | — | o mesmo que B, depois de a API também esperar |

É aqui que as opções se separam. Em A, uma falha nossa atrasa a lista, mas não tira a lista de
quem a usa. Em B e C, qualquer falha nossa (banco parado, `dbt build` recriando a tabela,
migração) chega ao consumidor na hora.

### Empurrar ou puxar, e com que frequência

A **empurra** o arquivo para a pasta, e a superintendência **puxa** da pasta quando quer: a
esteira e o consumidor não precisam estar no ar ao mesmo tempo. O ETL roda **todo dia**, depois do
`dbt build` das 03:00, mas só escreve uma geração nova quando algum arquivo mudou (mesmo SHA-256 =
geração mantida). Com a PRF publicando uma vez por mês, isso dá cerca de uma geração por mês, e a
lista chega no máximo um dia depois da republicação. Ficam as últimas 6 gerações, cerca de meio
ano, para comparar uma lista com a anterior.

## Decisão

1. **A opção nula, A: CSV agendado por UF**, empurrado para a pasta compartilhada da PRF de cada
   UF, com manifesto e troca atômica do link `atual`. É o asset `etl_reverso_trechos_criticos` do
   Dagster ([`orquestracao/etl_reverso.py`](../../orquestracao/etl_reverso.py)), a última etapa
   da esteira diária.
2. **B e C foram descartadas pela disponibilidade e pelo acoplamento, e não pelo desempenho.**
   As três custam o mesmo (~20 ms). O que A dá e as outras não: o consumidor continua com a lista
   quando a nossa plataforma está fora do ar, não precisa de credencial no nosso banco e abre o
   dado numa planilha.
3. **Frequência: todo dia, escrevendo só quando muda.** Um consumidor que planeja o mês não ganha
   nada com um dado mais fresco que um dia, e a fonte muda uma vez por mês.
4. **Recorte por UF no arquivo**, e não no banco: cada superintendência recebe só o próprio CSV.
   É o privilégio mínimo da #52 aplicado à entrega, sem dar a ninguém de fora um papel no banco.

**Se o consumidor fosse uma aplicação que precisa do dado em tempo real, ou que precisa devolver
dado, A não bastaria.** Para uma equipe que planeja operações uma vez por mês, ela basta.

## Consequências

**O que ganhamos**

- A lista da UF chega pronta para abrir no Excel, com a descrição de cada coluna no manifesto.
- Falha da esteira não chega ao consumidor: ele continua com a última geração, e o manifesto diz
  de quando ela é.
- Nenhum serviço novo, nenhuma porta aberta, nenhum papel no banco para quem é de fora.
- Rodar de novo não duplica nada (mesmo dado = mesma geração), e as 6 últimas gerações ficam
  guardadas para comparação.

**O que perdemos**

- **O dado tem até um dia de atraso** depois do `dbt build`, e a idade fica no manifesto, e não
  no arquivo da UF: quem copia só o CSV perde a data.
- **Não há volta.** A PRF não registra pelo mesmo caminho o que fez em cada trecho, e o BlackSpot
  não fica sabendo se a lista mudou alguma coisa na rodovia.
- **A pasta compartilhada aqui é um volume do Docker** (`etl_reverso`). O destino real (uma pasta
  de rede, um Drive, um SFTP) não foi testado, e a permissão por UF fica com quem administra essa
  pasta, fora do BlackSpot.
- **Um consumidor novo com outro recorte** (o DNIT, com outras colunas) é outro arquivo ou outra
  pasta, e o módulo cresce.

**O que se torna irreversível**

- Nada no BlackSpot: o ETL só lê os marts, e trocar por tabela ou API é trocar uma etapa do
  Dagster. O que não volta é o arquivo já entregue: uma lista errada que a PRF baixou continua na
  mão dela, e por isso cada geração tem data e SHA-256 no manifesto.

## Gatilho de revisão

- **A PRF pedir o dado mais fresco que um dia**, ou a fonte passar a publicar com mais frequência
  que uma vez por dia (o mesmo gatilho do ADR 0005): rever a frequência e considerar B.
- **O consumidor precisar devolver dado** (por exemplo, "operação feita no trecho em tal data"):
  A não tem volta, e aí uma tabela ou API com escrita passa a valer o serviço a mais.
- **Mais de dois consumidores com recortes diferentes**: o número de arquivos e de pastas cresce,
  e uma API com autenticação por recorte (ou B com o recorte de linha da #52) fica mais simples de
  manter.
- **A geração passar de 1 s ou o arquivo de uma UF passar de 1 MB** (hoje 21 ms e 1,4 KB): rever
  o formato (Parquet, ou entrega incremental só do que mudou).
