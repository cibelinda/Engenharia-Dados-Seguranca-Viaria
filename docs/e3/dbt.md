# Modelo dimensional, testes e consulta otimizada

Parte da E3 da issue #43. O contrato entre as partes está no [README.md](README.md). O código
fica em [`dbt/models/staging/`](../../dbt/models/staging/), em
[`dbt/models/marts/trecho/`](../../dbt/models/marts/trecho/) e nos testes `dbt/tests/trecho_*`.

```bash
docker compose run --rm dbt build      # modelos e testes (o banco precisa estar carregado)
```

## Camadas

```
origem (public, versão vigente)        staging (views)              marts (tabelas)
───────────────────────────────        ───────────────              ───────────────
ocorrencia_vigente ──────────────────► stg_ocorrencia ──┬──────────► fct_ocorrencia ──┬──► dim_trecho ──┐
lote_vigente ────────────────────────► stg_lote ────────┘                │             │                ├──► mart_risco_trecho_ano
                                       stg_ocorrencia ─────────────────► dim_tempo ───┼────────────────┘
causa_acidente ──────────────────────► stg_causa ──────────────────────► dim_causa    │
pessoa_vigente, veiculo_vigente, ...   stg_pessoa, stg_veiculo, ...      (o fato aponta para as três)
```

| Camada | Schema | Materialização | Papel |
|---|---|---|---|
| staging | `analitico_staging` | view | Uma view por tabela de origem: limpa, **sem mudar o nome das colunas** |
| marts | `analitico_marts` | tabela | Fato, dimensões e a resposta da pergunta de gestão |

A camada `intermediate` é usada pela parte do IBGE (`int_ocorrencia_municipio`); esta parte
não precisou dela.

## Limpeza no staging

A origem guarda o que a PRF publicou, sem corrigir ([`modelagem-origem.md`](../modelagem-origem.md)).
Os dois sistemas da PRF escrevem a mesma coisa de jeitos diferentes, e é no staging que isso
vira um vocabulário só. Duas regras valem para todas as views:

- **"Não sei" vira NULL**, e não um valor que se conta como categoria: `Ignorado`, `Ignorada`,
  `Não Informado`, `Inválido`, `Não identificado`.
- **As colunas que a parte do IBGE usa passam sem mudança de valor** (`id_lote`, `id`, `ano`,
  `uf`, `municipio`, `geom`, `mortos`, `feridos_graves`). Conferido com `EXCEPT` nos dois
  sentidos entre `stg_ocorrencia` e `ocorrencia_vigente`: zero linhas de diferença.

| View | O que estava sujo (medido em 2026-11-09) | Depois |
|---|---|---|
| `stg_ocorrencia` | `Ceu Claro` (753 mil) e `Céu Claro` (408 mil); `Nevoeiro/neblina` e `Nevoeiro/Neblina`; `Ignorado` (9.584) e `Ignorada` (28.422) | `Céu Claro`, `Nevoeiro/Neblina`, NULL |
| | `Plena Noite` (237 mil, BR-Brasil) e `Plena noite` (481 mil) | `Plena noite` |
| | sentido `Não Informado` (1.507); classificação `Ignorado` (11.660) | NULL |
| `stg_pessoa` | estado físico `Morto`, `Ferido Grave`, `Ferido Leve` (BR-Brasil) × `Óbito`, `Lesões Graves`, `Lesões Leves` (BAT); `Ignorado` e `Não Informado` | o vocabulário do BAT; NULL |
| | sexo `M` (162 mil) e `F` (46 mil) ao lado de `Masculino` e `Feminino`; `Não Informado`, `Inválido`, `Ignorado`, `I` | `Masculino`, `Feminino` ou NULL |
| `stg_veiculo` | `Motocicletas` e `Motocicleta`, `Caminhão-trator` e `Caminhão-Trator`, `Micro-ônibus` e `Microônibus` e mais cinco pares | uma grafia por tipo |
| | ano de fabricação 1900 e 1901 (208 veículos: o menor valor que o esquema aceita) | NULL |
| `stg_lote`, `stg_ocorrencia_causa`, `stg_ocorrencia_tipo`, `stg_causa`, `stg_tipo` | nada a limpar | colunas listadas uma a uma, para que uma coluna nova na origem não apareça sem passar por aqui |

As causas (101 descrições, várias repetidas com outra grafia) não são juntadas no staging: a
descrição original fica, e quem junta é a `dim_causa`, onde a regra de negócio mora.

## Modelo dimensional

Estrela com um fato e três dimensões. A dimensão de variação lenta (`dim_municipio`) é da
parte do IBGE ([`ibge.md`](ibge.md)).

| Modelo | Granularidade: o que é uma linha | Chave | Linhas |
|---|---|---|---|
| `fct_ocorrencia` | **um acidente**, na versão vigente de cada ano, 2007 a 2026 | `(id_lote, id)` | 2.243.584 |
| `dim_trecho` | **um trecho de 10 km**: BR + UF + `floor(km / 10) * 10`, com ao menos um acidente | `chave_trecho` (ex.: `101-SC-0200`) | 7.544 |
| `dim_tempo` | **um dia**, do primeiro ao último acidente, inclusive dias sem acidente | `data` | 7.183 |
| `dim_causa` | **uma causa como a PRF escreveu** (`id_causa` da origem) | `id_causa` | 101 (86 causas harmonizadas) |
| `mart_risco_trecho_ano` | **um trecho por ano**, para cada trecho com acidente no ano | `(chave_trecho, ano)` | 105.942 |

**`fct_ocorrencia`.** As medidas são as contagens da ocorrência (`pessoas`, `veiculos`,
`mortos`, `feridos_graves`, `feridos_leves`, `ilesos`) e `grave` (`mortos > 0 or feridos_graves > 0`,
a definição do projeto). As chaves são `data` → `dim_tempo`, `chave_trecho` → `dim_trecho` e
`id_causa` → `dim_causa`. A hora fica no fato (`hora`), porque é hora local sem fuso e não cabe
numa dimensão de dia. `chave_trecho` é NULL em 1.612 acidentes: os 1.581 com `br = 0`
(rodovia não identificada) e os sem `br`, `uf` ou `km`. Desses, 180 são graves.

A coordenada (só BAT) vem com duas marcas, porque o [ADR 0002](../adr/0002-banco-espacial-postgis.md)
mostrou que metade dos pontos de 2019 a 2024 é um ponto padrão, e não o local do acidente:

- `coordenada_padrao`: o ponto exato é de 10 ou mais acidentes com kms diferentes;
- `coordenada_confiavel`: tem ponto, não é padrão e está dentro do retângulo do Brasil.

| | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| `coordenada_padrao` | 5,9% | 15,7% | 48,2% | 50,5% | 51,3% | 50,3% | 50,1% | 50,6% | 6,6% | 0,1% |

Os números batem com os do ADR 0002 (6,5% ... 51,8% ... 0,1%); a pequena diferença é que o
ADR conta os acidentes do arquivo, e o fato conta os da versão vigente.

**`dim_trecho`.** A UF faz parte do trecho porque a PRF recomeça o km em cada UF. Dois
atributos de qualidade:

- `km_isolado`: o trecho tem 5 acidentes ou menos em 20 anos e fica a mais de 100 km do último
  trecho com mais de 5 acidentes da mesma BR e UF. É o km digitado errado: a BR-040 em MG tem
  acidente todo ano até o km 830, e depois um acidente aqui e ali nos km 1.030, 1.870, 2.140,
  2.240... até o 9.960. São 338 trechos com 495 acidentes. A comparação é com o último trecho "cheio",
  e não com o vizinho, porque os kms errados formam cadeias (o 2.140 e o 2.240 estão a 100 km
  um do outro). O trecho fica no ranking, mas quase nunca sobe nele.
- `geom_centro`: o centro dos acidentes com coordenada confiável, para localizar o trecho no
  mapa. NULL nos 623 trechos que só têm acidente do BR-Brasil ou ponto padrão.

**`dim_causa`.** Junta as variantes da mesma causa em `causa` (`Dormindo` e `Condutor Dormindo`
→ `Condutor dormindo`; `Ingestão de álcool`, `Ingestão de Álcool` e `Ingestão de álcool pelo
condutor` → `Ingestão de álcool pelo condutor`) e classifica em `grupo`. Das 101 descrições, 38 são do condutor, 34 da via, 10 do veículo, 8 do
pedestre, 6 do ambiente e 5 ficam em Outras. Uma causa nova da PRF entra como
`Não classificada`, e o teste do `grupo` avisa, sem parar a esteira.

**`dim_tempo`.** `ano_completo` é falso no ano corrente, que a PRF publica até o mês anterior.
O mart usa essa coluna para que o ranking de 2026 (até agosto) não seja comparado com os
outros sem aviso.

## A resposta: `mart_risco_trecho_ano`

| Coluna | O que é |
|---|---|
| `chave_trecho`, `br`, `uf`, `km_inicio`, `km_fim`, `rotulo` | o trecho (as colunas que o painel lê: `br`, `uf`, `km_inicio`, `ano`, `graves`) |
| `ano`, `ano_completo` | o ano e se ele está completo |
| `acidentes`, `graves`, `mortos`, `feridos_graves` | contagens do trecho no ano |
| `posicao` | posição no ano pelo número de graves (`rank`: empate fica na mesma posição). NULL quando o trecho não teve grave |
| `percentil_graves` | a posição como fração (0 = o pior trecho do ano). O BR-Brasil registrava o dobro de acidentes do BAT, então um limiar absoluto não serve para comparar 2010 com 2020; a posição relativa serve |

O mart tem **contrato** (`contract: enforced`): se uma coluna mudar de nome ou de tipo, o
`dbt build` para antes de criar a tabela, e o painel não quebra em silêncio.

O que a tabela responde, nos 19 anos completos (2007–2025): em 2025, o pior trecho foi a
**BR-101/SC km 200–210** (125 acidentes graves), seguido do km 210–220 da mesma BR (100). Só 135
trechos estiveram alguma vez entre os 50 piores de um ano, e **7 estiveram em todos os 19**:
BR-101/SC km 200–210 e 210–220, BR-101/ES km 260–270, BR-316/PI km 0–10, BR-381/MG km 480–490,
BR-040/MG km 520–530 e BR-277/PR km 0–10. Esses são os pontos negros que se mantêm, e não o acaso
de um ano.

## Testes

35 testes desta parte, todos passando no `dbt build`. A regra do enunciado foi seguida: testar
o que o dado tem de sujo. Não há `not_null` em coluna que o esquema da origem já garante; os
`accepted_values` do staging listam o vocabulário **depois** da limpeza, então falham se a
variante (`Ceu Claro`, `Morto`, `M`) voltar.

| Tipo | Teste | O que pega |
|---|---|---|
| Esquema | contrato do `mart_risco_trecho_ano` (15 colunas com tipo) | coluna renomeada ou com outro tipo, antes de o painel ler |
| Esquema | `accepted_values` em `fase_dia`, `condicao_meteorologica`, `sentido_via`, `classificacao_acidente`, `estado_fisico`, `sexo`, `sistema`, `uf`, `grupo` | variante de grafia ou "não sei" que escapou da limpeza |
| Volume | `trecho_fato_volume_bate_com_carga` | o fato tem, ano a ano, exatamente as linhas que a carga gravou (`lote_arquivo`: lidas − rejeitadas) |
| Volume | `trecho_volume_graves_bate_com_origem` | graves do ranking + graves sem trecho = graves da origem, ano a ano |
| Unicidade | `trecho_fato_um_por_acidente`, `trecho_uma_linha_por_trecho_ano` (chaves compostas, singulares); `unique` em `chave_trecho`, `data`, `id_causa`, `ano` do lote | join que duplica |
| Integridade referencial | `relationships` do fato para as três dimensões, do mart para `dim_trecho` e de `stg_ocorrencia_causa` para `stg_causa` | chave sem dimensão |
| Distribuição | `trecho_graves_sem_trecho` | mais de 0,5% dos graves de um ano sem trecho (hoje o pior ano é 2017, com 0,18%) |
| Distribuição | `trecho_graves_salto_entre_anos` | graves de um ano completo variando mais de 20% sobre o anterior (a maior variação de 2007 a 2025 é 13%; o total de acidentes cai pela metade em 2017, mas os graves não) |
| Distribuição | `trecho_km_isolado_raro` | mais de 0,1% dos acidentes em trecho isolado (hoje 495 em 2,2 milhões): um km lido com a vírgula no lugar errado |
| Limpeza | `trecho_estado_fisico_bate_com_mortos` | depois de juntar `Morto` e `Óbito`, as pessoas em óbito e com lesão grave batem com `mortos` e `feridos_graves` (8 e 19 divergências em 2,2 milhões, as das pessoas rejeitadas na carga); se uma grafia nova escapar, são milhares |
| Limpeza | `trecho_causa_variante_sem_juntar` | duas causas que só diferem em maiúscula ou acento com valores diferentes em `causa` |
| Coerência | `trecho_posicao_coerente` | posição 1 que não é o máximo, trecho com mais graves atrás de um com menos, empate com posições diferentes |

Os limiares das distribuições vieram de medir o banco carregado (2026-11-09), e não de chute; a
medida está no comentário de cada teste.

## Consulta otimizada

A consulta escolhida é a do painel ([`painel/app.py`](../../painel/app.py)), que roda a cada
troca de ano: os 20 trechos com mais acidentes graves no ano. Arquivos em
[`explain/`](explain/): a [consulta](explain/consulta.sql), o plano [antes](explain/antes.txt) e
o plano [depois](explain/depois.txt).

```sql
SELECT br, uf, km_inicio, graves FROM analitico_marts.mart_risco_trecho_ano
WHERE ano = 2025 AND br <> 0 ORDER BY graves DESC LIMIT 20;
```

| | Antes | Depois |
|---|---|---|
| Plano | `Seq Scan` + `Sort` (top-N heapsort) | `Index Scan Backward` no índice `(ano, graves)` |
| Linhas lidas para devolver 20 | 105.942 (100.555 descartadas pelo filtro) | 20 |
| Páginas (`Buffers: shared hit`) | 1.496 | 7 |
| Tempo de execução (3 execuções, cache quente) | 9,96 / 11,12 / 11,20 ms | 0,10 / 0,05 / 0,07 ms |

O índice vem da configuração `indexes` do próprio modelo, e não de migração (combinado no
contrato), então é recriado a cada `dbt build`, junto com a tabela. Com o índice em `(ano,
graves)`, o PostgreSQL entra direto no ano pedido e lê o índice de trás para a frente, que já é
a ordem de `graves DESC`: para nas 20 primeiras entradas, sem ordenar nada.

Dois detalhes do plano "antes": a estimativa era de 357 linhas para o ano, e vieram 5.387. O
dbt cria a tabela sem rodar `ANALYZE`, então o planejador começa sem estatística da tabela nova
(o autovacuum corrige depois). Com o índice, a estimativa errada deixa de importar, porque o
`LIMIT 20` para a leitura de qualquer jeito.

O mesmo raciocínio deu os outros índices do modelo: `(chave_trecho, ano)` no fato, para o
detalhe de um trecho ao longo dos anos, e a chave única de cada dimensão.

## Tempo

No `dbt build` inteiro, os modelos desta parte levam ~39 s, quase tudo na `fct_ocorrencia`
(25 s para 2,2 milhões de linhas) e na `dim_trecho` (6,5 s, pelo centro geométrico de cada
trecho). As views do staging levam menos de 0,4 s cada.

## Cuidado: o slot do CDC e o disco

Cada `dbt build` regrava a `fct_ocorrencia` (~500 MB) e gera o mesmo tanto de WAL. Com o
Debezium da E2 parado, o slot de replicação `blackspot_cdc` impede o PostgreSQL de apagar esse
WAL ([`docs/e2/cdc.md`](../e2/cdc.md), "Slot de replicação"): na máquina em que esta parte foi
feita, o slot chegou a reter 1,3 GB e o disco encheu no meio do build. Se o CDC não for usado,
apague o slot (`SELECT pg_drop_replication_slot('blackspot_cdc')`). O Debezium o recria quando
subir de novo, mas não retoma do ponto em que parou: as mudanças feitas enquanto o slot não
existia não viram eventos.
