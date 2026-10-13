# ADR 0002: Usar um banco espacial (PostgreSQL com PostGIS)

- **Status:** aceito
- **Data:** 2026-10-12
- **Origem:** correção da professora na avaliação da E1
- **Relacionado:** [ADR 0001](0001-modelo-normalizado-insert-only-versionado-por-lote.md) (continua
  valendo), [ADR 0003](0003-dataset-completo-br-brasil-e-bat.md) (dataset completo)

## Contexto

Na E1, a origem era um PostgreSQL 18 sem extensões. A latitude e a longitude de cada acidente
eram guardadas como dois `numeric`, e a pergunta de gestão usava só BR + km.

A correção da professora: **o banco escolhido não é apropriado para os dados, que têm latitude e
longitude, nem para o objetivo do trabalho**. Pediu para verificar a informação e escolher um
banco adequado.

**Verificação** (nos 50 arquivos, em 2026-10-12):

| | BR-Brasil (2007–2016) | BAT (2017–2026) |
|---|---|---|
| Colunas `latitude` e `longitude` | **não existem** em nenhum arquivo | existem em todos (ocorrência, pessoa e todas as causas) |
| Ocorrências com coordenada | 0 de 1.562.165 | 681.419 de 681.419 (100%) |
| Coordenada inválida | — | 33 pares fora do limite (2017, anulados pela carga); 20 pontos fora do Brasil |
| Coordenada padrão, e não o local do acidente | — | **cerca de 50% dos acidentes de 2019 a 2024** estão num ponto exato compartilhado por 10 ou mais acidentes de kms diferentes (um ponto em São José/SC reúne 438 acidentes do km 205 ao 210,7); 6–16% em 2017, 2018 e 2025 |

A informação está correta para o BAT: desde 2017, todo acidente tem coordenada. Antes disso, o
único referencial é BR + km. **Mas a coordenada nem sempre é o local do acidente**: de 2019 a
2024, metade delas é um ponto padrão repetido. Esse achado só apareceu porque o banco passou a
agrupar pontos (seção "Medição"), e ele muda como a coordenada pode ser usada na E3.

**Por que isso importa para o objetivo.** Um *black spot* é, por definição, um lugar onde os
acidentes se concentram. As perguntas que o projeto precisa responder são espaciais: quais
acidentes graves estão a menos de X metros uns dos outros, em que ponto do trecho eles se
concentram, se o ponto negro coincide com uma curva, um trevo ou uma travessia urbana, qual
município ou qual segmento da malha do DNIT contém o ponto. Com dois `numeric`:

- não há tipo geométrico nem sistema de referência: a distância entre dois acidentes tem de ser
  calculada à mão (fórmula de haversine) em cada consulta;
- não há índice espacial: "acidentes num raio de 2 km" é uma varredura da tabela;
- não há funções de agrupamento espacial (clusters de acidentes), nem de cruzamento com outras
  camadas (malha rodoviária, limites municipais do IBGE).

## Alternativas

### A. PostgreSQL sem extensão (a escolha da E1)

- **A favor:** já está pronto; nada muda.
- **Contra:** trata a coordenada como dois números soltos. Nenhuma das operações acima existe
  no banco, e o trabalho iria para o Python ou para a E3, fora do lugar onde o dado mora.

### B. PostgreSQL com PostGIS (adotada)

PostGIS é a extensão espacial do PostgreSQL, e a referência em banco espacial de código aberto
(padrão OGC Simple Features / SQL-MM).

- **A favor:** tipos `geometry`/`geography` com SRID, índice espacial GiST (R-tree), centenas de
  funções (`ST_DWithin`, `ST_ClusterDBSCAN`, `ST_Transform`, `ST_LineLocatePoint` para
  referência linear na malha). **Mantém tudo o que a E1 construiu**: o modelo relacional
  normalizado, o insert-only por lote, as FKs, as migrações do Flyway, as views e os testes. A
  troca é de imagem Docker (`postgres:18.6` → `postgis/postgis:18-3.6`, o mesmo PostgreSQL 18.6)
  e uma migração.
- **Contra:** mais uma dependência (a extensão e a imagem); quem consulta precisa conhecer SRID
  e projeção para medir em metros.

### C. MongoDB (documentos GeoJSON com índice `2dsphere`)

- **A favor:** consultas de proximidade (`$near`, `$geoWithin`) nativas.
- **Contra:** perde o que a E1 garante pelo banco: FKs entre ocorrência, veículo e pessoa, CHECKs
  de domínio, transação por lote e views de versão vigente. Não tem agrupamento espacial nem
  projeção cartográfica. Seria reescrever o esquema, a carga e os testes por um ganho que o
  PostGIS dá sem reescrever.

### D. Banco analítico com extensão espacial (DuckDB spatial)

- **A favor:** rápido para agregações sobre o histórico inteiro.
- **Contra:** é um banco embarcado de um processo só, sem servidor nem concorrência de escrita. A
  E1 pede uma **fonte transacional**. Pode fazer sentido como destino analítico na E3, lendo
  desta origem.

### E. Banco de séries temporais (TimescaleDB) ou de grafos (Neo4j)

- **Contra:** o volume (2,2 milhões de acidentes, carga mensal) não pede particionamento
  temporal, e a pergunta não é sobre relações em rede. O TimescaleDB é também uma extensão do
  PostgreSQL, compatível com o PostGIS, se a E2 vier a precisar.

## Decisão

**Alternativa B: PostgreSQL 18.6 com PostGIS 3.6.** Implementada em:

- `docker-compose.yml`: o serviço `db` usa a imagem `postgis/postgis:18-3.6`;
- [`V0009__postgis.sql`](../../db/migrations/V0009__postgis.sql): `CREATE EXTENSION postgis`,
  coluna `ocorrencia.geom` e índice GiST.

Detalhes:

- **`geom geometry(Point, 4674)` é uma coluna gerada** de `longitude`/`latitude`. A carga continua
  gravando só o que a PRF publicou, e o ponto nunca diverge dos números.
- **SRID 4674 (SIRGAS 2000)**, o referencial geodésico oficial do Brasil (IBGE). Para medir em
  metros, as consultas usam `geom::geography` ou projetam com `ST_Transform(geom, 5880)` (SIRGAS
  2000 / Brazil Polyconic).
- **Índice GiST parcial** (`WHERE geom IS NOT NULL`): o BR-Brasil inteiro não tem ponto.
- **O trecho (BR + UF + km) continua sendo o referencial comum aos 20 anos**: é o único que
  existe antes de 2017. O ponto refina a localização a partir de 2017.

## Medição

Script: [`bench/medicao_espacial.py`](../../bench/medicao_espacial.py). Resultado:
[`bench/resultados/medicao_espacial.json`](../../bench/resultados/medicao_espacial.json).
Rodado em 2026-10-12, PostgreSQL 18.6 + PostGIS 3.6.4 no Docker, sobre o dataset completo
carregado do zero. Tempos: mediana de 5 execuções depois de uma de aquecimento,
`EXPLAIN (ANALYZE, BUFFERS)`.

```bash
docker compose up --build -d && docker compose wait load
docker compose run --rm -v ./bench:/app/bench load python bench/medicao_espacial.py
```

**1. Raio: acidentes graves a menos de 2 km de um ponto** (o centro do maior grupo do item 2,
BR-101/SC em São José):

| | E1: `numeric` + haversine | PostGIS: `ST_DWithin` em `geography` + GiST |
|---|---|---|
| Acidentes graves encontrados | 715 | 715 |
| Tempo, mediana (mín.–máx.) | 608 ms (600–610) | **46 ms** (44–48) |
| Buffers lidos (8 kB) | 426.112 | **5.220** |
| Usa índice espacial | não (varre a tabela) | sim (`ocorrencia_geog_idx`) |

Mesma resposta, 13 vezes mais rápido e 82 vezes menos leitura.

**2. Agrupamento de acidentes graves (`ST_ClusterDBSCAN`, BAT 2017–2025).** Sem PostGIS, não há
como fazer isso no banco.

| Variante | Raio / mínimo | Grupos | Acidentes nos grupos | Tempo |
|---|---|---|---|---|
| Todos os pontos | 100 m / 25 | 325 | 12.224 | 1,0 s |
| Sem os pontos repetidos (item 4) | 300 m / 20 | 129 | 4.160 | 1,8 s |

Com todos os pontos, o maior grupo tem **114 acidentes num raio de 11 m** (BR-020/CE, km 419):
não é um ponto negro, é uma coordenada padrão. Sem os pontos repetidos, os maiores grupos são
pontos negros plausíveis, todos presentes em 8 ou 9 dos 9 anos:

| Acidentes graves | Anos | BR/UF | km (mediana) | Raio do grupo |
|---|---|---|---|---|
| 167 | 9 | BR-101/SC | 205,8 | 1,5 km |
| 130 | 8 | BR-101/ES | 270 | 1,0 km |
| 119 | 9 | BR-101/PE | 69,1 | 0,9 km |
| 92 | 9 | BR-319/RO | 63 | 1,1 km |
| 82 | 9 | BR-101/PB | 88 | 0,7 km |

**3. A coordenada concorda com BR + km?** Para os 4.302 trechos de 10 km do BAT com 20 ou mais
acidentes, a distância mediana dos acidentes ao centro do trecho é de **2,5 km** (p90: 6,2 km), e
87% dos trechos ficam até 5 km. Um trecho de 10 km tem raio de ~5 km: a coordenada e o km
publicados são, em geral, coerentes.

**4. Coordenadas repetidas.** 8.074 pontos exatos concentram 10 ou mais acidentes, somando
225.005 acidentes (33% do BAT); em 7.884 deles, os acidentes são de kms diferentes, o que
descarta "muitos acidentes no mesmo lugar". Fração dos acidentes do ano num ponto repetido:

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| 6,5% | 16,0% | 48,6% | 51,0% | 51,8% | 50,8% | 50,6% | 51,1% | 6,7% | 0,1% |

A origem guarda as coordenadas como a PRF publicou, sem corrigir (é o papel da origem). A E3
precisa marcar esses pontos e decidir o que fazer com eles: tirá-los da análise espacial,
ou reposicioná-los pela BR + km (referência linear na malha do DNIT).

**5. Espaço.**

| | Tamanho |
|---|---|
| Coluna `geom` (681 mil pontos) | 18,8 MB |
| Índice GiST em `geom` | 29,7 MB |
| Índice GiST em `geom::geography` | 53,5 MB |
| Tabela `ocorrencia` inteira, com índices | 775 MB |
| Banco inteiro | 2,7 GB |

O PostGIS acrescenta ~102 MB, 4% do banco.

## Consequências

**O que ganhamos**

- As perguntas espaciais do objetivo (proximidade, agrupamento, cruzamento com outras camadas)
  são respondidas no próprio banco, com índice: 13 vezes mais rápido no raio de 2 km.
- A qualidade da coordenada ficou mensurável. O agrupamento revelou que metade dos pontos de
  2019–2024 é coordenada padrão, o que com dois `numeric` passaria despercebido e distorceria
  qualquer mapa de pontos negros.
- Nada do que a E1 garantia se perde: o modelo, o histórico e as restrições são os mesmos.
- O caminho para georreferenciar o BR-Brasil fica aberto: com a malha do Sistema Nacional de
  Viação (DNIT) carregada como linhas, `ST_LineInterpolatePoint` transforma BR + km em ponto
  (referência linear). É trabalho da E3, porque exige uma fonte nova e validação.

**O que perdemos**

- Uma dependência a mais (a imagem `postgis/postgis` em vez da oficial `postgres`).
- Espaço: ~102 MB entre a coluna `geom` e os dois índices GiST (4% do banco).

**O que se torna irreversível**

- Nada. Remover a extensão é apagar `geom` e o índice; latitude e longitude continuam nas colunas
  de origem.

**Gatilho de revisão**

- A E3 precisar de análise espacial sobre o histórico inteiro mais rápida do que o PostgreSQL
  entrega: aí um destino analítico (DuckDB spatial, por exemplo) lê desta origem.
- A PRF passar a publicar a geometria do trecho, ou a E3 carregar a malha do DNIT: aí entram
  tabelas de linhas e a referência linear.
