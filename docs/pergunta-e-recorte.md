# Pergunta de gestão e recorte dos dados

Decisões das issues #1 e #2. Os números vêm do reconhecimento de 2026-09-27
([`docs/fontes/`](fontes/README.md) e
[`csv_cabecalhos.json`](fontes/reconhecimento-2026-09-27/csv_cabecalhos.json)).

## Pergunta de gestão

> **Quais trechos de 10 km das rodovias federais concentraram mais acidentes com mortos ou
> feridos graves entre 2017 e 2025, e esses trechos se mantêm de um ano para o outro?**

| Elemento | Valor |
|---|---|
| Objeto analisado | Trecho de rodovia federal: BR + UF + faixa de 10 km (ex.: BR-040/GO, km 0–10) |
| Recorte geográfico | Todas as rodovias federais do Brasil |
| Recorte temporal | 2017 a 2025 (anos completos) |
| Medida | Número de acidentes com ao menos um morto ou ferido grave por trecho e por ano; persistência do trecho entre os mais graves ao longo dos anos |

### Por que esta pergunta

- **Responde ao objetivo do projeto.** Um *black spot* é um trecho de via onde os acidentes se
  concentram. A pergunta pede exatamente esses trechos.
- **Mede gravidade, não só quantidade.** Quem decide onde fiscalizar ou fazer obra prioriza
  onde há morte e lesão grave. Contar todos os acidentes mistura colisões sem vítima com
  acidentes fatais. As colunas `mortos` e `feridos_graves` existem em todas as ocorrências do
  BAT.
- **Usa BR + km, e não coordenadas.** `br` e `km` existem em todos os anos. A completude de
  `latitude`/`longitude` ainda não foi medida (pergunta aberta 7 do reconhecimento).
- **A persistência separa o ponto negro do acaso.** Um trecho que aparece entre os mais graves
  em um único ano pode ser flutuação; um que se repete ano após ano é o que justifica
  intervenção.

### Alternativas descartadas

| Pergunta | Por que não |
|---|---|
| "Quais UFs ou municípios têm mais acidentes?" | Não localiza o trecho, que é o objeto de um *black spot*. O município vem só pelo nome, sem código IBGE. |
| "Quais as principais causas de acidente?" | Não diz onde agir. No arquivo de ocorrência do BAT só vem a causa principal. |
| "Quais trechos têm mais acidentes?" (sem gravidade) | Trata igual uma colisão sem vítima e um acidente fatal. |
| Agrupar por coordenada (latitude/longitude) | A qualidade das coordenadas ainda não foi medida, e elas não existem antes de 2017. |

### O que ainda precisa ser definido

- **O tamanho do trecho (10 km) é um parâmetro, não um dado.** Trechos curtos demais deixam
  poucos acidentes por trecho e ano; longos demais diluem o ponto negro. O valor pode ser
  recalibrado na E3 com o dado carregado.
- **A definição operacional de "grave"** (`mortos > 0 ou feridos_graves > 0`, ou
  `classificacao_acidente`) depende do perfilamento: pergunta aberta 5 do reconhecimento.
- **O critério de persistência**: o que conta como um trecho que "se mantém" entre os mais
  graves. Pode ser estar entre os N piores de cada ano, acima de um percentil, ou aparecer em
  um número mínimo dos 9 anos do recorte. A escolha é da Squad e fica para a E3.

## Recorte dos dados

**Sistema BAT, anos 2017 a 2025, conjuntos `ocorrencia` (`datatranAAAA`) e `pessoa`
(`acidentesAAAA`).**

| Conjunto | Arquivos | Linhas físicas (sem cabeçalho) | Descompactado |
|---|---|---|---|
| `ocorrencia` | 9 | 632.713 | ~181 MB |
| `pessoa` | 9 | 1.654.197 | ~615 MB |

Ocorrências por ano: 89.567 (2017), 69.333 (2018), 67.558 (2019), 63.585 (2020),
64.567 (2021), 64.606 (2022), 67.766 (2023), 73.202 (2024), 72.529 (2025).

As contagens são de linhas físicas medidas no reconhecimento. A contagem de registros
confirma-se na carga.

### Por que este recorte

- **Um único formato.** No BAT, os nomes das colunas são estáveis, o separador é `;` e as
  datas são `aaaa-mm-dd`. O BR-Brasil (2007–2016) tem três formatos de data e dois
  separadores.
- **Sem colisão de IDs.** O `id` é único dentro de cada sistema. Juntar os dois sistemas
  exigiria incluir o sistema de origem na chave (490.283 IDs colidem).
- **Anos completos.** 2025 é o último ano fechado.
- **Tem o que a pergunta precisa:** `br`, `km`, `uf`, `data_inversa`, `mortos` e
  `feridos_graves` estão em todos os arquivos de ocorrência do recorte.
- **Volume suficiente** para a E3 e para os planos de execução: cerca de 630 mil ocorrências
  e 1,65 milhão de registros de pessoa.

### Por que `pessoa` entra e `pessoa_todas_causas` não

- `pessoa` traz o veículo (`id_veiculo`) e a pessoa (`pesid`) de cada acidente. Sem ele, a
  origem não tem os relacionamentos ocorrência → veículo → pessoa que um sistema transacional
  teria (issue #3).
- `pessoa_todas_causas` (4.070.595 linhas em 2017–2025) traz as causas e tipos secundários.
  A pergunta não usa causa, e a granularidade desse arquivo ainda não está clara (pergunta
  aberta 4 do reconhecimento). Fica fora da E1 e pode entrar se a E3 precisar.

### Recortes descartados

| Recorte | Por que não |
|---|---|
| 2007–2026 completo (BR-Brasil + BAT) | Formatos diferentes, IDs que colidem, sem coordenadas antes de 2017. A queda de volume entre 2014 (169.201 ocorrências) e 2017 (89.567) ainda não tem explicação verificada, e comparar trechos através dessa quebra misturaria critério de registro com mudança real. A comparabilidade dos domínios de causa e tipo entre os sistemas também está em aberto (pergunta 6). |
| BAT 2017–2026 (incluindo 2026) | 2026 é parcial (até 31/08 no reconhecimento) e é regravado todo mês. Comparar um ano incompleto com anos fechados distorce a persistência dos trechos. 2026 fica como candidato a fonte de mudanças na E2. |
| Só o DF | Cerca de 1.000 ocorrências por ano (1.011 em 2025): pouco volume para a E3. Além disso, `uf` ≠ `regional` (a circunscrição da PRF-DF fica em grande parte em GO). |
| Só os últimos anos (ex.: 2024–2025) | Poucos anos para medir se um trecho se mantém entre os mais graves. |

### Gatilho de revisão

Revisar o recorte se o perfilamento mostrar que `br` ou `km` estão ausentes ou inválidos em
uma parte relevante das ocorrências do BAT, ou se a E3 precisar das causas secundárias.
