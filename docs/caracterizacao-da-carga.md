# Caracterização da carga

> **Revisão de 2026-10-13.** Depois da correção da E1, a origem carrega o dataset completo da
> PRF (2007–2026, BR-Brasil e BAT) num PostgreSQL com PostGIS (ADRs
> [0002](adr/0002-banco-espacial-postgis.md) e [0003](adr/0003-dataset-completo-br-brasil-e-bat.md)).
> Os números abaixo são os do dataset completo. A versão da E1 (BAT 2017–2025, 632 mil
> ocorrências) está na tag [`e1`](https://github.com/cibelinda/Engenharia-Dados-Seguranca-Viaria/blob/e1/docs/caracterizacao-da-carga.md).

Passo 1 do Método de Decisão (issue #6). Dados: os 50 arquivos da PRF, de 2007 a 2026,
conjuntos `ocorrencia` (`datatranAAAA`), `pessoa` (`acidentesAAAA`) e, no BAT,
`pessoa_todas_causas` (`acidentesAAAA_todas_causas_tipos`)
([`pergunta-e-recorte.md`](pergunta-e-recorte.md)).

Os números vêm de três fontes:

- o reconhecimento de 2026-09-27 ([`docs/fontes/`](fontes/README.md));
- o perfil dos ZIPs, gerado por [`bench/perfil_recorte.py`](../bench/perfil_recorte.py), em
  [`bench/resultados/perfil_dataset_completo.json`](../bench/resultados/perfil_dataset_completo.json),
  com o SHA-256 de cada ZIP lido;
- o banco carregado do zero em 2026-10-13 (`docker compose up`) e a medição do ADR 0001
  ([`bench/resultados/medicao_adr.json`](../bench/resultados/medicao_adr.json)).

Para reproduzir:

```bash
docker compose up --build -d && docker compose wait load
docker compose run --rm -v ./bench:/app/bench load python bench/perfil_recorte.py   # perfil dos ZIPs
docker compose run --rm -v ./bench:/app/bench load python bench/medicao_adr.py      # medição do ADR 0001
```

## Origem

Dados abertos de acidentes da Polícia Rodoviária Federal. Os arquivos ficam no Google Drive,
e a PRF os publica como ZIP com um CSV cada (cp1252; separador `;`, exceto o arquivo de pessoa
de 2007–2015, que usa `,`). A publicação é mensal (unidade DIOP). Não há API: a captura é por
download de arquivo inteiro.

São dois sistemas de registro: **BR-Brasil** (2007–2016), sem coordenadas, e **BAT** (2017 em
diante), com latitude e longitude em todo acidente.

## Período

De 01/01/2007 a 31/08/2026 no banco. A pergunta de gestão usa os **19 anos completos**, de 2007
a 2025. 2026 é parcial e regravado todo mês: fica no banco, porque é o material da E2, mas fora
do ranking.

## Volume

Na fonte (50 arquivos, ~367 MB compactados):

| Conjunto | Sistema | Arquivos | Registros |
|---|---|---|---|
| `ocorrencia` | BR-Brasil | 10 | 1.562.200 |
| `ocorrencia` | BAT | 10 | 681.425 |
| `pessoa` | BR-Brasil | 10 | 3.369.428 |
| `pessoa` | BAT | 10 | 1.786.741 |
| `pessoa_todas_causas` | BAT | 10 | 4.479.488 |

No banco, depois da carga (versão vigente, um lote por ano):

| Tabela | Linhas | Tamanho em disco, com índices |
|---|---|---|
| `ocorrencia` | 2.243.584 | 764 MB |
| `veiculo` | 4.008.904 | 728 MB |
| `pessoa` | 4.998.779 | 994 MB |
| `ocorrencia_causa` | 934.079 | 115 MB |
| `ocorrencia_tipo` | 1.051.668 | 102 MB |
| `linha_rejeitada` | 1.275 | 1 MB |
| **Total do banco** | **13,2 milhões** | **2,7 GB** |

Por sistema: o BR-Brasil ocupa ~1,7 GB (7,7 milhões de linhas), e o BAT ~1,0 GB (5,6 milhões).
A carga do zero leva ~8 min (467 s); rodar de novo, sem arquivo novo, leva segundos.

## Cardinalidade

| Medida | Valor |
|---|---|
| Registros de `pessoa` por ocorrência | média 2,23; mediana 2; p95 5; máx. 248 |
| Veículos por ocorrência | média 1,79; mediana 2; p95 3; máx. 131 |
| Linhas de `pessoa` com `pesid = 0` (veículo sem pessoa) | 156.248 |
| `causa_acidente` distintas | 11 no BR-Brasil, 92 no BAT (vocabulários diferentes) |
| `tipo_acidente` distintos | 16 no BR-Brasil, 21 no BAT |
| BRs distintas (sem `br = 0`) | 212 |
| UFs | 27 |
| Municípios distintos (UF + nome) | ~2.500 |
| Trechos distintos (BR + UF + faixa de 10 km), 2007–2025 | 7.486 (6.732 com acidente no BR-Brasil, 6.856 no BAT) |
| IDs de ocorrência que se repetem entre BR-Brasil e BAT | 490.283 (não colidem: toda PK começa por `id_lote`) |

### Chaves de `pessoa`

`(id, pesid)` não é único: tem 55.429 linhas excedentes, todas de `pesid = 0`, isto é, de
veículos listados sem pessoa (reboques, semirreboques, veículos estacionados).
`(id, pesid, id_veiculo)` é a chave da linha. No BR-Brasil há ainda 91 `pesid` repetidos no
mesmo arquivo, que a carga rejeita com o motivo.

## Taxa de escrita

- **Volume anual:** no BAT, de 63,6 mil a 89,6 mil ocorrências por ano; em 2025, 72.529, cerca
  de 6 mil por mês e 200 por dia. No BR-Brasil, de 96 mil a 192 mil por ano.
- **Padrão de escrita:** em lote. A PRF substitui o arquivo inteiro do ano, com o mesmo ID e o
  mesmo nome no Drive. Não existe escrita linha a linha.
- **Regravações observadas** (`Last-Modified` do Drive, no [`sources.yaml`](../sources.yaml)):

  | Anos | Última gravação |
  |---|---|
  | 2007–2016 (BR-Brasil, os 20 arquivos) | 24/11/2022 |
  | 2017–2021 | 27/09/2024 |
  | 2022–2023 | 16/08/2024 |
  | 2024 | 23/09/2026 (ano fechado, regravado 4 dias antes do levantamento) |
  | 2025 | 18/03/2026 |
  | 2026 | 22/09/2026 (ano parcial, regravado todo mês) |

- **O que uma regravação custa no banco:** o lote é o ano inteiro, e só é criado quando o
  SHA-256 de algum arquivo do ano muda. Uma regravação de 2024 acrescenta ~628 mil linhas
  (73.201 ocorrências, 139.693 veículos, 179.244 pessoas, 111.388 causas, 124.271 tipos) e
  ~110 MB (proporção do ano no tamanho de cada tabela). A medição do ADR 0001 registrou 69 MB,
  abaixo disso porque reaproveitou espaço liberado por uma rodada anterior. Uma regravação do
  BR-Brasil inteiro, como a de 2022, acrescentaria ~1,7 GB.
- **Crescimento esperado:** ~1,2 GB por ano. São ~4,5 regravações de ano fechado por ano (9 em
  dois anos, de 2024 a 2026), ~500 MB, mais o ano corrente, regravado todo mês com tamanho
  crescente, ~700 MB.

## Crescimento e sazonalidade

Ocorrências na versão vigente (já sem as linhas rejeitadas):

| Ano | Sistema | Ocorrências | Variação | Com morto ou ferido grave | % graves |
|---|---|---|---|---|---|
| 2007 | BR-Brasil | 127.671 | — | 21.227 | 16,6% |
| 2008 | BR-Brasil | 141.038 | +10,5% | 22.273 | 15,8% |
| 2009 | BR-Brasil | 158.646 | +12,5% | 23.761 | 15,0% |
| 2010 | BR-Brasil | 183.465 | +15,6% | 26.342 | 14,4% |
| 2011 | BR-Brasil | 192.322 | +4,8% | 27.515 | 14,3% |
| 2012 | BR-Brasil | 184.561 | −4,0% | 26.591 | 14,4% |
| 2013 | BR-Brasil | 186.745 | +1,2% | 25.911 | 13,9% |
| 2014 | BR-Brasil | 169.197 | −9,4% | 25.195 | 14,9% |
| 2015 | BR-Brasil | 122.158 | −27,8% | 21.852 | 17,9% |
| 2016 | BR-Brasil | 96.362 | −21,1% | 21.007 | 21,8% |
| 2017 | BAT | 89.567 | −7,1% | 18.663 | 20,8% |
| 2018 | BAT | 69.332 | −22,6% | 17.535 | 25,3% |
| 2019 | BAT | 67.557 | −2,6% | 18.309 | 27,1% |
| 2020 | BAT | 63.584 | −5,9% | 17.452 | 27,4% |
| 2021 | BAT | 64.566 | +1,5% | 18.118 | 28,1% |
| 2022 | BAT | 64.606 | +0,1% | 18.409 | 28,5% |
| 2023 | BAT | 67.766 | +4,9% | 19.212 | 28,4% |
| 2024 | BAT | 73.201 | +8,0% | 20.644 | 28,2% |
| 2025 | BAT | 72.529 | −0,9% | 20.493 | 28,3% |
| 2026 (até 31/08) | BAT | 48.711 | — | 13.653 | 28,0% |

- **Os acidentes graves são bem mais estáveis que o total.** O total cai de 192 mil (2011) para
  64 mil (2020), uma queda de dois terços. Os graves caem de 27,5 mil para 17,5 mil, pouco mais
  de um terço. Somam 410.509 de 2007 a 2025 (18,7% das ocorrências).
- **Quebra entre 2014 e 2018.** As ocorrências caem 59% de 2014 a 2018, mas a fração de graves
  sobe de 15% para 25%: o que sumiu foram sobretudo acidentes sem vítima grave. A hipótese é
  mudança no critério de registro (acidente sem vítima deixando de gerar boletim), na transição
  para o BAT, mas **não foi verificada**. Por isso a persistência deve ser medida pela posição
  relativa do trecho em cada ano, e não por contagem absoluta
  ([`pergunta-e-recorte.md`](pergunta-e-recorte.md), "Cuidados na análise").
- **Sazonalidade:** dezembro é o mês de pico (208.273 ocorrências somando 2007–2025, 14% acima
  da média mensal de 182.906). Fevereiro é o menor (169.639), em parte por ter menos dias.
- O menor mês da série é abril de 2020 (3.885), no início da pandemia. O maior é dezembro de
  2010 (18.929).

## Taxa e padrão de leitura

A leitura serve à pergunta de gestão. Ela agrega por trecho e por ano e varre os 19 anos. Não há
acesso por chave nem consulta em tempo real. A leitura acontece em rodadas de análise, sempre
muito depois da escrita, que é mensal.

Consultas que respondem à pergunta. `ocorrencia_vigente` (migração `V0012`) traz a versão do
lote vigente de cada ano, e `ano` é derivado de `ocorrido_em`. Ficam fora do ranking as
ocorrências com `br = 0` (rodovia não identificada) e com `km` NULL (ausente ou negativo no
BR-Brasil): sem eles, não dá para montar o trecho
([`pergunta-e-recorte.md`](pergunta-e-recorte.md), "Decidido depois"). 2026 fica fora por ser
parcial.

```sql
-- Q1: acidentes com morto ou ferido grave por trecho de 10 km e ano
SELECT br, uf, floor(km / 10) * 10 AS km_inicio,
       ano,
       count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
FROM ocorrencia_vigente
WHERE br <> 0 AND km IS NOT NULL AND ano <= 2025
GROUP BY br, uf, km_inicio, ano;

-- Q2: persistência, ou seja, em quantos anos o trecho ficou entre os 50 mais graves
WITH por_trecho AS (
    SELECT br, uf, floor(km / 10) * 10 AS km_inicio,
           ano,
           count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
    FROM ocorrencia_vigente
    WHERE br <> 0 AND km IS NOT NULL AND ano <= 2025
    GROUP BY br, uf, km_inicio, ano
), ranqueado AS (
    SELECT *, rank() OVER (PARTITION BY ano ORDER BY graves DESC) AS posicao
    FROM por_trecho
)
SELECT br, uf, km_inicio, count(*) AS anos_entre_os_50, sum(graves) AS graves_total
FROM ranqueado
WHERE posicao <= 50
GROUP BY br, uf, km_inicio
ORDER BY anos_entre_os_50 DESC, graves_total DESC;

-- Q3: série anual de um trecho
SELECT ano,
       count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves,
       count(*) AS total
FROM ocorrencia_vigente
WHERE br = 116 AND uf = 'SP' AND km >= 200 AND km < 210 AND ano <= 2025
GROUP BY ano ORDER BY ano;

-- Q4 (2017+): acidentes graves num raio de 2 km de um ponto da BR-040 no DF (PostGIS, índice GiST)
SELECT ano, count(*)
FROM ocorrencia_vigente
WHERE (mortos > 0 OR feridos_graves > 0)
  AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(-47.95, -15.87), 4674)::geography, 2000)
GROUP BY ano ORDER BY ano;
```

| Consulta | O que lê | Tempo medido (mediana) |
|---|---|---|
| Q1 | `ocorrencia` inteira, 19 anos (100.919 linhas de resultado) | 2,4 s |
| Q2 | idem, com ranking por ano (135 trechos) | 2,8 s |
| Q3 | `ocorrencia` de um trecho | — (não medida; filtra por `br`, `uf`, `km`) |
| Q4 | pontos do BAT pelo índice GiST | 46 ms no ponto da medição do [ADR 0002](adr/0002-banco-espacial-postgis.md) (608 ms sem PostGIS) |

Q1 e Q2 vêm de [`medicao_adr.json`](../bench/resultados/medicao_adr.json) (5 execuções depois de
uma de aquecimento). As quatro leem só `ocorrencia`; `pessoa`, causas e tipos entram no
perfilamento e na E3. Com 7.486 trechos e ~21,6 mil acidentes graves por ano, a média é de
~2,9 acidentes graves por trecho por ano, número que serve para calibrar o tamanho do trecho.

O top 50 da Q2 é um valor provisório. O critério de persistência ainda precisa ser definido,
e também o desempate: `rank()` dá a mesma posição a trechos empatados, então o "top 50" pode
ter mais de 50 trechos num ano.

## Latência tolerada

Meses. A pergunta é anual, a PRF publica uma vez por mês com semanas de defasagem, e um ano
só é comparável depois de fechado. Um atraso de um mês entre a publicação e a carga não muda
nenhuma resposta. As consultas analíticas levam segundos (Q2, 2,8 s), muito abaixo disso.

## Características encontradas no perfil

- **Formatos do BR-Brasil:** data em três formatos (`dd/mm/aaaa`, `aaaa-mm-dd`, `dd/mm/aa`),
  decimal com ponto ou vírgula (o `km` de 2016 já usa vírgula), ausência marcada com o texto
  `(null)` e textos completados com espaços (`'Morto       '`). A carga trata tudo sem passo
  manual (README, seção "Carga").
- **`br = 0`** (rodovia não identificada) em 1.581 ocorrências, 1.507 delas no BAT. Ficam no
  banco como vêm da PRF, mas saem do ranking.
- **`uf`, `br` e `km` ausentes** em 12 ocorrências do BR-Brasil, e **`km` negativo** em 19: a
  carga grava NULL, e elas saem do ranking.
- **Coordenadas:** 100% das ocorrências do BAT têm latitude e longitude; 33 pares de 2017 estão
  fora do limite válido e viram NULL. Nenhum arquivo do BR-Brasil tem as colunas. **De 2019 a
  2024, cerca de metade das coordenadas é um ponto padrão repetido**, e não o local do acidente
  ([ADR 0002](adr/0002-banco-espacial-postgis.md)).
- **IDs em notação científica** (`1e+05`, `4e+05`...) em 6 ocorrências do BAT, com os registros
  de pessoa e de causas ligados a elas pelo mesmo texto. O `id` original não é recuperável.
- **IDs de ocorrência repetidos no mesmo arquivo:** 35 no BR-Brasil.
- `mortos` e `feridos_graves` da ocorrência batem com a soma das pessoas, exceto em 8 e 19
  ocorrências do BR-Brasil, respectivamente, por pessoas rejeitadas na carga.

## Inconsistências e tratamento na carga

Regras de conversão da carga: README, seção "Carga". Em cada arquivo, lidas = carregadas +
rejeitadas: 11.879.282 registros lidos, 1.275 rejeitados (0,01%), todos com motivo em
`linha_rejeitada`.

| Sistema | Arquivo | Rejeitados | Motivo |
|---|---|---|---|
| BAT | `datatran` | 6 | `id` em notação científica |
| BAT | `acidentes` | 25 | `id` em notação científica |
| BAT | `acidentes` | 1 | `pesid = 0` e `id_veiculo = 0`: nem pessoa nem veículo |
| BAT | `todas_causas_tipos` | 59 | `id` em notação científica |
| BAT | `todas_causas_tipos` | 29 | ocorrência não carregada |
| BR-Brasil | `datatran` | 35 | `id` repetido no arquivo |
| BR-Brasil | `acidentes` | 936 | pessoa sem ocorrência carregada (a ocorrência não está no arquivo ou foi rejeitada) |
| BR-Brasil | `acidentes` | 91 | `pesid` repetido |
| BR-Brasil | `acidentes` | 61 | ano de fabricação entre 1851 e 1899 |
| BR-Brasil | `acidentes` | 32 | o mesmo `id_veiculo` em duas ocorrências |

Não viram rejeição, mas mudam o valor: coordenadas fora do limite, `uf`/`br`/`km` `(null)` e `km`
negativo viram NULL, assim como idade 0, negativa ou acima de 110 e ano de fabricação 0 ou
futuro (desconhecido).

## Declaração de histórico

**A origem sobrescreve.** A PRF publica cada ano como um arquivo que é substituído
inteiro, no mesmo ID e com o mesmo nome, sem versão nem registro de alteração. Quem guarda
só a versão mais recente perde o estado anterior a cada regravação.

**O projeto guarda como insert-only, versionado por lote.** A decisão foi tomada na #3 e está
implementada no esquema: `lote_carga`, PKs que começam por `id_lote` e views `*_vigente`
([`modelagem-origem.md`](modelagem-origem.md) e
[ADR 0001](adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md)). Cada carga de um
ano é um lote. Uma republicação da PRF gera um lote novo, e o anterior não é alterado nem apagado.

| | Insert-only por lote (adotado) | CRUD (descartado) |
|---|---|---|
| Permite perguntar | quantas ocorrências de 2024 a PRF alterou, incluiu ou removeu depois de fechar o ano; se um trecho entrou ou saiu do ranking de graves por causa de uma revisão; qual era a resposta da pergunta de gestão numa data passada | só o estado da última versão publicada |
| Impede | nada que a origem permita | qualquer pergunta sobre o que a PRF mudou; a versão anterior se perde no primeiro UPDATE |

Nos dois casos, as versões anteriores a 2026-09-27 (linha de base dos SHA-256 do
reconhecimento) já não existem na origem e estão perdidas para qualquer modelo.

### Evidência de revisão da origem (#7)

**Evidência indireta** (reconhecimento de 2026-09-27, [`docs/fontes/`](fontes/README.md)):

- **Nenhum dos 50 arquivos tem coluna de atualização ou de versão**
  ([`csv_cabecalhos.json`](fontes/reconhecimento-2026-09-27/csv_cabecalhos.json)). As únicas
  colunas de tempo são `data_inversa` e `horario`, que marcam o evento. O arquivo traz só o
  estado atual.
- **A PRF regrava os arquivos no mesmo ID e com o mesmo nome** (`Last-Modified` do Drive,
  registrado no [`sources.yaml`](../sources.yaml)):

  | Ano | Última gravação | Situação |
  |---|---|---|
  | 2024 | 23/09/2026 | ano fechado, regravado |
  | 2025 | 18/03/2026 | ano fechado, regravado |
  | 2026 | 22/09/2026 | ano parcial, regravado mensalmente |

Isso mostra que a origem sobrescreve. Mas não mostra o que muda numa regravação, nem quanto:
a data de gravação pode mudar mesmo que o conteúdo seja igual.

**Linha de base guardada:** os SHA-256 de 2024, 2025 e 2026 (os 9 arquivos dos três conjuntos),
de 2026-09-27, copiados para
[`fontes/linha-de-base-2026-09-27/`](fontes/linha-de-base-2026-09-27/sha256_2026-09-27_2024-2026.txt),
fora de `data/raw/`. Os hashes detectam se um arquivo mudou, mas não o que mudou. Os ZIPs
dessa data não foram copiados porque não havia cópia local no momento do registro.

**Comparação direta: pendente.** Data prevista: **26/10/2026**, depois da próxima
atualização mensal da PRF (a última, de 2026, foi em 22/09/2026).

O conteúdo da linha de base está no banco: os lotes vigentes de 2024, 2025 e 2026, carregados
em 2026-10-13 (banco recriado com o dataset completo), têm em `lote_arquivo.sha256` os mesmos
hashes da linha de base, conferidos um a um. A comparação por chave é feita entre lotes, e por
isso o volume do banco não pode ser apagado até lá (`docker compose down -v`). Se for apagado,
a linha de base só volta enquanto a PRF não regravar esses anos. Passos:

1. `python -m blackspot.download --force --year 2024 --year 2025 --year 2026 --dest <pasta-nova>`
   e comparar os SHA-256 com a linha de base: um hash diferente é um arquivo republicado;
2. se 2024, 2025 ou 2026 mudou, rodar a carga no mesmo banco: ela cria um lote novo para o ano e
   mantém o anterior;
3. comparar os dois lotes do ano por chave (`id` em `ocorrencia`; `(id, pesid, id_veiculo)` em
   `pessoa`): linhas inseridas, removidas e alteradas, e quais colunas mudaram;
4. resumir o resultado aqui e revisar o [ADR 0001](adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md)
   se necessário.

O resultado é insumo da E2 (captura de mudanças).
