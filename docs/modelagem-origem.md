# Modelagem do sistema de origem

Documento de modelagem da issue #3: o raciocínio e a evidência por trás do esquema em
[`db/migrations/`](../db/migrations/). **Não é um ADR.** A decisão formal (histórico,
normalização e carimbos de tempo) é o ADR 0001, da issue #6, que pode citar ou incorporar
este texto.

**Data:** 2026-09-27. **Revisto em 2026-10-12** (seção "Dataset completo e banco espacial"),
depois da correção da E1: o banco passou a ser PostgreSQL com PostGIS
([ADR 0002](adr/0002-banco-espacial-postgis.md)) e a origem passou a carregar o dataset
completo da PRF ([ADR 0003](adr/0003-dataset-completo-br-brasil-e-bat.md)). As seções 1 a 4
continuam valendo; os números delas são do recorte BAT 2017–2025 da E1.

## Contexto

A origem do BlackSpot guarda os acidentes da PRF do recorte BAT 2017–2025
([`pergunta-e-recorte.md`](pergunta-e-recorte.md)): 632.713 ocorrências e 1.654.197
linhas do arquivo de pessoa. A pergunta de gestão pede os trechos de 10 km com mais
acidentes com morto ou ferido grave e se eles persistem de um ano para o outro.

Três fatos da fonte pesam na modelagem ([`docs/fontes/`](fontes/README.md)):

1. **Nenhum dos 50 arquivos tem coluna de versão**, e a PRF regrava arquivos no mesmo ID e
   com o mesmo nome, inclusive anos fechados (2024 foi regravado em 23/09/2026). A única
   identificação de versão que existe é o SHA-256 do arquivo.
2. **O arquivo de pessoa mistura duas entidades**, e cada lado tem um valor 0 que marca a
   ausência do outro.
3. **O arquivo de pessoa repete os dados do acidente e do veículo** em cada linha.

## 1. Histórico: insert-only versionado por lote de carga

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

## 2. Entidades: ocorrência, veículo e pessoa separados

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

## 3. Normalizar até onde

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

## 4. Carimbos de tempo

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
- **`idade = 0`** em 147.311 pessoas, acima de 110 em 2.449 (ex.: 906, 2016) e **negativa
  em 1** (`-1`, que o `CHECK (idade >= 0)` recusa): o esquema aceita qualquer idade `>= 0` e
  deixa a decisão para a carga.
- **Coordenada fora do limite válido** em 33 ocorrências de 2017 (ex.: longitude `-405,96`,
  latitude `-23324903`, que nem cabe em `numeric(12,10)`): a carga grava latitude e longitude
  NULL, e não rejeita a ocorrência. 8 delas são graves, com BR e km válidos, e contam para a
  pergunta de gestão.
- **Ausências que viram NULL:** `tipo_acidente` vazio (41), `classificacao_acidente = NA`
  (10), `regional`/`delegacia`/`uop` = `NA` ou `N/A`.
- **`br = 0`** em 1.407 ocorrências e, dentro do limite válido, coordenadas fora do Brasil (20),
  em (0, 0) (7) ou com só um valor zerado (7): aceitas
  como vêm; relevantes para a E3.
- Conversões: `km`, `latitude` e `longitude` com vírgula decimal; `uso_solo` Sim/Não →
  booleano; `tracado_via` separado por `;`.

## Gatilhos de revisão

- A comparação direta entre versões (issue #7, fase 2) mostrar que as regravações só
  acrescentam linhas, sem alterar as existentes: aí um insert-only por diferença pode
  substituir a recarga do ano inteiro.
- As regravações ficarem frequentes a ponto de o volume duplicado pesar.
- A PRF quebrar a unicidade global de `pesid` ou `id_veiculo`.
- ~~A E2 usar 2026~~ e ~~o recorte passar a incluir o BR-Brasil~~: os dois aconteceram em
  2026-10-12 e estão tratados na seção abaixo. A chave **não** precisou incluir o sistema de
  origem, porque toda PK começa por `id_lote` e cada lote é de um só sistema.

## Dataset completo e banco espacial (2026-10-12)

Migrações [`V0009`](../db/migrations/V0009__postgis.sql) a
[`V0012`](../db/migrations/V0012__visoes_vigentes.sql). As de `V0001` a `V0008` não foram
editadas: um banco da E1 chega ao esquema novo aplicando só as quatro novas.

### Coordenadas e PostGIS

| Fato | Evidência |
|---|---|
| O BAT publica latitude e longitude | 100% das 681.425 ocorrências de 2017–2026 |
| O BR-Brasil não publica coordenada | Nenhum dos 20 arquivos de 2007–2016 tem as colunas |
| Coordenada inválida | 33 pares fora do limite em 2017 (a carga anula); 20 pontos fora do Brasil |

Daí: `ocorrencia.geom geometry(Point, 4674)`, **coluna gerada** de `longitude`/`latitude`, com
índice GiST parcial. A carga não grava o ponto: ele não pode divergir dos números publicados.
SIRGAS 2000 (EPSG:4674) é o referencial oficial do Brasil; para medir em metros, as consultas
projetam para EPSG:5880 ou usam `geography`. O trecho (`br`, `uf`, `km`) continua sendo o
referencial comum aos 20 anos.

### Dois sistemas no mesmo esquema

Verificado nos arquivos do BR-Brasil (2007–2016):

| Fato | Evidência | No esquema |
|---|---|---|
| IDs colidem com o BAT | 490.283 | Nada muda: a PK começa por `id_lote`, e o lote é de um ano e de um sistema (`lote_carga.sistema`, gerada do ano) |
| `(null)` em `uf`, `br` e `km` | 12 ocorrências, todas com mortos/feridos contados | Colunas aceitam NULL; a ocorrência entra e sai do ranking |
| `km` negativo | 19 ocorrências (ex.: -687,4 em Garuva/SC, repetido em 2008 e 2009) | `km` NULL (a carga anula, como as coordenadas inválidas) |
| `(null)` em causa, fase do dia, condição, pista, traçado e uso do solo | 2 a 69 ocorrências por campo | Colunas aceitam NULL |
| `classificacao_acidente = 'Ignorado'` | 11.660 ocorrências | Valor aceito no CHECK |
| `id` repetido em `datatran` | 0 a 7 por ano (35 no total), com atributos diferentes (ex.: condição meteorológica) | A segunda linha vai para `linha_rejeitada`, e as pessoas dela também (`pesid repetido`) |
| Não há `pesid = 0` | Toda linha de pessoa é uma pessoa | — |
| Pessoa sem veículo é `id_veiculo` `(null)`/`NA`, não 0 | 52.250 linhas | Mesma regra: `id_veiculo` NULL |
| "Sem veículo ⇔ pedestre, testemunha, cavaleiro" **não vale** | 53 passageiros e 38 condutores sem veículo; 17 pedestres com veículo | O CHECK sai do banco; a carga continua exigindo a regra no BAT |
| Outro vocabulário de pessoa | `estado_fisico`: Ileso, Ferido Leve, Ferido Grave, Morto, Ignorado; `tipo_envolvido`: também Vítima, Autor, Ciclista, Proprietário de Carga/CNH | CHECKs com os dois vocabulários, sem harmonizar |
| Textos completados com espaços | `'Ileso       '`, `marca` | A carga tira os espaços |
| `nacionalidade` e `naturalidade` | Só no BR-Brasil | Colunas novas em `pessoa`, NULL no BAT |
| Ano de fabricação no futuro | 157 veículos (9999, 2222, 7788...) | NULL, como `idade` acima de 110 |
| Mortos e feridos graves batem com pessoa | Em todas as ocorrências menos 8 e 19, que perderam pessoas rejeitadas | Contagens mantidas em `ocorrencia`, como no BAT |

**Alternativa descartada:** um esquema por sistema. Toda consulta de 2007 a 2025 viraria um
`UNION`, e as views, os índices e os testes se duplicariam
([ADR 0003](adr/0003-dataset-completo-br-brasil-e-bat.md)).

### Todas as causas e tipos (BAT)

O arquivo `acidentesAAAA_todas_causas_tipos` tem uma linha por pessoa × causa × tipo. Medido em
2024 (603.839 linhas): as causas e os tipos são os mesmos para todas as pessoas da ocorrência,
cada ocorrência tem exatamente uma causa principal, e a causa principal e o tipo de ordem 1 são os
do arquivo de ocorrência em 100% dos casos. Por isso entram duas tabelas de nível de ocorrência,
e não uma tabela de pessoa × causa × tipo:

- `ocorrencia_causa (id_lote, id, id_causa, causa_principal)`, com no máximo uma principal por
  ocorrência (índice único parcial);
- `ocorrencia_tipo (id_lote, id, ordem, id_tipo)`.

Responde à pergunta aberta 4 do reconhecimento (a granularidade do arquivo).
