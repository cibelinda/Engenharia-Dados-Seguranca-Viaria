# AI-USAGE.md — Squad [nome]

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
(PR #15), que reunia as declarações do `commits.md`. Os campos que só quem fez sabe
responder estão marcados **[a completar — nome]**. Revisores e datas vêm dos PRs no GitHub.

---

## Entradas

### 2026-09-27 — Manifesto das fontes da PRF (aquisição dos dados)

- **Ferramenta:** [a completar — Cibelly]
- **Onde:** `sources.yaml`
- **O que foi pedido:** o manifesto com os 50 arquivos da PRF, os IDs do Google Drive e o
  SHA-256 de referência de cada arquivo.
- **O que foi aproveitado:** [a completar — Cibelly]
- **Como foi verificado:** os IDs do Google Drive foram conferidos um a um, à mão, porque a
  página da PRF tem links ocultos que apontam para arquivos de outros anos
  (`docs/fontes/README.md`). [a completar — Cibelly]
- **Quem revisou:** [a completar — entrou direto na `main`, antes do fluxo por PR]

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

- **Ferramenta:** [a completar — Cibelly]
- **Onde:** `db/migrations/` e `docs/modelagem-origem.md`
- **O que foi pedido:** perfilamento, SQL das migrações e documento de modelagem, incluindo
  os ajustes pedidos na revisão do PR #13 (feitos em 2026-09-28).
- **O que foi aproveitado:** [a completar — Cibelly]
- **Como foi verificado:** na revisão, as 8 migrações foram aplicadas num banco vazio e as
  restrições foram conferidas contra os 18 arquivos do recorte. [a completar — Cibelly]
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

- **Ferramenta:** [a completar — Maria Clara]
- **Onde:** `bench/perfil_recorte.py`, `docs/caracterizacao-da-carga.md` e
  `docs/adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md`
- **O que foi pedido:** o script de perfil e o rascunho dos textos.
- **O que foi aproveitado:** [a completar — Maria Clara]
- **Como foi verificado:** os 18 SHA-256 lidos pelo perfil são iguais aos do `sources.yaml`
  de 2026-09-27; o custo do modelo foi medido com `bench/medicao_adr.py`.
  [a completar — Maria Clara]
- **Quem revisou:** Ana Luiza Komatsu (pediu ajustes) e Cibelly (PR #12)

### 2026-09-28 — Testes de esquema, restrições e versão vigente (#8, PR #17)

- **Ferramenta:** [a completar — Maria Clara]
- **Onde:** `tests/`, serviço `tests` no compose e README
- **O que foi pedido:** os testes, o serviço `tests` no compose e o README.
- **O que foi aproveitado:** [a completar — Maria Clara]
- **Como foi verificado:** os testes falham quando uma restrição é removida do banco. Na
  revisão, os 46 testes passaram.
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
- **Quem revisou:** Ana Luiza Komatsu (aprovou o PR #20); este PR: [a completar]

### 2026-09-28 — Testes de volume, distribuição, dado faltante e reprocessamento (#8, PR #21)

- **Ferramenta:** [a completar — Maria Clara]
- **Onde:** `tests/test_volume.py`, `tests/test_distribuicao.py`, `tests/test_dado_faltante.py`,
  `tests/test_reprocessamento.py`, `tests/banco.py`, serviço `tests` no compose e README
- **O que foi pedido:** os testes sobre o banco carregado, os limiares medidos na carga e o README.
- **O que foi aproveitado:** [a completar — Maria Clara]
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
