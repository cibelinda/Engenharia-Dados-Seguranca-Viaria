# Fontes de dados — reconhecimento (Etapa 1)

Levantamento feito em **2026-09-27** sobre os dados abertos de acidentes da PRF.
Os artefatos brutos da investigação estão em
[`reconhecimento-2026-09-27/`](reconhecimento-2026-09-27/). O manifesto de download
derivado deles é o [`sources.yaml`](../../sources.yaml) na raiz.

Nenhuma decisão de modelagem é tomada aqui. As hipóteses em aberto estão listadas no fim.

## Onde os dados estão

| Canal | Situação em 2026-09-27 | Uso no projeto |
|---|---|---|
| [gov.br/prf — Dados Abertos da PRF](https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf) | Fonte oficial. Atualização declarada: mensal (unidade DIOP). | Origem dos IDs do manifesto |
| [Dicionário de dados](https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dicionario-acidentes) | 5 PDFs no Google Drive | Documentação (com divergências, ver abaixo) |
| [dados.gov.br](https://dados.gov.br/dados/conjuntos-dados/acidentes-rodovias-federais) | Página só renderiza no navegador; a API responde 401 (exige token) | Não usado |
| portal.prf.gov.br / prf.gov.br/portal | URLs antigas, ainda aparecem em buscas; sem resposta | Não usado |

## BR-Brasil × BAT

Segundo o dicionário oficial, os dados vêm de **dois sistemas de registro diferentes**:

- **BR-Brasil**: 2007–2016
- **BAT** (Boletim de Acidente de Trânsito): de 2017 em diante

Quase todas as quebras de formato e de identificadores coincidem com essa troca.

## Os três conjuntos

| Conjunto (`dataset` no manifesto) | Arquivo | Anos | Granularidade declarada |
|---|---|---|---|
| `ocorrencia` | `datatranAAAA.zip` | 2007–2026 | 1 linha por acidente, com contagens agregadas (pessoas, mortos, feridos, veículos). No BAT, traz **só a causa principal e o tipo de ordem 1**. |
| `pessoa` | `acidentesAAAA.zip` | 2007–2026 | 1 linha por pessoa envolvida, repetindo os dados do acidente e do veículo |
| `pessoa_todas_causas` | `acidentesAAAA_todas_causas_tipos.zip` | só 2017–2026 | Pessoa × causa × tipo; inclui `causa_principal` (Sim/Não) e `ordem_tipo_acidente` |

São 50 arquivos no total (20 × 2 + 10), cerca de 370 MB em ZIP e cerca de 4 GB descompactados.
Cada ZIP contém exatamente um CSV. O ano de 2026 é parcial: vai de 01/01 a 31/08 na verificação.

| Conjunto | BR-Brasil (2007–16) | BAT (2017–26) |
|---|---|---|
| ocorrência | ~1,56 M linhas | ~0,68 M |
| pessoa | ~3,37 M | ~1,79 M |
| pessoa_todas_causas | — | ~4,48 M |

Contagem por arquivo: [`csv_cabecalhos.json`](reconhecimento-2026-09-27/csv_cabecalhos.json).
Recorte `uf = DF`: cerca de 1.000 ocorrências por ano (1.066 em 2016, 1.011 em 2025).

## Mudanças de formato

| Aspecto | Observado nos arquivos |
|---|---|
| Codificação | cp1252/latin-1 em todos, sem BOM |
| Separador | `pessoa` 2007–2015: `,` — todo o resto: `;` |
| Aspas | `ocorrencia` 2007–2011 sem aspas; demais com aspas |
| `data_inversa` | `dd/mm/aaaa` (2007–2011) · `aaaa-mm-dd` (2012–2015 e 2017+) · `dd/mm/aa` (2016) |
| `km` | Decimal com ponto até 2016; com vírgula a partir de 2017 |
| Colunas `ocorrencia` | 26 → 25 em 2016 (sai `ano`) → 30 em 2017 (entram `latitude`, `longitude`, `regional`, `delegacia`, `uop`) |
| Colunas `pessoa` | 28 → 35 em 2017 (entram `ilesos`, `feridos_leves`, `feridos_graves`, `mortos` binários por pessoa, coordenadas e unidades da PRF; saem `nacionalidade` e `naturalidade`) |

Dentro de cada sistema, os nomes das colunas são estáveis.

## Identificadores

- `id` identifica o acidente, `pesid` a pessoa e `id_veiculo` o veículo (segundo o dicionário).
- **`id` não é global.** É único dentro de cada sistema e não se repete entre anos do mesmo
  sistema, mas **490.283 IDs colidem entre BR-Brasil e BAT** (por exemplo, 69 mil IDs de 2010
  reaparecem em 2025). Qualquer chave que combine os dois períodos precisa incluir o sistema de origem.
- Todo `id` de `ocorrencia` aparece em `pessoa`. No BR-Brasil há IDs em `pessoa` sem
  ocorrência correspondente (773 em 2007, 82 em 2008, poucos depois).
- **`(id, pesid)` não é único no BAT.** Por exemplo, 2024 tem 196.448 linhas e 190.135 pares distintos.
- **Há IDs corrompidos em notação científica** (ex.: `4e+05` em `datatran2021`). São de 0 a 30
  por arquivo no BAT, e o valor original não é recuperável a partir do arquivo.
- Algumas duplicatas de `id` em `ocorrencia` do BR-Brasil (0 a 7 por ano).
- O município vem só pelo nome, sem código IBGE.
- `regional` ≠ `uf`: o próprio dicionário avisa que "a circunscrição da SPRF-DF grande parte
  está localizada na UF GO". Em 2025 há 1.011 ocorrências com `uf=DF` e 1.818 com `regional` do DF.

## Mecanismo de download e regravação de arquivos

- Os arquivos ficam no **Google Drive**. O endpoint
  `https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t`
  funciona sem autenticação e devolve nome, tamanho e `Last-Modified`.
- **A página da PRF tem links ocultos (âncoras sem texto) que apontam para arquivos de outros
  anos.** Por exemplo, ao lado do link de 2025 (ocorrência) há um link oculto para `datatran2024`.
  O mapeamento completo está em [`links_pagina_prf.json`](reconhecimento-2026-09-27/links_pagina_prf.json),
  e a página salva em `pagina_dados_abertos_prf_2026-09-27.html`. Por isso o manifesto usa
  **IDs validados manualmente** e não raspagem da página.
- **A PRF regrava arquivos no mesmo ID e com o mesmo nome** (datas de `Last-Modified` do Drive):

  | Anos | Última gravação observada |
  |---|---|
  | 2007–2016 | 24/11/2022 |
  | 2017–2021 | 27/09/2024 |
  | 2022–2023 | 16/08/2024 |
  | 2024 | **23/09/2026** (ano fechado, regravado 4 dias antes do levantamento) |
  | 2025 | 18/03/2026 |
  | 2026 | 22/09/2026 (atualização mensal) |

  Consequências:
  1. Um checksum fixo vai deixar de bater quando a PRF revisar um ano. O downloader trata isso
     como aviso, não como erro (ver o README da raiz).
  2. Há evidência de que a PRF revisa anos já fechados. Isso é insumo para a decisão futura
     entre CRUD e insert-only, que ainda **não foi tomada**.
  3. Os SHA-256 desta data ([`sha256_2026-09-27.txt`](reconhecimento-2026-09-27/sha256_2026-09-27.txt))
     são a linha de base para detectar revisões.

## Dicionários oficiais × arquivos reais

| Campo | Dicionário diz | Arquivo real |
|---|---|---|
| `data_inversa` | `dd/mm/aaaa` | `aaaa-mm-dd` no BAT e em 2012–2015; `dd/mm/aa` em 2016 |
| `km` | "casa decimal separada por ponto" | vírgula no BAT (2017+) |

O dicionário não serve como fonte de tipos. Os tipos precisam sair do perfilamento.

IDs dos PDFs no Drive: ocorrência até 2016 `11zOQvccvoVSImByIp5-E0PxJ2larrEXy`; pessoa até 2016
`1239K60cfl2eWDCEm9RZWyHuPVXc4z7dG`; pessoa 2017+ `11qwcs8wLghYymG8owRb2FwS2Hi_SjZMf`; pessoa
todas as causas 2017+ `11xcaEgl1hpyfl2hnlFaa0MsxERd6uaKF`; ocorrência 2017+
`11pXLw_0D0hHVS8fiC8cv2dPX39vpuOH1`.

## Licença — ambiguidade

- A página de dados abertos define os dados como "sem restrição de licenças, patentes ou
  mecanismos de controle" e cita a LAI (Lei 12.527/2011) e o Decreto 8.777/2016.
- O rodapé do site gov.br aplica **CC BY-ND 3.0** ao "conteúdo deste site". Não está claro se
  isso vale também para os arquivos de dados.
- Nenhuma licença específica acompanha os CSVs.
- O conjunto `pessoa` traz idade, sexo e dados do veículo, mas nenhum identificador pessoal direto.

Posição atual: citamos a fonte e não redistribuímos os arquivos (`data/raw/` fica fora do Git).
A questão do espelhamento continua em aberto.

## Perguntas em aberto para a Etapa 2 (perfilamento)

1. **Por que `(id, pesid)` não é único no BAT?** Pode ser `pesid` vazio (veículo sem pessoa?),
   pessoa repetida por veículo, ou outra coisa.
2. **Quantos IDs corrompidos em notação científica existem**, em quais arquivos, e se as linhas
   afetadas podem ser associadas por outros campos.
3. **Queda de volume entre 2014 e 2017** (de ~169 mil para ~90 mil ocorrências por ano; 96 mil
   em 2016). Hipótese **não verificada**: mudança de critério de registro (por exemplo, acidentes
   sem vítima deixando de gerar boletim), além da troca de sistema.
4. Qual a granularidade real de `pessoa_todas_causas`: é o produto pessoa × causa × tipo? E por
   que em 2020, 2022 e 2023 ele tem 1 `id` a mais que `pessoa`?
5. Como `estado_fisico`, as binárias por pessoa, as contagens por ocorrência e
   `classificacao_acidente` se relacionam. É a base para definir "grave" operacionalmente.
6. Os domínios de causa, tipo e estado físico são comparáveis entre BR-Brasil e BAT? Isso decide
   o recorte temporal.
7. Completude e qualidade de `latitude`/`longitude` (BAT).
8. O que muda quando a PRF regrava um arquivo: volume e natureza das revisões (comparar as
   versões de 2024 e 2026 com a linha de base).
