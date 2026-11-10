# AI-USAGE.md — Squad BlackSpot

Registro de uso de assistentes e agentes de IA no Projeto Integrado.

Este arquivo cumpre a [Política de Uso de IA](https://unb-bd2.github.io/Disciplina/uso-de-ia/)
da disciplina. Ele não é confissão nem formalidade: é o mesmo tipo de registro
que um ADR faz para decisões de arquitetura.

**Duas regras de forma.** Escreva **no momento do uso**, não na véspera da
Entrega — registro reconstruído de memória sai impreciso, e imprecisão aqui é o
que a política pune. E versione junto com o código: uma entrada por commit
relevante é melhor que um resumo mensal.

**Não precisa registrar** autocompletar de editor, correção ortográfica ou
tradução. Registre o que produziu artefato ou mudou uma decisão.

**Combinado da Squad (#9).** Quem usar IA num PR acrescenta a entrada neste arquivo
no mesmo PR.

As entradas de 2026-09-27 e 2026-09-28 anteriores à #7 vêm do `AI-USAGE.md` provisório
(PR #15), que reunia as declarações do `commits.md`. Os campos que só quem fez sabia
responder foram completados por cada pessoa (PRs #23, #24 e #25). Revisores e datas vêm dos
PRs no GitHub.

---

## Entradas

### 2026-09-27 — Manifesto das fontes da PRF (aquisição dos dados)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `sources.yaml`
- **O que foi pedido:** o manifesto com os 50 arquivos da PRF, os IDs do Google Drive e o
  SHA-256 de referência de cada arquivo.
- **O que foi aproveitado:** o manifesto inteiro, depois de lido e conferido.
- **Como foi verificado:** os IDs do Google Drive foram conferidos um a um, à mão, porque a
  página da PRF tem links ocultos que apontam para arquivos de outros anos
  (`docs/fontes/README.md`).
- **Quem revisou:** ninguém; entrou direto na `main` (commit `3dcbde3`), antes do fluxo por PR.

### 2026-09-27 — Recorte dos dados (#2, PR #10)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `docs/pergunta-e-recorte.md`
- **O que foi pedido:** a escolha do recorte a partir dos números do reconhecimento em
  `docs/fontes/`.
- **O que foi aproveitado:** o recorte BAT 2017–2025, conjuntos `ocorrencia` e `pessoa`, e o
  texto das justificativas e das alternativas descartadas em `docs/pergunta-e-recorte.md`.
- **Como foi verificado:** as contagens foram somadas arquivo a arquivo a partir do
  `csv_cabecalhos.json` do reconhecimento (632.713 ocorrências e 1.654.197 registros de
  pessoa), e as colunas que a pergunta usa (`br`, `km`, `uf`, `data_inversa`, `mortos`,
  `feridos_graves`) foram conferidas nos cabeçalhos. Na revisão do PR #10, a soma das
  ocorrências por ano foi conferida (632.713).
- **Quem revisou:** Maria Clara (PR #10)

### 2026-09-27 — Esteira do Docker Compose (#5, PR #11)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `docker-compose.yml`, `Dockerfile`, scripts e README
- **O que foi pedido:** a configuração do Docker, os scripts e o README, incluindo os
  ajustes pedidos na revisão do PR.
- **O que foi aproveitado:** `Dockerfile`, `.dockerignore`, `docker-compose.yml`, a migração e
  a carga provisórias e a seção "Como subir o projeto" do README.
- **Como foi verificado:** subida do zero num clone novo do GitHub, sem `.env`: os 18 arquivos
  baixados com o SHA-256 igual à referência e as contagens iguais às do reconhecimento. Uma
  segunda subida não baixou nem duplicou nada. Os 5 testes do downloader continuaram
  passando. Os ajustes da revisão (`pull_policy`, hash como aviso, tempos) foram testados de
  novo.
- **Quem revisou:** Maria Clara e Cibelly (PR #11)

### 2026-09-27 — Esquema físico (#3, PRs #13 e #16)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `db/migrations/` e `docs/modelagem-origem.md`
- **O que foi pedido:** perfilamento, SQL das migrações e documento de modelagem, incluindo
  os ajustes pedidos na revisão do PR #13 (feitos em 2026-09-28).
- **O que foi aproveitado:** as migrações e o documento de modelagem inteiros, depois de
  lidos e conferidos.
- **Como foi verificado:** na revisão, as 8 migrações foram aplicadas num banco vazio e as
  restrições foram conferidas contra os 18 arquivos do recorte.
- **Quem revisou:** Ana Luiza Komatsu (PR #13)

### 2026-09-28 — Revisão do PR #13 (esquema físico)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** revisão do PR #13
- **O que foi pedido:** a revisão do PR #13.
- **O que foi aproveitado:** a revisão inteira: a análise do esquema, os problemas apontados
  e a decisão de pedir ajustes (*Request changes*).
- **Como foi verificado:** as 8 migrações foram aplicadas num banco vazio. A coordenada
  inválida foi testada direto no Postgres (recusada pelo `CHECK` e por estouro de `numeric`).
  O impacto foi contado nos arquivos: 33 ocorrências de 2017, 8 delas graves, e 68 linhas
  de pessoa.
- **Quem revisou:** não se aplica (é uma revisão)

### 2026-09-28 — Caracterização da carga e ADR 0001 (#6, PR #12)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `bench/perfil_recorte.py`, `bench/medicao_adr.py`, `bench/resultados/`,
  `docs/caracterizacao-da-carga.md` e
  `docs/adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md`
- **O que foi pedido:** o script de perfil, a caracterização da carga, o esqueleto do ADR 0001
  e, depois da carga (#4), a medição A × C (`bench/medicao_adr.py`) e a versão final do ADR
  (decisão, perdas, irreversibilidade e gatilho de revisão). Também os ajustes pedidos nas
  revisões do PR #12.
- **O que foi aproveitado:** os dois scripts e os textos, inteiros. As métricas da medição
  (tempo da Q1 e da Q2, disco, custo de uma republicação) e os limiares do gatilho de revisão
  (2 GB, 2 s, 1% de linhas alteradas) foram sugeridos pela IA e aceitos. Mudou por pedido da
  Squad: a declaração de histórico passou de proposta a decisão tomada, e as consultas do
  ranking ganharam `WHERE br <> 0`.
- **Como foi verificado:** os 18 SHA-256 lidos pelo perfil são iguais aos do `sources.yaml`
  de 2026-09-27. Os números do perfil foram comparados com a carga da #4: 632.708 ocorrências
  (632.713 menos 5 rejeitadas) e 1.509.549 pessoas; os 9 veículos a menos aparecem só em
  linhas rejeitadas. As consultas Q1–Q3 rodaram no esquema da #3 e no banco carregado, e o
  plano (`EXPLAIN`) foi conferido para explicar por que a versão antiga quase não custa
  leitura. A conferência pegou dois erros do texto gerado, corrigidos antes do merge: "br
  válida em 100%" (há 1.407 com `br = 0`) e 1.191.471 veículos distintos (o número contava o
  `id_veiculo = 0`; o certo é 1.191.470).
- **Quem revisou:** Ana Luiza Komatsu (pediu ajustes) e Cibelly (PR #12)

### 2026-09-27 e 2026-09-28 — Revisões dos PRs #10, #11 e #18

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** revisões dos PRs #10 (pergunta e recorte), #11 (esteira do Docker Compose) e
  #18 (carga real)
- **O que foi pedido:** a revisão dos três PRs e o texto dos comentários.
- **O que foi aproveitado:** os comentários de revisão do #10 e do #11, publicados como
  estão. No #11, os pontos levantados foram a imagem desatualizada no `docker compose up`, o
  download aceitando hash divergente e os tempos inconsistentes. No #18, a conferência foi
  feita antes do merge, mas a revisão não foi registrada no GitHub.
- **Como foi verificado:** no #10, a soma das ocorrências por ano (632.713). No #11, as
  opções do downloader lidas no código. No #18, a esteira rodou do zero num projeto separado
  do Compose: contagens iguais ao perfil dos arquivos, 2.286.910 linhas lidas (o total dos
  18 arquivos), a segunda carga sem gravar nada e os 46 testes passando no banco carregado.
- **Quem revisou:** não se aplica (são revisões)

### 2026-09-28 — Testes de esquema, restrições e versão vigente (#8, PR #17)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `tests/`, serviço `tests` no compose e README
- **O que foi pedido:** os testes, o serviço `tests` no compose e o README.
- **O que foi aproveitado:** os testes (`tests/banco.py`, `test_esquema.py`,
  `test_versao_vigente.py`), o serviço `tests` e o texto do README, inteiros. A mensagem de
  commit e a descrição do PR foram lidas e aprovadas antes do commit.
- **Como foi verificado:** os testes rodaram num banco temporário com as 8 migrações. Com
  duas restrições removidas do banco (`ocorrencia_feridos_soma` e
  `lote_carga_um_em_carga_por_ano`), os dois testes correspondentes falharam. Sem banco,
  `python -m unittest discover tests` continua rodando e pula os testes de dados. Na revisão,
  os 46 testes passaram.
- **Quem revisou:** Ana Luiza Komatsu (aprovou o PR #17)

### 2026-09-28 — Revisões dos PRs #12 e #17

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** revisões dos PRs #12 e #17
- **O que foi pedido:** a revisão dos PRs #12 e #17.
- **O que foi aproveitado:** as revisões inteiras: a análise dos PRs, os pontos levantados e
  as decisões (*Approve* no #17, *Request changes* no #12).
- **Como foi verificado:** os 46 testes do #17 rodados num banco limpo, e os pontos
  pendentes do #12 conferidos nos arquivos da branch.
- **Quem revisou:** não se aplica (são revisões)

### 2026-09-28 — Carga real (#4, PR #18)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `blackspot/load.py`, regras de conversão e README
- **O que foi pedido:** o código da carga, as regras de conversão e o README.
- **O que foi aproveitado:** `blackspot/load.py` e a tabela de conversões do README. As
  regras de idade (0, negativa ou acima de 110 viram `NULL`) e de ano de fabricação (0 vira
  `NULL`) vieram da sugestão e foram aceitas.
- **Como foi verificado:** carga do zero conferida contra o perfil dos arquivos: 632.708
  ocorrências (632.713 menos 5 rejeitadas), 1.509.549 pessoas, 29 linhas rejeitadas com
  motivo e 33 coordenadas anuladas em 2017. A segunda carga não gravou nada. Os 46 testes, e
  depois os 80, passaram no banco carregado, e o teste final foi feito num clone limpo.
- **Quem revisou:** sem revisão formal no PR #18; o merge foi feito por Maria Clara

### 2026-09-28 — Evidência de revisão dos arquivos da PRF (#7, PR #19)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `docs/caracterizacao-da-carga.md`, ADR 0001 e
  `docs/fontes/linha-de-base-2026-09-27/`
- **O que foi pedido:** registrar a evidência indireta de revisão dos arquivos da PRF e
  deixar a comparação direta como pendente, sem inventar datas nem dados.
- **O que foi aproveitado:** o texto das duas seções e a cópia dos hashes de 2024–2026,
  inteiros. A busca opcional por cópias antigas (Kaggle, Base dos Dados) não foi feita, e a
  data da comparação ficou como `[DATA A DEFINIR]` para a Squad decidir.
- **Como foi verificado:** as datas de regravação e a ausência de coluna de versão foram
  conferidas contra `docs/fontes/README.md`, `sources.yaml` e `csv_cabecalhos.json`; os
  hashes foram copiados sem alteração do arquivo de 2026-09-27; o diff foi lido antes do
  commit.
- **Quem revisou:** Ana Luiza Komatsu (aprovou o PR #19)

### 2026-09-28 — Ajustes finais da E1: testes, data da #7 e este arquivo

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `tests/test_reprocessamento.py`, `tests/test_volume.py`,
  `docs/caracterizacao-da-carga.md`, ADR 0001 e o cabeçalho deste arquivo
- **O que foi pedido:** corrigir os três pontos da revisão automática do Copilot no PR #21,
  trocar o `[DATA A DEFINIR]` da comparação direta (#7) por uma data e atualizar o aviso
  sobre os campos a completar.
- **O que foi aproveitado:** as correções inteiras. O teste de reexecução passou a contar
  também `causa_acidente` e `tipo_acidente`; o de republicação compara uma impressão digital
  (MD5 das linhas, em ordem de chave) do lote antigo antes e depois, e do lote novo; a regex
  dos motivos de rejeição ficou ancorada no fim. A data 2026-10-27 foi sugerida pela IA (a
  última gravação de 2026 foi em 22/09/2026, e a atualização é mensal), mas no merge ficou a
  data que o PR #26 já tinha posto na `main`, 26/10/2026.
- **Como foi verificado:** os 80 testes passaram no banco carregado. Com um motivo de
  rejeição inventado (`pesid = 0 e id_veiculo = 0: motivo inesperado`), a regex nova apontou
  o motivo, e a antiga não. Com uma carga alterada para mudar uma linha do lote antigo sem
  mudar a contagem, o teste de republicação falhou pela impressão digital. Nada ficou
  gravado no banco.
- **Quem revisou:** Ana Luiza Komatsu (aprovou o PR #27)

### 2026-09-28 — Diário de bordo e AI-USAGE.md (#9, PR #20 e este PR)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `diario-de-bordo.md` e `AI-USAGE.md`
- **O que foi pedido:** transformar o `commits.md` num diário semanal com a entrada da
  semana 1, e passar o `AI-USAGE.md` provisório para o template da disciplina.
- **O que foi aproveitado:** o diário inteiro (PR #20). Neste arquivo, a estrutura e as
  entradas; os campos que só quem fez sabe responder ficaram marcados para cada pessoa
  completar.
- **Como foi verificado:** os números e as datas do diário foram conferidos contra os
  documentos em `docs/`; os revisores e as datas deste arquivo foram tirados dos PRs no
  GitHub.
- **Quem revisou:** Ana Luiza Komatsu (aprovou o PR #20); o PR #22 não tem revisão registrada
  no GitHub, e o merge foi feito por Cibelly.

### 2026-09-28 — Testes de volume, distribuição, dado faltante e reprocessamento (#8, PR #21)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `tests/test_volume.py`, `tests/test_distribuicao.py`, `tests/test_dado_faltante.py`,
  `tests/test_reprocessamento.py`, `tests/banco.py`, serviço `tests` no compose e README
- **O que foi pedido:** os testes sobre o banco carregado, os limiares medidos na carga e o README.
- **O que foi aproveitado:** os quatro arquivos de teste, a extensão do `tests/banco.py` e o
  texto do README, inteiros. Os limiares de distribuição (variação anual de 30%, graves 15%,
  nulos por campo) foram medidos no banco carregado e propostos pela IA; foram aceitos como
  estão, com a justificativa escrita em cada teste. A mensagem de commit e a descrição do PR
  foram lidas e aprovadas antes do commit.
- **Como foi verificado:** os testes falham quando o banco é alterado (contagem de lidas de
  2020, `regional = 'NA'`, idade 0) e passam de novo depois de desfeito. Na revisão, os 80
  testes passaram num clone limpo, duas vezes seguidas, sem deixar nada gravado no banco.
- **Quem revisou:** Ana Luiza Komatsu (aprovou o PR #21)

### 2026-09-28 — Revisões dos PRs #19, #20 e #21

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** revisões dos PRs #19, #20 e #21
- **O que foi pedido:** a revisão dos PRs #19 (evidência da #7), #20 (diário de bordo) e #21
  (testes de volume e distribuição).
- **O que foi aproveitado:** as revisões inteiras e as decisões de aprovar os três.
- **Como foi verificado:** no #19, os 9 hashes da linha de base conferidos com o arquivo do
  reconhecimento; no #20, os números do diário conferidos com os documentos; no #21, os 80
  testes rodados num clone limpo, duas vezes seguidas, sem deixar nada gravado no banco.
- **Quem revisou:** não se aplica (são revisões)

### 2026-09-28 — Campos de Cibelly e nome da Squad neste arquivo (#9)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `AI-USAGE.md`
- **O que foi pedido:** preencher os campos marcados para Cibelly, o nome da Squad e o revisor
  do PR #22, sem mexer nos campos das outras pessoas.
- **O que foi aproveitado:** o preenchimento inteiro. Ferramenta, o que foi aproveitado e o nome
  da Squad foram respondidos por Cibelly; o revisor do PR #22 e a origem do `sources.yaml`
  (commit `3dcbde3`) foram tirados do GitHub e do histórico do git.
- **Como foi verificado:** o diff foi lido antes do commit.
- **Quem revisou:** o PR #24 não tem revisão registrada no GitHub; o merge foi feito por Cibelly.

---

## E2

Cada pessoa preenche só a própria entrada abaixo, no PR da sua parte, no mesmo formato das
entradas acima. Se a parte não usou IA, escreva isso no lugar.

### Ingestão em lote — Ana Luiza Komatsu

#### 2026-10-12 — Base compartilhada da E2 (PR #34)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `docker-compose.yml`, `compose/`, `Dockerfile`, `requirements.txt`, `docs/e2/README.md`
- **O que foi pedido:** deixar pronto o que as três partes da E2 usariam em comum, para cada
  uma trabalhar sem depender do PR das outras.
- **O que foi aproveitado:** a base inteira: `wal_level=logical`, volume `lakehouse`, arquivos
  `compose/lote.yml` e `compose/cdc.yml` incluídos, bibliotecas e o contrato entre as partes. A
  troca do MinIO por um volume veio da conferência: as imagens do MinIO não puderam ser baixadas.
- **Como foi verificado:** a E1 subiu do zero com a base e os testes da época (80) passaram; a
  inclusão dos arquivos de `compose/` e o volume compartilhado foram testados antes. Depois do
  #36, a base foi atualizada com a `main` e revisada pela Maria Clara, que conferiu a esteira
  subindo.
- **Quem revisou:** Maria Clara (PR #34)

#### 2026-10-12 — Ingestão em lote (#31)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `blackspot/ingestao_lote.py`, `compose/lote.yml`, `tests/test_ingestao_lote.py`,
  `docs/e2/lote.md`
- **O que foi pedido:** a ingestão em lote do PostgreSQL para tabelas Delta, idempotente, com
  tratamento de dado atrasado, os testes e a documentação.
- **O que foi aproveitado:** o código, o serviço, os testes e o texto, inteiros, incluindo os
  ajustes pedidos na revisão (geometria em WKB, chave dos testes igual à do banco, causas e
  tipos, mudança de esquema e leitura em `REPEATABLE READ`).
- **Como foi verificado:** subida do zero com os 20 anos: 80 partições gravadas em 94 s, com as
  mesmas contagens das views vigentes; segunda execução sem gravar nada; um arquivo Parquet por
  partição, em zstd; republicação de 2024 simulada num banco de teste reescreveu só as 5
  partições de 2024, sem duplicar, com a versão anterior acessível no histórico; 107 testes
  passando (99 da `main` e 8 novos).
- **Quem revisou:** Maria Clara (PR #35)

&nbsp;

### Captura de mudanças (CDC) — Cibelly

#### 2026-10-18 — Captura de mudanças (#32)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), usado em conjunto com a Cibelly
- **Onde:** `blackspot/cdc/`, `compose/cdc.yml`, `tests/test_cdc.py`, `docs/e2/cdc.md`
- **O que foi pedido:** o CDC do PostgreSQL para tabelas Delta (Debezium e Redpanda), com o
  script que altera linhas no banco, a demonstração da semântica de entrega, a medição da
  latência, os testes e a documentação. Depois, a conferência de tudo contra a issue antes do PR.
- **O que foi aproveitado:** o trabalho foi feito em conjunto: código, serviços, testes e texto
  saíram da conversa entre a Cibelly e o assistente, com as decisões tomadas por ela. Na
  conferência, entrou a compactação das tabelas do CDC quando o consumidor fica ocioso, porque
  cada lote de mensagens gravava um arquivo (o `lote_carga` tinha 158 arquivos para 167 linhas).
- **Como foi verificado:** a esteira subiu com `docker compose up --build`, com o conector
  RUNNING; a republicação simulada de 2026 (264 mil eventos) chegou no Delta com os km alterados
  e a ocorrência removida, e o desfazer levou os DELETEs; na demonstração da semântica, o
  consumidor caiu antes de confirmar o offset, releu 2 eventos sem inserir nada, e o
  reprocessamento do início leu 1,58 milhão de eventos sem inserir nada; latência mediana de
  1,03 s (p95 1,13 s) com a compactação; 119 testes passando (12 do CDC).
- **Quem revisou:** [revisor do PR da #32]

&nbsp;

### ADR 0004, medição e diário — Maria Clara

#### 2026-10-13 — Revisão dos PRs #34 e #35

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** comentários nos PRs #34 e #35
- **O que foi pedido:** a revisão dos dois PRs da E2.
- **O que foi aproveitado:** os dois comentários, publicados como estão: no #34, o conflito no
  `_config.yml`, o número do ADR (0002 → 0004) e a contagem de testes; no #35, a quebra na coluna
  `geom`, o teste de duplicata pela chave errada, os números do recorte antigo e a referência ao
  ADR que ainda não existia, além de três pontos que não bloqueavam o merge.
- **Como foi verificado:** o #35 foi mesclado com a `main` numa worktree separada, e a esteira
  rodou do zero com os 20 anos: a ingestão parou com `RuntimeError` no tipo `USER-DEFINED`. Com
  uma correção provisória, só local, a ingestão gravou 60 partições, e os testes rodaram (105
  passaram; o de duplicata falhou nas três tabelas). As duplicatas foram contadas de novo pela
  chave primária, no banco e no Delta: zero.
- **Quem revisou:** não se aplica (é uma revisão)

#### 2026-10-13 — ADR 0004, medição e diário (#33)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `docs/adr/0004-ingestao-por-lote-incremental-em-delta.md`, `docs/adr/index.md`,
  `bench/medicao_e2.py`, `bench/resultados/medicao_e2.json` e `diario-de-bordo.md`
- **O que foi pedido:** o ADR 0004 sobre o mecanismo de ingestão, com a opção nula; a medição
  reproduzível (recarga completa, compressão, Delta × Iceberg); e o diário das Semanas 7 a 10.
- **O que foi aproveitado:** [A COMPLETAR por Maria Clara]
- **Como foi verificado:** a medição rodou no banco carregado do zero a partir da `main`, com os
  20 anos. A primeira versão do script tinha dois erros, corrigidos antes de usar os números: o
  alargamento de tipo no Delta aparecia como bem-sucedido porque o script não conferia o tipo
  depois da escrita, e a coluna nova no Iceberg falhava por um tipo do Arrow passado no lugar do
  tipo do pyiceberg. Os números do ADR foram conferidos um a um contra o `medicao_e2.json`, o
  que pegou mínimos e máximos copiados de uma rodada anterior. O diário segue o cronograma da
  disciplina (Semana 7 = 22/09).
- **Quem revisou:** [revisor do PR da #33]

---

## E3

Cada pessoa preenche só a própria entrada abaixo, no PR da sua parte, no mesmo formato das
entradas acima. Se a parte não usou IA, escreva isso no lugar.

### Base do IBGE, município e painel — Ana Luiza Komatsu

#### 2026-10-28 — Planejamento da E3, base do IBGE e painel (#42, #45, PR #46)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** divisão da E3 e base compartilhada (`docs/e3/README.md`, PR #46), base do IBGE e painel
- **O que foi pedido:** ajuda para planejar o que cada uma faria na E3, de forma que as partes
  fossem independentes, e apoio na base do IBGE (ingestão, ligação do acidente ao município,
  histórico do município, ranking) e no painel.
- **O que foi aproveitado:** a divisão das issues e o contrato entre as partes; o código e a
  documentação do IBGE e do painel, usados como apoio.
- **Como foi verificado:** o `dbt build` com os 39 itens passando; 14 de 2,2 milhões de
  acidentes sem município; o histórico testado com uma troca de nome; o painel rodado sem erro.
- **Quem revisou:** [revisora do PR]

&nbsp;

### Modelo dimensional, testes e consulta otimizada — Cibelly

#### 2026-11-09 — Modelo dimensional, testes e consulta otimizada (#43)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), usado em conjunto comigo
- **Onde:** `dbt/models/staging/stg_*.sql`, `_origem__sources.yml` e `_origem__models.yml`,
  `dbt/models/marts/trecho/`, `dbt/tests/trecho_*.sql`, `docs/e3/dbt.md` e `docs/e3/explain/`
- **O que foi pedido:** a minha parte da E3 inteira: a análise do projeto e da issue, o perfil
  do que está sujo na origem, a limpeza das views de staging sem mudar o nome das colunas, o fato
  e as três dimensões com a granularidade escrita, o `mart_risco_trecho_ano` com as colunas que o
  painel da Ana espera, os testes (esquema, volume, unicidade, integridade e distribuição), o
  `EXPLAIN (ANALYZE, BUFFERS)` antes e depois e o `docs/e3/dbt.md`.
- **O que foi aproveitado:** os modelos, os testes, os planos do `EXPLAIN` e a documentação,
  revisados por mim antes de entrar no PR. As decisões de modelagem que pesaram: o "não sei"
  vira NULL no staging, as variantes de causa são juntadas na `dim_causa` (e não no staging,
  para não perder a descrição original), a coordenada padrão do ADR 0002 é marcada no fato em
  vez de apagada, e o ranking usa `rank` com percentil porque o BR-Brasil e o BAT têm volumes
  diferentes. Também decidi, no meio do trabalho, apagar o slot de replicação do CDC
  (`blackspot_cdc`), que estava retendo 1,3 GB de WAL e enchendo o disco a cada `dbt build`; o
  aviso ficou no `dbt.md`.
- **Como foi verificado:** tudo rodou no banco carregado com os 20 anos. O `dbt build` passou com
  os 13 modelos e os 35 testes desta parte; a consulta do painel caiu de ~11 ms (seq scan, 1.496
  páginas) para ~0,07 ms (index scan, 7 páginas), em três execuções de cada; o `EXCEPT` nos dois
  sentidos deu zero diferença nas colunas do staging que a parte do IBGE usa; as consultas do
  painel rodaram direto no mart. Os limiares dos testes de distribuição saíram de medir o banco,
  e não de chute. A primeira versão tinha três erros, corrigidos antes de usar: a regra do
  `km_isolado` comparava com o trecho vizinho e deixava passar cadeias de km errado (o km 2.240
  da BR-040/MG), e o número de trechos isolados do texto (171) era o da regra antiga (são 338); o
  teste de coerência do ranking usava uma subconsulta correlacionada que seria lenta demais; e o
  teste de estado físico agrupava as 5 milhões de pessoas e estourava o disco temporário. O
  modelo `int_ocorrencia_municipio` da Ana não rodou na minha máquina por falta de disco (a
  junção espacial precisa de arquivo temporário), e não por causa desta parte.
- **Quem revisou:** [revisora do PR da #43]

&nbsp;

### Orquestração, freshness, ADR 0005 e diário — Maria Clara

#### 2026-10-28 — Revisão do PR #46

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** revisão da base compartilhada da E3 (PR #46)
- **O que foi pedido:** a revisão do PR.
- **O que foi aproveitado:** o comentário, publicado como está: o `target-path` obsoleto no
  `dbt_project.yml`, o `dbt deps` que não funciona com o projeto montado só para leitura, o
  `dbt build` que falha num banco ainda sem carga, a branch de partida contraditória entre o
  README e o PR e os comentários das views de staging. A Ana corrigiu os cinco pontos no mesmo PR.
- **Como foi verificado:** a imagem do PR foi construída e o `dbt parse` rodou com o projeto
  montado só para leitura; `pip check` sem conflito; as fontes conferidas contra as migrações.
- **Quem revisou:** não se aplica (é uma revisão)

#### 2026-11-02 — Revisão do PR #47

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** revisão da base do IBGE e do painel (PR #47)
- **O que foi pedido:** a revisão do PR e, depois, os ajustes pequenos.
- **O que foi aproveitado:** os ajustes pequenos, combinados com a Ana e feitos direto na branch
  do PR: o contrato com as colunas e os valores do `int_ocorrencia_municipio` e a pasta
  `dbt/seeds/`, a seed no schema `analitico_staging`, e a ingestão do IBGE tentando de novo quando
  a resposta não é JSON e pedindo as estimativas até o ano corrente. Ficaram de fora o número de
  divergências do `ibge.md` (não era erro: depende da carga de 2026 no banco) e o `hard_deletes`
  no snapshot (decisão da Ana). As colunas da `mart_risco_trecho_ano` que o painel espera ficaram
  para combinar com a Cibelly.
- **Como foi verificado:** o PR rodou numa cópia do banco carregado: migração, ingestão do IBGE e
  `dbt build` (39 itens passando); as contagens do `docs/e3/ibge.md` refeitas no banco; o painel
  rodou com a ferramenta de teste do Streamlit.
- **Quem revisou:** não se aplica (é uma revisão)

#### 2026-11-02 — Orquestração, freshness, ADR 0005 e diário (#44)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5)
- **Onde:** `orquestracao/`, `compose/orquestracao.yml`, `docs/e3/orquestracao.md`,
  `docs/adr/0005-dbt-e-dagster-em-vez-de-cron-com-sql.md`, `docs/adr/index.md` e
  `diario-de-bordo.md`
- **O que foi pedido:** a parte da #44: o orquestrador agendado com o grafo, o retry e o backfill
  demonstrados, a freshness e o SLA, o ADR 0005 com a opção nula e o diário das Semanas 11 a 13.
- **O que foi aproveitado:** o código da orquestração, o ADR 0005, a medição, a documentação
  e o diário, revisados antes do commit e mantidos como estão, com as demonstrações de retry
  (banco derrubado no meio do `dbt build`, API do IBGE bloqueada até esgotar as tentativas), de
  backfill (2015 e 2016) e de freshness.
- **Como foi verificado:** tudo rodou numa cópia do banco carregado com os 20 anos, junto com a
  #42: a esteira inteira, o banco derrubado no meio do `dbt build`, a API do IBGE bloqueada até
  esgotar as tentativas, o backfill de 2015 e 2016 (lotes e totais conferidos no banco, no Delta e
  na tabela de consumo) e a verificação de freshness dentro e fora do SLA. Os números do ADR e da
  documentação foram copiados do `medicao_adr0005.json` e do histórico do Dagster. A primeira
  versão tinha dois erros, corrigidos antes de usar: as esperas do retry descritas como 30, 60 e
  120 s (são 30, 90 e 210 s), e o resumo do dbt vazio na interface, porque a linha vem com o
  horário na frente.
- **Quem revisou:** [revisora do PR da #44]
