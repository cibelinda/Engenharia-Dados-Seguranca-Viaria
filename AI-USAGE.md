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
