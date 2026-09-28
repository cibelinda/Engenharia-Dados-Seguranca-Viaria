# ADR 0001 — Modelagem do sistema de origem

**Status:** provisório (E1). Será formalizado no ADR completo da issue #6, depois da
comparação direta entre versões de arquivos (fase 2 da issue #7).
**Data:** 2026-09-27
**Implementação:** [`db/migrations/`](../../db/migrations/) (issue #3)

## Contexto

A origem do BlackSpot guarda os acidentes da PRF do recorte BAT 2017–2025
([`pergunta-e-recorte.md`](../pergunta-e-recorte.md)): 632.713 ocorrências e 1.654.197
linhas do arquivo de pessoa. A pergunta de gestão pede os trechos de 10 km com mais
acidentes com morto ou ferido grave e se eles persistem de um ano para o outro.

Três fatos da fonte pesam na modelagem ([`docs/fontes/`](../fontes/README.md)):

1. **Nenhum dos 50 arquivos tem coluna de versão**, e a PRF regrava arquivos no mesmo ID e
   com o mesmo nome, inclusive anos fechados (2024 foi regravado em 23/09/2026). A única
   identificação de versão que existe é o SHA-256 do arquivo.
2. **O arquivo de pessoa mistura duas entidades**, e cada lado tem um valor 0 que marca a
   ausência do outro.
3. **O arquivo de pessoa repete os dados do acidente e do veículo** em cada linha.

## Decisão 1 — Histórico: insert-only versionado por lote de carga

A origem **não sobrescreve**. Cada carga de um ano cria um lote (`lote_carga`), e todas as
linhas daquele ano entram de novo, marcadas com o `id_lote`. A versão vigente de cada ano
é o maior lote concluído, exposta nas views `*_vigente`.

**Por quê.** Como a PRF revisa anos fechados sem avisar e sem versionar, um esquema CRUD
apagaria justamente a evidência de que houve revisão: um trecho poderia sair do ranking
sem que ninguém conseguisse dizer se foi o trânsito que mudou ou o dado. O insert-only
"puro", sem lote, guardaria tudo mas não teria como dizer qual linha é a atual, porque a
fonte não informa. Versionar por lote resolve as duas coisas, e o custo é pequeno: um ano
tem cerca de 70 mil ocorrências e 190 mil linhas de pessoa, e só se cria lote novo quando
o SHA-256 de algum arquivo do ano muda.

**O lote é o ano, e não o arquivo.** Veículo e pessoa vêm de `acidentesAAAA.zip`; a
ocorrência vem de `datatranAAAA.zip`. Se cada arquivo fosse um lote, a FK de veículo para
ocorrência cruzaria versões diferentes do mesmo ano, e não haveria resposta certa para
"este veículo pertence a qual versão do acidente?". Por isso os dois arquivos do ano entram
juntos, e o detalhe de cada um (SHA-256, Last-Modified, linhas lidas e rejeitadas) fica em
`lote_arquivo`. Se só um dos dois mudar, o outro é recarregado igual: são no máximo cerca
de 200 mil linhas a mais.

**O que isso permite perguntar.** "O que a PRF mudou em 2024 entre as versões de
2026-03 e 2026-09?"; "o ranking de trechos de 2024 muda conforme a versão do arquivo?";
"quantas linhas cada versão rejeitou?". Com CRUD nenhuma dessas perguntas teria resposta.

**Como as chaves ficam.** Toda PK de dado começa por `id_lote`: `ocorrencia (id_lote, id)`,
`veiculo (id_lote, id, id_veiculo)`, `pessoa (id_lote, pesid)`. A unicidade vale dentro do
lote. Considerei um `UNIQUE (pesid)` parcial "só no lote vigente", mas índice parcial não
pode depender de outra tabela, e marcar a linha vigente com uma flag obrigaria a dar
UPDATE em linhas de dado, o que quebra o insert-only. A unicidade entre lotes vigentes de
anos diferentes fica garantida por construção (cada lote traz só o seu ano, reforçado pela
FK `(id_lote, ano)` de ocorrência) e deve ser verificada pela carga.

**O que muda.** A tabela de controle `lote_carga` é a única que recebe UPDATE (status
`em_carga` → `concluido` | `falhou`). Um índice parcial impede duas cargas do mesmo ano ao
mesmo tempo.

## Decisão 2 — Entidades: ocorrência, veículo e pessoa separados

Verificado nos dados do recorte (BAT 2017–2025):

| Fato | Evidência |
|---|---|
| `(id, pesid, id_veiculo)` é único | 1.654.197 linhas, nenhuma tripla repetida |
| `pesid = 0` é veículo sem pessoa | 144.628 linhas, `tipo_envolvido = NA`; 129.823 semirreboques, 11.277 reboques |
| `id_veiculo = 0` é pessoa sem veículo | 60.890 linhas: 31.209 pedestres, 29.323 testemunhas, 357 cavaleiros; `tipo_veiculo = NA` |
| Pedestre/testemunha/cavaleiro ⇔ `id_veiculo = 0` | Correspondência exata nos dois sentidos |
| `pesid ≠ 0` é global | Nenhum `pesid` aparece em duas ocorrências |
| `id_veiculo ≠ 0` é global | Nenhum `id_veiculo` aparece em duas ocorrências (o único que aparece é o 0) |
| Entre `pesid = 0`, `(id, id_veiculo)` não se repete | 144.628 linhas, 144.628 pares; nenhum par aparece também com pessoa |
| Atributos de veículo consistentes | 0 divergências em `tipo_veiculo`, `marca` e `ano_fabricacao_veiculo` dentro do mesmo `(id, id_veiculo)` |

Daí:

- **`veiculo`** recebe as linhas com `id_veiculo ≠ 0`, uma vez por veículo.
- **`pessoa`** recebe as linhas com `pesid ≠ 0`. `id_veiculo` é **NULL** para pedestre,
  testemunha e cavaleiro, e um CHECK amarra essa regra ao `tipo_envolvido`.
- **Pessoa tem duas FKs, e nenhuma é redundante.** `(id_lote, id) → ocorrencia` vale sempre;
  sem ela, um pedestre ficaria sem ocorrência, já que a FK composta para veículo não é
  verificada quando `id_veiculo` é NULL. `(id_lote, id, id_veiculo) → veiculo` garante que
  o veículo da pessoa é da mesma ocorrência.

**PK de veículo: composta, embora `id_veiculo` seja global.** A PK
`(id_lote, id, id_veiculo)` é o alvo da FK composta de pessoa. Com uma PK só em
`id_veiculo`, nada impediria uma pessoa de apontar para a ocorrência A e para um veículo da
ocorrência B. A unicidade global observada fica registrada num `UNIQUE (id_lote, id_veiculo)`:
se a PRF quebrar essa propriedade, a carga rejeita a linha em vez de aceitar um veículo
ambíguo. O custo é um índice a mais em cerca de 1,1 milhão de linhas por lote completo.

## Decisão 3 — Normalizar até onde

| Dado da fonte | Decisão | Evidência |
|---|---|---|
| Atributos do acidente repetidos em pessoa (data, hora, br, km, causa, tipo…) | Só em `ocorrencia` | Iguais aos da ocorrência em 100% das linhas |
| Binárias `ilesos/feridos_leves/feridos_graves/mortos` de pessoa | Fora; fica `estado_fisico` | São o `estado_fisico` codificado em 100% das linhas |
| `dia_semana` | Fora | Derivável de `ocorrido_em` |
| Causa e tipo de acidente | Tabelas de domínio | 91 causas e 21 tipos no recorte, repetidos em 632 mil linhas |
| `tracado_via` | `text[]` | A PRF combina valores com `;` (1.328 combinações de poucos valores) |
| **Contagens da ocorrência** (`mortos`, `feridos_graves`…) | **Mantidas (desnormalização)** | `mortos` e `feridos_graves` batem 100% com a soma de pessoa, mas são o filtro de gravidade da pergunta; recalcular exigiria agregar 1,5 milhão de linhas por consulta e impediria o índice parcial por gravidade |
| `ocorrencia.pessoas` | Mantida | **Não** é derivável: em 93.524 ocorrências é maior que o número de linhas em pessoa |

Os demais campos categóricos da ocorrência (fase do dia, condição meteorológica, tipo de
pista…) ficam como texto: têm de 2 a 10 valores e nenhuma consulta da pergunta depende deles.

## Decisão 4 — Carimbos de tempo

| Carimbo | Onde | Tipo | Observação |
|---|---|---|---|
| Hora do evento | `ocorrencia.ocorrido_em` | `timestamp` (sem fuso) | `data_inversa` + `horario` da PRF. Hora local do acidente; o fuso não é informado e o Brasil tem quatro |
| Hora de publicação na fonte | `lote_arquivo.drive_last_modified` | `timestamptz` | Last-Modified do Google Drive |
| Hora da ingestão | `lote_carga.iniciado_em` / `finalizado_em` | `timestamptz` | Toda linha chega a ela pelo `id_lote` |
| Hora de processamento | — | — | Não existe na E1: não há transformação depois da carga |

Cada tabela declara em `COMMENT ON TABLE`/`COLUMN` quais carimbos guarda. O tipo diferente
(`timestamp` × `timestamptz`) é proposital: impede tratar a hora local do acidente como se
fosse um instante absoluto comparável à hora da ingestão.

## Alternativas descartadas

| Alternativa | Por que não |
|---|---|
| CRUD (UPSERT por `id`) | Destrói a evidência das revisões da PRF, que já acontecem em anos fechados |
| Insert-only sem lote | Não há como saber qual linha é a vigente: a fonte não tem versão |
| Lote por arquivo | A FK veículo → ocorrência cruzaria versões diferentes do mesmo ano |
| Flag `vigente` nas linhas de dado | Exige UPDATE em dado; a vigência sai do `lote_carga` |
| Uma tabela larga igual ao arquivo de pessoa | Mistura pessoa e veículo, repete o acidente em cada linha e não tem chave natural sem os zeros |
| PK de veículo só em `id_veiculo` | Não garante que pessoa e veículo são da mesma ocorrência |

## Consequências

- Volume cresce a cada revisão da PRF: cerca de 70 mil ocorrências e 190 mil linhas de pessoa
  por ano recarregado. Com a frequência observada (poucas regravações por ano), é aceitável.
- Toda consulta analítica deve ler as views `*_vigente`, e não as tabelas.
- A consulta "histórico de um acidente entre versões" (`WHERE id = ?` em todos os lotes)
  não tem índice próprio hoje: as PKs começam por `id_lote`. Se a E2 precisar, entra um
  índice em `ocorrencia (id)`.
- Os CHECKs de domínio fechado (`tipo_envolvido`, `estado_fisico`, `classificacao_acidente`)
  fazem um valor novo da PRF virar linha rejeitada, e não dado silenciosamente aceito.

## Achados para a carga (issue #4)

Não resolvidos no esquema. O esquema só define o que é válido:

- **Linha com `pesid = 0` e `id_veiculo = 0`** (1 no recorte, `tipo_envolvido = NA`): não é
  pessoa nem veículo → `linha_rejeitada`.
- **IDs em notação científica:** 5 ocorrências (`1e+05`, `2e+05`, `3e+05`, `4e+05`, `6e+05`)
  e 23 linhas de pessoa → `linha_rejeitada` (o valor original não é recuperável).
- **`ano_fabricacao_veiculo = 0`** em 147.201 linhas: o esquema exige NULL para desconhecido
  (CHECK `>= 1900`). 1.900 aparece 167 vezes e pode ser outro sentinela.
- **`idade = 0`** em 147.311 pessoas e acima de 110 em 2.449 (ex.: 906, 2016): o esquema
  aceita qualquer idade `>= 0` e deixa a decisão para a carga.
- **Ausências que viram NULL:** `tipo_acidente` vazio (41), `classificacao_acidente = NA`
  (10), `regional`/`delegacia`/`uop` = `NA` ou `N/A`.
- **`br = 0`** em 1.407 ocorrências e coordenadas fora do Brasil (53) ou zeradas (14): aceitas
  como vêm; relevantes para a E3.
- Conversões: `km`, `latitude` e `longitude` com vírgula decimal; `uso_solo` Sim/Não →
  booleano; `tracado_via` separado por `;`.

## Gatilhos de revisão (para a issue #6)

- A comparação direta entre versões (issue #7, fase 2) mostrar que as regravações só
  acrescentam linhas, sem alterar as existentes: aí um insert-only por diferença pode
  substituir a recarga do ano inteiro.
- As regravações ficarem frequentes a ponto de o volume duplicado pesar.
- A PRF quebrar a unicidade global de `pesid` ou `id_veiculo`.
- O recorte passar a incluir o BR-Brasil: a chave de ocorrência precisa incluir o sistema
  de origem (490.283 IDs colidem).
