# ADR 0001: Modelar a origem normalizada e insert-only, versionada por lote de carga

- **Status:** aceito, revisado em 2026-10-13. Continua valendo depois das correções da E1, com o
  banco espacial do [ADR 0002](0002-banco-espacial-postgis.md) e o dataset completo do
  [ADR 0003](0003-dataset-completo-br-brasil-e-bat.md). O contexto é o da decisão (recorte da E1);
  a medição foi refeita sobre o dataset completo, que disparou dois gatilhos de revisão (seção
  "Revisão de 2026-10-13").
- **Data:** 2026-09-28 (rascunho em 2026-09-27; revisão em 2026-10-13)
- **Issue:** #6 (esquema da #3, carga da #4, evidência da #7)

## Contexto

Pergunta de gestão (PR #10): *quais trechos de 10 km das rodovias federais concentraram mais
acidentes com mortos ou feridos graves entre 2017 e 2025, e esses trechos se mantêm de um ano
para o outro?*

Carga (detalhes em [`caracterizacao-da-carga.md`](../caracterizacao-da-carga.md)):

- **Volume:** 632.713 ocorrências e 1.654.197 registros de pessoa (BAT 2017–2025), ~800 MB
  em CSV.
- **Estrutura:** o arquivo `pessoa` tem uma linha por pessoa em veículo, com
  `(id, pesid, id_veiculo)` único, e repete todos os dados da ocorrência e do veículo em cada
  linha. 144.628 linhas são veículos sem pessoa (`pesid = 0`). São 1.191.470 veículos
  distintos, com média de 1,96 veículo e 2,61 registros por ocorrência.
- **Escrita:** lote mensal. A PRF substitui o arquivo do ano inteiro, sem versão. Anos
  fechados são regravados: 2024 foi regravado em 23/09/2026, e 2017–2021 em 27/09/2024.
  Uma regravação de 2024 tem 73.202 ocorrências e 196.448 registros de pessoa.
- **Leitura:** agregação por trecho (BR + UF + faixa de km) e por ano sobre todo o recorte;
  sem acesso por chave e sem tempo real. Latência tolerada: meses.
- **A E2 é sobre captura de mudanças.** As regravações da PRF são o material dela.

Restrições: custo zero; PostgreSQL 18 já disponível no compose; equipe de três pessoas com
SQL e Python; migrações com Flyway; licença dos dados ambígua (não redistribuímos os arquivos).

O enunciado pede que o modelo responda a três perguntas:

1. **Histórico:** CRUD (sobrescreve) ou insert-only?
2. **Normalização:** até onde normalizar?
3. **Carimbo de tempo:** que tempo cada tabela guarda?

## Alternativas

### A. Opção nula: uma tabela por arquivo, espelhando o CSV

Duas tabelas (`datatran`, `acidentes`) com as colunas do CSV. Cada carga faz truncate e recarrega o ano.

- **A favor:** é a mais simples de carregar e de explicar. A Q1 lê uma tabela só, sem join.
  Não precisa decidir chave de pessoa nem de veículo.
- **Contra:** perde a versão anterior a cada regravação, e a E2 fica sem material. Os dados
  da ocorrência se repetem em cada linha de `acidentes` (~2,6 vezes). O banco não garante
  integridade: não há FK ocorrência → pessoa, e `(id, pesid)` repete.

### B. Modelo normalizado com CRUD

Tabelas `ocorrencia`, `veiculo` e `pessoa`, com FKs e tabelas de domínio (causa, tipo,
classificação). Cada carga faz upsert pela chave natural.

- **A favor:** integridade garantida pelo banco. Sem repetição de dados. Uma única versão de
  cada linha, sem filtro de versão vigente nas consultas.
- **Contra:** a regravação sobrescreve. Não dá para saber o que a PRF mudou, e a perda é
  irreversível. Linhas que a PRF removeu ficam no banco, a menos que a carga também apague.

### C. Modelo normalizado insert-only, versionado por lote

O mesmo modelo de B, mais a tabela `lote_carga`. Toda linha referencia o lote que a trouxe,
e a chave inclui o lote. Uma regravação insere uma nova versão e não altera as anteriores.
As consultas leem uma view de versão vigente.

- **A favor:** preserva cada versão publicada pela PRF, que é o material da E2. Permite
  responder "o que mudou em 2024 depois de fechado". Tem a integridade de B.
- **Contra:** volume cresce a cada regravação. Toda consulta paga o filtro de versão vigente.
  A carga precisa de lote, idempotência e comparação de versões.

**Definido na #3** ([`modelagem-origem.md`](../modelagem-origem.md)): o lote é o ano, e não o
arquivo. Os dois arquivos do ano entram juntos, para que as FKs de veículo e pessoa não cruzem
versões, e um lote novo só é criado quando o SHA-256 de algum deles muda. O custo medido está
em "Medição".

## Decisão

**Alternativa C: modelo normalizado, insert-only, versionado por lote de carga.** A decisão foi
tomada na #3 e está implementada nas migrações `V0001`–`V0008` e na carga da #4. Na E1, a
medição mostrou que ela não custava espaço nem tempo de consulta relevantes em relação à opção
nula. No dataset completo o custo é maior (12% de espaço e ~1 s por consulta) e continua muito
abaixo da latência tolerada (seção "Revisão de 2026-10-13").

Respostas às três perguntas ([`modelagem-origem.md`](../modelagem-origem.md)):

1. **Histórico:** insert-only, versionado por lote. O lote é o ano: os dois arquivos do ano
   entram juntos, e um lote novo só é criado quando o SHA-256 de algum deles muda.
2. **Normalização:** ocorrência, veículo e pessoa separados, com domínios de causa e tipo. A
   linha com `pesid = 0` vira veículo sem pessoa, e não pessoa. Não normalizamos mais do que
   isso (município, UF, BR ficam como texto/número na ocorrência): a pergunta não precisa, e
   harmonizar descrições é transformação (E3).
3. **Carimbo de tempo:**
   - **evento:** `ocorrencia.ocorrido_em` (`data_inversa` + `horario`), `timestamp` sem fuso, porque a PRF não informa;
   - **ingestão:** `lote_carga` (início e fim da carga) e `lote_arquivo` (SHA-256 e `Last-Modified` do Drive de cada arquivo);
   - **processamento:** não existe na E1.

## Medição

Script: [`bench/medicao_adr.py`](../../bench/medicao_adr.py). Resultado:
[`bench/resultados/medicao_adr.json`](../../bench/resultados/medicao_adr.json). A alternativa A
é montada no mesmo banco a partir da versão vigente: uma tabela plana por arquivo, sem FK e sem
índice. Consultas Q1 e Q2 de [`caracterizacao-da-carga.md`](../caracterizacao-da-carga.md), com
`EXPLAIN (ANALYZE, BUFFERS)`, 5 execuções depois de uma de aquecimento, mediana.

```bash
docker compose up --build -d && docker compose wait load
docker compose run --rm -v ./bench:/app/bench load python bench/medicao_adr.py
```

### Dataset completo (2026-10-13)

PostgreSQL 18.6 + PostGIS 3.6 no Docker, banco carregado do zero com os 20 anos (C). Q1 e Q2
sobre 2007–2025.

| | A (opção nula) | C (adotada) |
|---|---|---|
| Linhas | 2.243.584 + 5.155.023 | 2.243.584 ocorrências, 4.008.904 veículos, 4.998.779 pessoas (+ 934.079 causas e 1.051.668 tipos do BAT) |
| Tamanho em disco, com índices | 2.215 MB | 2.487 MB (2.704 MB com causas e tipos, que A não espelha) |
| Q1, mediana (mín.–máx.) | 1.696 ms (1.635–1.771) | 2.431 ms (2.399–2.493) |
| Q2, mediana (mín.–máx.) | 1.727 ms (1.708–1.764) | 2.759 ms (2.639–2.824) |
| Buffers lidos (8 kB) | 69.200 | 71.554 |

**Republicação de 2024 em C** (simulada com um lote novo igual ao vigente, e desfeita):

| | Valor |
|---|---|
| Linhas acrescentadas | 627.797 (73.201 ocorrências, 139.693 veículos, 179.244 pessoas, 111.388 causas, 124.271 tipos) |
| Espaço acrescentado | 69 MB medidos; ~110 MB pela proporção do ano em cada tabela (+4% do banco) |
| Q1 / Q2 com duas versões de 2024 | 2.710 ms / 2.729 ms |
| Buffers lidos | 71.712 (+158) |

O espaço medido fica abaixo do esperado porque a republicação reaproveitou o espaço liberado por
uma rodada anterior da medição, desfeita antes; a estimativa proporcional é a referência.

**O que mudou em relação à E1:**

- **C passou a ocupar mais que A** (+12%; na E1, −7%). A normalização ainda tira a repetição dos
  dados do acidente no arquivo de pessoa, mas C tem índices que A não tem: PKs, FKs, os índices
  de consulta da `V0007` e, desde o ADR 0002, a coluna `geom` com os índices GiST (~102 MB).
- **C ficou 43% (Q1) e 60% (Q2) mais lenta que A**, contra 2% e 15% na E1. Os buffers lidos
  diferem só 3%, então o tempo a mais vem de processar a view `ocorrencia_vigente`, e não de ler
  mais disco.
- **As versões antigas continuam quase sem custo de leitura:** com duas versões de 2024, os
  buffers sobem 0,2%. A view acha o lote vigente de cada ano e busca só as linhas dele pela PK
  `(id_lote, id)`.

### Recorte da E1 (2026-09-28)

PostgreSQL 18.6 sem PostGIS, BAT 2017–2025. Mantido como registro da decisão original.

| | A (opção nula) | C (adotada) |
|---|---|---|
| Linhas | 632.708 + 1.654.173 | 632.708 ocorrências, 1.191.461 veículos, 1.509.549 pessoas |
| Tamanho em disco, com índices | 784 MB | 731 MB |
| Q1, mediana (mín.–máx.) | 669 ms (572–803) | 685 ms (674–718) |
| Q2, mediana (mín.–máx.) | 618 ms (584–651) | 708 ms (696–716) |
| Republicação de 2024 | — | +392.138 linhas, +85 MB (+12%) |

## Revisão de 2026-10-13: gatilhos disparados

O dataset completo disparou dois dos três gatilhos de revisão definidos na decisão original:

| Gatilho | Limite | Medido | Por quê |
|---|---|---|---|
| Tamanho do banco | 2 GB | **2,7 GB** | O escopo passou de 9 para 20 anos, com o BR-Brasil (ADR 0003). O gatilho supunha crescimento por republicações, a partir de 731 MB |
| Q2 na mediana | 2 s | **2,8 s** | 3,5 vezes mais ocorrências (2,2 milhões contra 632 mil). A opção nula também subiu, para 1,7 s |
| Republicações mudam menos de 1% das linhas | — | pendente | Comparação direta da #7, em 26/10/2026 |

**Reavaliação.** Os dois gatilhos medem custo, e o custo subiu por causa do volume, não por causa
do insert-only: a opção nula, com o mesmo dado, ocupa 2,2 GB e leva 1,7 s. O que levou à escolha
de C não mudou. A PRF continua regravando arquivos sem versão, inclusive o BR-Brasil inteiro em
2022, e só C guarda o que ela mudou, que é o material da E2. A restrição que importa para a
pergunta é a latência tolerada, de meses (caracterização da carga), e 2,8 s está muito abaixo
dela. **A decisão se mantém.**

**O que muda é o ritmo de crescimento.** Com 2026 no banco, o ano corrente vira um lote novo a
cada regravação mensal. A caracterização estima ~1,2 GB por ano: ~700 MB das regravações do ano
corrente e ~500 MB das regravações de anos fechados. Esse é o primeiro ponto a atacar se o espaço
apertar.

**Gatilhos recalibrados** para o dataset completo (substituem os da decisão original):

- o banco passar de **6 GB** (hoje 2,7 GB; ~3 anos no ritmo estimado);
- a **Q2 passar de 10 s** na mediana do `bench/medicao_adr.py`, ou surgir um consumidor que
  precise de resposta em menos de 5 s (por exemplo, um painel interativo na E4);
- a #7 mostrar que as republicações mudam **menos de 1%** das linhas de um ano (mantido): aí
  gravar só as linhas alteradas economizaria ~99% dos ~110 MB por republicação de um ano do BAT,
  e mais ainda nas regravações mensais do ano corrente.

## Evidência de revisão da origem (#7)

Detalhes em [`caracterizacao-da-carga.md`](../caracterizacao-da-carga.md), "Evidência de
revisão da origem".

- **Evidência indireta:** nenhum dos 50 arquivos tem coluna de atualização ou de versão, e a
  PRF regrava os arquivos no mesmo ID e com o mesmo nome: 2024 em 23/09/2026 (ano fechado),
  2025 em 18/03/2026 e 2026 mensalmente. A origem sobrescreve, e isso sustenta a escolha de
  insert-only.
- **Comparação direta: pendente.** Data prevista: **26/10/2026**, depois da próxima
  atualização mensal da PRF. Nela, 2024, 2025 e 2026 serão baixados de novo e comparados, por
  hash, com a linha de base de 2026-09-27
  ([`docs/fontes/linha-de-base-2026-09-27/`](../fontes/linha-de-base-2026-09-27/sha256_2026-09-27_2024-2026.txt)).
  Os lotes de 2024 e 2025 já carregados têm esses mesmos hashes; um ano republicado vira um
  lote novo, e os dois lotes são comparados por chave. É o próprio insert-only que torna essa
  comparação possível.
  O resultado alimenta o terceiro gatilho de revisão abaixo e a E2.

## Consequências

**O que ganhamos**

- Cada versão publicada pela PRF fica guardada. "O que a PRF mudou em 2024 depois de fechado?"
  tem resposta, e é o material da E2.
- Sem repetição dos dados do acidente: a normalização tira ~2,2 repetições por ocorrência do
  arquivo de pessoa. Na E1, isso deixava C 7% menor que A; no dataset completo, os índices pesam
  mais e C fica 12% maior (ver "O que perdemos").
- Integridade garantida pelo banco (PKs, FKs, CHECKs, cobertos pelos testes da #8). O que não
  cabe no esquema aparece em `linha_rejeitada` com o motivo (1.275 linhas no dataset completo),
  em vez de entrar sem aviso.

**O que perdemos**

- **Espaço:** C ocupa 12% mais que A (2.487 MB contra 2.215 MB), pelos índices e pela geometria.
- **Espaço a cada republicação:** uma republicação de um ano como 2024 acrescenta ~628 mil linhas
  e ~110 MB, mesmo que a PRF tenha mudado poucas linhas, porque o lote grava o ano inteiro. Com
  ~4,5 regravações de ano fechado por ano e as regravações mensais do ano corrente, são
  ~1,2 GB por ano.
- **Tempo de consulta:** a Q2 fica 1 s (60%) mais lenta que em A (2,8 s contra 1,7 s), pelo
  processamento da view de versão vigente. Na E1 eram 90 ms (15%).
- **Risco de consulta errada:** quem ler `ocorrencia` em vez de `ocorrencia_vigente` conta cada
  republicação duas vezes. Só as views dão a resposta certa.
- **Carga mais complexa:** controle de lote, status, SHA-256 e idempotência (~400 linhas na #4,
  contra um `COPY` por arquivo em A).
- **Unicidade de `pesid` e `id_veiculo` só dentro do lote:** entre lotes vigentes de anos
  diferentes, ela depende da carga, não de uma restrição do banco.

**O que se torna irreversível**

- Nada do dado. Voltar de C para B custa um `DELETE` das versões não vigentes e uma migração que
  tire `id_lote` das chaves. O contrário não existe: com B, as versões sobrescritas não voltariam.
- O que tem custo de reverter é o formato das chaves: `id_lote` está em todas as PKs e FKs, e
  as consultas usam as views. Trocar o lote-ano por outro esquema de versão (por exemplo, só as
  linhas alteradas) é uma migração de todas as tabelas de dado e da carga.

**Gatilho de revisão**

Os gatilhos da decisão original (banco acima de 2 GB, Q2 acima de 2 s) dispararam com o dataset
completo. Foram reavaliados e recalibrados na seção "Revisão de 2026-10-13", que tem os
gatilhos vigentes.
