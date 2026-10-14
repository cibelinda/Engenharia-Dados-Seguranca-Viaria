# Diário de bordo

Uma entrada por semana, no formato **o que foi medido / o que surpreendeu / o que foi
decidido**. O que foi feito em cada commit, por quem e quando, fica no histórico do git.
O antigo `commits.md` (removido no PR #15) continua em `git show 58468f7:commits.md`.
Os usos de IA ficam registrados no [`AI-USAGE.md`](AI-USAGE.md).

As semanas seguem o [cronograma da disciplina](https://github.com/UnB-BD2/PlanoEnsino/blob/main/_data/cronograma.yml):
a Semana 7 começa em 22/09/2026 e a Semana 10, em 13/10/2026, data da E2.

## Semana 7 — E1 (22 a 28/09/2026)

Reconhecimento da fonte, pergunta e recorte, esquema, carga e ADR 0001.

### O que foi medido

- **Fonte** ([`docs/fontes/`](docs/fontes/README.md)): 50 arquivos da PRF (2007–2026), cerca
  de 370 MB em ZIP e 4 GB descompactados, vindos de dois sistemas de registro: BR-Brasil
  (2007–2016) e BAT (2017+). Entre eles, 490.283 IDs de acidente colidem.
- **Recorte** ([`docs/pergunta-e-recorte.md`](docs/pergunta-e-recorte.md)): BAT 2017–2025,
  com 632.713 ocorrências e 1.654.197 registros de pessoa.
- **Perfil** ([`docs/caracterizacao-da-carga.md`](docs/caracterizacao-da-carga.md)):
  `(id, pesid, id_veiculo)` é único em todo o recorte. As 144.628 linhas com `pesid = 0`
  são veículos sem pessoa.
- **Carga:** 2.286.910 registros lidos, 29 rejeitados. O banco ocupa 731 MB.
- **Medição do ADR 0001:** o modelo adotado (normalizado e insert-only) ocupa 731 MB, contra
  784 MB da opção nula. A Q2 leva 708 ms, contra 618 ms. Uma republicação de 2024
  acrescenta 85 MB.

### O que surpreendeu

- **A PRF regrava arquivos no mesmo ID e com o mesmo nome, inclusive anos fechados.** 2024
  foi regravado em 23/09/2026, 4 dias antes do reconhecimento. Os arquivos não têm coluna de
  versão.
- A página da PRF tem links ocultos que apontam para arquivos de outros anos. Por isso os
  IDs do manifesto foram validados à mão.
- O dicionário oficial não bate com os arquivos (formato de `data_inversa`, separador
  decimal de `km`).
- Há IDs corrompidos em notação científica (`4e+05`), e o valor original não é recuperável.
- `(id, pesid)` não é único no BAT. Todas as repetições vêm de `pesid = 0`.
- A queda de 22,6% nas ocorrências em 2018 quase não aparece nos acidentes graves (−6%).
- O modelo normalizado ocupa **menos** espaço que a opção nula, mesmo com índices e
  versionamento.

### O que foi decidido

- **Pergunta de gestão (#1):** quais trechos de 10 km concentraram mais acidentes com mortos
  ou feridos graves entre 2017 e 2025, e se esses trechos se mantêm de um ano para o outro.
- **Recorte (#2):** BAT 2017–2025, conjuntos `ocorrencia` e `pessoa`. 2026 fica fora por ser
  parcial e regravado todo mês.
- **Modelagem (#3, #6):** insert-only, versionado por lote, sendo o lote o ano
  ([ADR 0001](docs/adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md)).
  Ocorrências com `br = 0` ficam no banco, mas saem do ranking.
- **Divergência de hash** é tratada como aviso, e não como erro, porque a PRF republica sem
  aviso.
- **Evidência de revisão (#7):** a evidência indireta fica registrada na E1. A comparação
  direta das versões fica para depois da próxima atualização mensal da PRF e vira insumo
  da E2.
- **Processo (#9):**
  - o `commits.md` foi substituído pelo histórico do git, por este diário e pelo `AI-USAGE.md`;
  - toda mudança entra por PR, com uma branch por issue e `Closes #N` na descrição;
  - cada PR é revisado por outra pessoa da Squad antes do merge;
  - quem usar IA num PR atualiza o `AI-USAGE.md` no mesmo PR.

## Semana 8 (29/09 a 05/10/2026)

Semana sem desenvolvimento no pipeline: a E1 foi entregue em 28/09 (tag `e1`) e a Squad
esperou a avaliação.

- **Feito:** aba de arquitetura e modelos no site (PR #30), com o pipeline e os modelos
  conceitual, lógico e físico.
- **Medido, surpreendeu, decidido:** nada nesta semana.

## Semana 9 — correções da E1 e início da E2 (06 a 12/10/2026)

Avaliação da E1 em 12/10. Duas correções da professora na avaliação da E1: o banco não era apropriado para dados com
latitude e longitude, e o BR-Brasil não podia ser descartado só por estar em outro formato.

### O que foi medido

- **Coordenadas** ([ADR 0002](docs/adr/0002-banco-espacial-postgis.md)): 100% das 681.425
  ocorrências do BAT (2017–2026) têm latitude e longitude; nenhum arquivo do BR-Brasil
  (2007–2016) tem as colunas.
- **Dataset completo** ([ADR 0003](docs/adr/0003-dataset-completo-br-brasil-e-bat.md)): os 50
  arquivos, 2.243.625 ocorrências e 5.156.169 registros de pessoa lidos; 2.243.584 ocorrências,
  4.008.904 veículos, 4.998.779 pessoas, 934.079 causas e 1.051.668 tipos carregados; 1.275 linhas
  rejeitadas, todas com motivo conhecido. Carga do zero em 467 s; banco com 2,7 GB.
- **PostGIS:** acidentes graves num raio de 2 km em 46 ms, contra 608 ms com haversine sem
  índice, com a mesma resposta. A coluna `geom` e os dois índices GiST ocupam ~102 MB.
- **Coordenada × BR + km:** em 87% dos trechos de 10 km do BAT, a distância mediana dos
  acidentes ao centro do trecho fica até 5 km.

- **E2, primeira versão do lote** (PR #35, ainda sobre o recorte da E1): 27 partições Delta
  (3 tabelas × 9 anos) em 46 s; a segunda execução não grava nada (2 s).

### O que surpreendeu

- **Metade das coordenadas de 2019 a 2024 não é o local do acidente.** São pontos padrão
  repetidos: um ponto em São José/SC reúne 438 acidentes do km 205 ao 210,7. Em 2017, 2018 e
  2025 a fração cai para 6–16%, e em 2026 para 0,1%. Só apareceu com o agrupamento espacial.
- No BR-Brasil, `mortos` e `feridos_graves` batem com as pessoas quase sempre (só 8 e 19
  ocorrências não batem, por pessoas rejeitadas). O perfil inicial indicava 4% de divergência,
  mas era um erro dele: não tirava os espaços de `'Morto       '`.
- O BR-Brasil marca ausência com o texto `(null)`, tem `km` negativo (19), ano de fabricação
  9999 e IDs de ocorrência repetidos no mesmo arquivo (35).
- O `km` de 2016 já usa vírgula decimal, e não ponto, como dizia o reconhecimento.

- **As imagens do MinIO deixaram de ser publicadas:** o `docker pull` de `minio/minio` e de
  `quay.io/minio/minio` é recusado. A camada analítica fica num volume do Docker.

### O que foi decidido

- **Banco espacial:** PostgreSQL 18.6 com PostGIS 3.6. `ocorrencia.geom` é uma coluna gerada
  das coordenadas (SIRGAS 2000), com índices GiST. O modelo da E1 continua o mesmo.
- **Dataset completo:** BR-Brasil e BAT no mesmo esquema, com o formato tratado na carga e o
  vocabulário de cada sistema guardado como veio. A pergunta de gestão passa a cobrir 2007–2025.
- **Migrações novas** (`V0009`–`V0012`), sem editar as da E1: um banco da E1 sobe para o esquema
  novo só aplicando as quatro.
- **Coordenadas repetidas** ficam como a PRF publicou; marcar e tratar é trabalho da E3.
- **Divisão da E2 em três partes independentes** (PR #34): lote (#31, Ana), CDC (#32, Cibelly)
  e ADR 0004, medição e diário (#33, Maria). A base comum (`wal_level=logical`, volume
  `lakehouse`, `compose/lote.yml` e `compose/cdc.yml`) vai para a `main` antes, para nenhum PR
  depender de outro.
- **Contrato da camada analítica** ([`docs/e2/README.md`](docs/e2/README.md)): Parquet com
  tabela Delta, zstd, partição pelo ano do evento.

## Semana 10 — E2 (13/10/2026)

Ingestão em lote, revisão dos PRs da E2, Release Notes 1 e ADR 0004.

### O que foi medido

- **Lote com os 20 anos** ([`docs/e2/lote.md`](docs/e2/lote.md)): 80 partições Delta (5 tabelas)
  em 87–94 s, com 138 MB; a segunda execução não grava nada. A republicação simulada de 2024
  reescreve só as 5 partições do ano, sem duplicar.
- **Medição do ADR 0004** ([`bench/medicao_e2.py`](bench/medicao_e2.py)):
  - recarga completa dentro do banco (opção nula) em 11 s, mas com 1,4 GB e sem formato aberto;
  - recarga completa em Delta em 82–86 s;
  - lote incremental: 7 s sem mudança e 3,3 s para republicar 2024;
  - uma republicação de 2024 são 627.797 eventos de INSERT para um CDC, numa transação;
  - zstd ocupa 21% (ocorrência) e 36% (pessoa) menos que o snappy.
- **Delta × Iceberg:** a Q1 lida pelo DuckDB leva 108 ms no Delta e 79 ms no Iceberg. Das quatro
  mudanças de esquema testadas, o deltalake faz uma (adicionar coluna) e o Iceberg faz as quatro.

### O que surpreendeu

- **O lote da E2 quebrava em cima da `main`:** a branch saiu de antes do PostGIS, e a coluna `geom`
  (tipo `USER-DEFINED`) não tinha conversão para o Arrow. Só apareceu rodando a esteira inteira
  com o merge, na revisão do PR #35.
- **A PRF reusa IDs entre o BR-Brasil e o BAT**, e o teste de duplicata, que contava só o ID,
  falhava com os 20 anos. Pela chave primária do banco, que começa por `id_lote`, não há
  duplicata.
- **O Delta, pelo deltalake, ignora sem aviso o alargamento de tipo:** a escrita de int64 numa
  coluna int32 passa, e a coluna continua int32.
- **zstd não deixa a leitura mais rápida:** a Q1 varia mais entre rodadas do que entre codecs.

### O que foi decidido

- **Revisão do lote (PR #35):** a geometria vai em WKB (`ST_AsBinary`), a escrita usa
  `schema_mode="merge"` para coluna nova, a leitura acontece numa transação `REPEATABLE READ` e os
  testes contam duplicata pela chave primária. As tabelas de causas e tipos entraram no lote.
- **ADR 0004 (proposto):** lote incremental por ano como caminho principal da camada analítica,
  com o CDC como trilha de mudanças. Delta com zstd, partição pelo ano do evento.
- **Release Notes 1** (tag `r1`), com as correções da E1.
- **Pendente na E2:** o CDC (#32).

