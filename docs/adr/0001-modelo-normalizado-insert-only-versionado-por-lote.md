# ADR 0001: Modelar a origem normalizada e insert-only, versionada por lote de carga

- **Status:** aceito
- **Data:** 2026-09-28 (rascunho em 2026-09-27)
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
tomada na #3 e está implementada nas migrações `V0001`–`V0008` e na carga da #4. A medição
abaixo confirma que ela não custa espaço nem tempo de consulta relevantes em relação à opção
nula.

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
[`bench/resultados/medicao_adr.json`](../../bench/resultados/medicao_adr.json). Rodado em
2026-09-28, PostgreSQL 18.6 no Docker, sobre o banco carregado pela #4 (C). A alternativa A é
montada no mesmo banco a partir da versão vigente: uma tabela plana por arquivo, sem FK e sem
índice. Consultas Q1 e Q2 de [`caracterizacao-da-carga.md`](../caracterizacao-da-carga.md),
com `EXPLAIN (ANALYZE, BUFFERS)`, 5 execuções depois de uma de aquecimento, mediana.

```bash
docker compose up --build -d && docker compose wait load
docker compose run --rm -v ./bench:/app/bench tests python bench/medicao_adr.py
```

| | A (opção nula) | C (adotada) |
|---|---|---|
| Linhas | 632.708 + 1.654.173 | 632.708 ocorrências, 1.191.461 veículos, 1.509.549 pessoas |
| Tamanho em disco, com índices | 784 MB | 731 MB |
| Q1, mediana (mín.–máx.) | 669 ms (572–803) | 685 ms (674–718) |
| Q2, mediana (mín.–máx.) | 618 ms (584–651) | 708 ms (696–716) |
| Buffers lidos (8 kB) | 22.618 | 23.404 |

**Republicação de 2024 em C** (simulada com um lote novo igual ao vigente, e desfeita):

| | Valor |
|---|---|
| Linhas acrescentadas | 392.138 (73.201 ocorrências, 139.693 veículos, 179.244 pessoas) |
| Espaço acrescentado | 85 MB (+12% do banco) |
| Q1 / Q2 com duas versões de 2024 | 816 ms / 756 ms |
| Buffers lidos | 23.443 (+39) |

As consultas quase não leem as versões antigas: a view `ocorrencia_vigente` acha o lote
vigente de cada ano e busca só as linhas dele pela PK `(id_lote, id)` (Bitmap Index Scan em
`ocorrencia_pkey`). A diferença de tempo depois da republicação está dentro da variação entre
execuções de A (572–803 ms).

## Evidência de revisão da origem (#7)

Detalhes em [`caracterizacao-da-carga.md`](../caracterizacao-da-carga.md), "Evidência de
revisão da origem".

- **Evidência indireta:** nenhum dos 50 arquivos tem coluna de atualização ou de versão, e a
  PRF regrava os arquivos no mesmo ID e com o mesmo nome: 2024 em 23/09/2026 (ano fechado),
  2025 em 18/03/2026 e 2026 mensalmente. A origem sobrescreve, e isso sustenta a escolha de
  insert-only.
- **Comparação direta: pendente.** Data prevista: **2026-10-27**, depois da próxima
  atualização mensal da PRF (a de 2026 foi em 22/09/2026). Nela, 2024, 2025 e 2026 serão baixados de novo e comparados, por
  chave, com a linha de base de 2026-09-27
  ([`docs/fontes/linha-de-base-2026-09-27/`](../fontes/linha-de-base-2026-09-27/sha256_2026-09-27_2024-2026.txt)).
  O resultado alimenta o terceiro gatilho de revisão abaixo e a E2.

## Consequências

**O que ganhamos**

- Cada versão publicada pela PRF fica guardada. "O que a PRF mudou em 2024 depois de fechado?"
  tem resposta, e é o material da E2.
- C ocupa 53 MB (7%) **menos** que A: a normalização tira a repetição dos dados do acidente
  (~2,6 vezes por ocorrência no arquivo de pessoa), e isso paga os índices e o `id_lote`.
- Integridade garantida pelo banco (PKs, FKs, CHECKs, cobertos pelos testes da #8). O que não
  cabe no esquema aparece em `linha_rejeitada` com o motivo (29 linhas), em vez de entrar sem aviso.

**O que perdemos**

- **Espaço a cada republicação:** uma republicação de um ano como 2024 acrescenta ~392 mil linhas
  e 85 MB, mesmo que a PRF tenha mudado poucas linhas, porque o lote grava o ano inteiro.
  Pelas regravações observadas (9 arquivos-ano em ~2 anos), são ~4 republicações de ano por
  ano, ou ~340 MB por ano.
- **Tempo de consulta:** Q2 fica 90 ms (15%) mais lenta que em A, pela junção com o lote vigente.
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

Revisar esta decisão se qualquer um acontecer:

- o banco passar de **2 GB** (hoje 731 MB; ~15 republicações de ano no ritmo atual, ~4 anos);
- a **Q2 passar de 2 s** na mediana do `bench/medicao_adr.py`;
- a #7 mostrar que as republicações mudam **menos de 1%** das linhas de um ano: aí gravar só as
  linhas alteradas economizaria ~99% dos 85 MB por republicação, e vale o custo da migração.
