# Pergunta de gestão e recorte dos dados

Decisões das issues #1 e #2, revistas em 2026-10-12 depois da correção da E1: o banco passou a
ser espacial ([ADR 0002](adr/0002-banco-espacial-postgis.md)) e o recorte BAT 2017–2025 foi
substituído pelo dataset completo da PRF ([ADR 0003](adr/0003-dataset-completo-br-brasil-e-bat.md)).
Os números vêm do reconhecimento de 2026-09-27 ([`docs/fontes/`](fontes/README.md)) e do perfil
do dataset completo ([`perfil_dataset_completo.json`](../bench/resultados/perfil_dataset_completo.json)).

## Pergunta de gestão

> **Quais trechos de 10 km das rodovias federais concentraram mais acidentes com mortos ou
> feridos graves entre 2007 e 2025, e esses trechos se mantêm de um ano para o outro?**

| Elemento | Valor |
|---|---|
| Objeto analisado | Trecho de rodovia federal: BR + UF + faixa de 10 km (ex.: BR-040/GO, km 0–10) |
| Recorte geográfico | Todas as rodovias federais do Brasil |
| Recorte temporal | 2007 a 2025 (os 19 anos completos; 2026 é parcial) |
| Medida | Número de acidentes com ao menos um morto ou ferido grave por trecho e por ano; persistência do trecho entre os mais graves ao longo dos anos |
| Complemento espacial (2017+) | Ponto de cada acidente (PostGIS): onde, dentro do trecho, os acidentes graves se concentram |

### Por que esta pergunta

- **Responde ao objetivo do projeto.** Um *black spot* é um trecho de via onde os acidentes se
  concentram. A pergunta pede exatamente esses trechos.
- **Mede gravidade, não só quantidade.** Quem decide onde fiscalizar ou fazer obra prioriza
  onde há morte e lesão grave. Contar todos os acidentes mistura colisões sem vítima com
  acidentes fatais. As colunas `mortos` e `feridos_graves` existem em todas as ocorrências do
  BAT.
- **Usa BR + km como referencial comum, e a coordenada como refinamento.** `br` e `km` existem
  nos 20 anos; `latitude` e `longitude` existem em 100% das ocorrências do BAT (2017+), mas em
  nenhuma do BR-Brasil. O trecho de 10 km é o único objeto comparável de 2007 a 2025; dentro
  dele, a partir de 2017, o PostGIS localiza o ponto negro
  ([ADR 0002](adr/0002-banco-espacial-postgis.md)). Cuidado: de 2019 a 2024, metade das
  coordenadas é um ponto padrão repetido, e não o local do acidente (medido no ADR 0002).
- **A persistência separa o ponto negro do acaso.** Um trecho que aparece entre os mais graves
  em um único ano pode ser flutuação; um que se repete ano após ano é o que justifica
  intervenção. Com o dataset completo, são 19 anos para medir isso, e não 9.

### Alternativas descartadas

| Pergunta | Por que não |
|---|---|
| "Quais UFs ou municípios têm mais acidentes?" | Não localiza o trecho, que é o objeto de um *black spot*. O município vem só pelo nome, sem código IBGE. |
| "Quais as principais causas de acidente?" | Não diz onde agir. No arquivo de ocorrência do BAT só vem a causa principal. |
| "Quais trechos têm mais acidentes?" (sem gravidade) | Trata igual uma colisão sem vítima e um acidente fatal. |
| Agrupar só por coordenada (latitude/longitude) | As coordenadas não existem antes de 2017: a pergunta perderia 10 dos 19 anos. Elas entram como complemento do trecho, não como substituto. |

### Decidido depois

- **Ocorrências com `br = 0`** (1.581 no dataset completo, 1.507 delas no BAT; rodovia não
  identificada) ficam no banco, mas saem do ranking de trechos: sem a BR, não dá para montar o
  trecho. O mesmo vale para as 12 ocorrências do BR-Brasil com `uf`, `br` e `km` ausentes e as
  19 com `km` negativo, que a carga grava com NULL. As consultas usam
  `WHERE br <> 0 AND km IS NOT NULL` (`br <> 0` já exclui `br` NULL).
- **Acidente grave é o que tem `mortos > 0` ou `feridos_graves > 0`**, e não o que vem em
  `classificacao_acidente` (pergunta aberta 5 do reconhecimento). No banco carregado
  (`ocorrencia_vigente`, BAT 2017–2025), a classificação é derivada das próprias contagens:

  | `classificacao_acidente` | Ocorrências | Com morto | Sem morto, com ferido grave | Só ferido leve | Sem ferido |
  |---|---|---|---|---|---|
  | Com Vítimas Fatais | 43.437 | 43.437 | 0 | 0 | 0 |
  | Com Vítimas Feridas | 462.962 | 0 | 125.394 | 337.568 | 0 |
  | Sem Vítimas | 126.299 | 0 | 0 | 0 | 126.299 |
  | `NULL` (`NA` na fonte) | 10 | 1 | 3 | 3 | 3 |

  No BR-Brasil (2007–2016) vale o mesmo, e `Ignorado` aparece só em ocorrências sem ferido:

  | `classificacao_acidente` | Ocorrências | Com morto | Sem morto, com ferido grave | Só ferido leve | Sem ferido |
  |---|---|---|---|---|---|
  | Com Vítimas Fatais | 62.851 | 62.851 | 0 | 0 | 0 |
  | Com Vítimas Feridas | 580.373 | 0 | 178.820 | 401.553 | 0 |
  | Sem Vítimas | 907.257 | 0 | 0 | 0 | 907.257 |
  | Ignorado | 11.660 | 0 | 0 | 0 | 11.660 |
  | `NULL` (`(null)` na fonte) | 24 | 1 | 2 | 4 | 17 |

  De 2007 a 2025, as contagens dão 410.509 acidentes graves em 2.194.873 (18,7%).

  "Com Vítimas Fatais" equivale a `mortos > 0`, mas "Com Vítimas Feridas" mistura ferido grave
  e ferido leve: 73% dessas ocorrências só têm feridos leves. Usar a classificação contaria
  80% das ocorrências como graves; as contagens dão 168.835 (26,7%), exatamente o "morto ou
  ferido grave" da pergunta. As contagens também classificam as 10 ocorrências sem
  classificação, 4 delas graves. `mortos` e `feridos_graves` batem 100% com a soma dos
  registros de pessoa ([`modelagem-origem.md`](modelagem-origem.md)), e a migração `V0007`
  já tem o índice parcial com esse filtro.

### O que ainda precisa ser definido

- **O tamanho do trecho (10 km) é um parâmetro, não um dado.** Trechos curtos demais deixam
  poucos acidentes por trecho e ano; longos demais diluem o ponto negro. O valor pode ser
  recalibrado na E3 com o dado carregado.
- **O critério de persistência**: o que conta como um trecho que "se mantém" entre os mais
  graves. Pode ser estar entre os N piores de cada ano, acima de um percentil, ou aparecer em
  um número mínimo dos 19 anos. A escolha é da Squad e fica para a E3. Por causa da quebra
  na troca de sistema (2016/2017, abaixo), um critério relativo a cada ano (ranking ou
  percentil) é mais seguro que um limiar absoluto de acidentes.

## Dados: o dataset completo da PRF

**Os 50 arquivos publicados, de 2007 a 2026: BR-Brasil (2007–2016) e BAT (2017+), com
ocorrência (`datatranAAAA`), pessoa (`acidentesAAAA`) e, no BAT, todas as causas e tipos
(`acidentesAAAA_todas_causas_tipos`).** Decisão e alternativas no
[ADR 0003](adr/0003-dataset-completo-br-brasil-e-bat.md).

| Conjunto | Sistema | Arquivos | Registros (sem cabeçalho) |
|---|---|---|---|
| `ocorrencia` | BR-Brasil | 10 | 1.562.200 |
| `ocorrencia` | BAT | 10 | 681.425 |
| `pessoa` | BR-Brasil | 10 | 3.369.428 |
| `pessoa` | BAT | 10 | 1.786.741 |
| `pessoa_todas_causas` | BAT | 10 | 4.479.488 |

Ocorrências por ano: 127.675 (2007), 141.043 (2008), 158.646 (2009), 183.469 (2010),
192.326 (2011), 184.568 (2012), 186.748 (2013), 169.201 (2014), 122.161 (2015), 96.363 (2016),
89.567 (2017), 69.333 (2018), 67.558 (2019), 63.585 (2020), 64.567 (2021), 64.606 (2022),
67.766 (2023), 73.202 (2024), 72.529 (2025) e 48.712 (2026, até 31/08).

### Por que o dataset completo

- **A pergunta é de série histórica.** A persistência de um trecho entre os mais graves fica
  mais forte com 19 anos do que com 9.
- **O que a pergunta usa existe nos 20 anos:** `br`, `km`, `uf`, `data_inversa`, `mortos` e
  `feridos_graves` estão em todos os arquivos de ocorrência.
- **Formato diferente não é motivo para descartar dados.** Separador, formatos de data,
  decimal com ponto ou vírgula e o marcador `(null)` do BR-Brasil são tratados na carga, sem
  passo manual ([README](../README.md#como-subir-o-projeto), seção "Carga").
- **A colisão de IDs entre os sistemas não afeta as chaves:** cada ano é um lote, e toda PK
  começa por `id_lote` ([ADR 0003](adr/0003-dataset-completo-br-brasil-e-bat.md)).

### Cuidados na análise (E3)

- **Quebra na troca de sistema.** As ocorrências caem de 169.201 (2014) para 96.363 (2016) e
  89.567 (2017); os acidentes graves caem bem menos (25.195, 21.007 e 18.663). A hipótese ainda
  não verificada é mudança no critério de registro (acidente sem vítima deixando de gerar
  boletim). Comparar trechos pela posição relativa em cada ano, e não pela contagem absoluta.
- **Coordenada só no BAT.** O ranking de 2007 a 2025 usa BR + km; o PostGIS refina a localização
  de 2017 em diante.
- **Vocabulários diferentes** entre os sistemas (`Morto` × `Óbito`, 12 × 91 causas). A pergunta
  não depende deles: a gravidade vem das contagens `mortos` e `feridos_graves`.
- **2026 é parcial** e regravado todo mês: entra no banco (é material da E2), mas não no
  ranking de anos completos.

### Recortes descartados

| Recorte | Por que não |
|---|---|
| BAT 2017–2025 (o recorte da E1) | Descartava o BR-Brasil por diferença de formato, que é trabalho de engenharia de dados, e deixava a persistência com 9 anos. Substituído pelo dataset completo (correção da E1). |
| Só o DF | Cerca de 1.000 ocorrências por ano (1.011 em 2025): pouco volume para a E3. Além disso, `uf` ≠ `regional` (a circunscrição da PRF-DF fica em grande parte em GO). |
| Só os últimos anos (ex.: 2024–2025) | Poucos anos para medir se um trecho se mantém entre os mais graves. |

### Gatilho de revisão

Revisar se a E3 concluir que a quebra de 2016/2017 impede comparar trechos entre os dois
sistemas mesmo por posição relativa: aí a persistência passa a ser medida dentro de cada sistema.
