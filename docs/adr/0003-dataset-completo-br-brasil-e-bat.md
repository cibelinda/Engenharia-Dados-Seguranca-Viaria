# ADR 0003: Carregar o dataset completo da PRF (BR-Brasil e BAT, 2007 em diante)

- **Status:** aceito
- **Data:** 2026-10-12
- **Substitui:** o recorte "BAT 2017–2025" de [`pergunta-e-recorte.md`](../pergunta-e-recorte.md)
  (issues #1 e #2), usado na E1
- **Origem:** correção da professora na avaliação da E1

## Contexto

Na E1, a origem carregou só o sistema BAT (2017–2025), com ocorrência e pessoa. O BR-Brasil
(2007–2016) ficou de fora porque publica em outro formato: separador `,` no arquivo de pessoa,
três formatos de data, decimal com ponto, aspas em uns anos e não em outros, e IDs que colidem
com os do BAT (490.283).

A correção da professora: **diferença de formato não justifica descartar dados. Tratar formatos
heterogêneos é o trabalho da engenharia de dados**, e o pipeline deve cobrir o dataset completo
da PRF.

Verificamos se a correção faz sentido, e não só a cumprimos:

- **A pergunta de gestão melhora.** "O trecho se mantém de um ano para o outro" é uma pergunta
  de série histórica: com 2017–2025 são 9 anos; com o dataset completo, 19 anos fechados. Um
  trecho que é ponto negro há 19 anos é um caso muito mais forte para intervenção.
- **O que a pergunta usa existe nos dois sistemas.** `br`, `km`, `uf`, `data_inversa`, `mortos`
  e `feridos_graves` estão em todos os arquivos de ocorrência de 2007 a 2026. Medido na carga:
  `mortos` e `feridos_graves` batem com as pessoas em `Morto`/`Ferido Grave` em todas as
  ocorrências do BR-Brasil, menos 8 e 19 que perderam pessoas para `linha_rejeitada`.
- **As diferenças de formato têm regra.** O separador sai do cabeçalho; a data sai da posição
  dos separadores; o decimal aceita ponto e vírgula; `(null)` é marcador de ausência. Nenhuma
  exige passo manual.
- **A colisão de IDs não exige chave nova.** O lote é o ano (ADR 0001), cada ano pertence a um
  só sistema, e toda PK de dado começa por `id_lote`. Dois acidentes com o mesmo `id` em 2010
  e 2025 estão em lotes diferentes e não colidem. O sistema fica registrado no lote
  (`lote_carga.sistema`, coluna gerada do ano).

O que a correção **não** resolve, e fica registrado:

- **A troca de sistema é uma quebra na série.** As ocorrências caem de 169.197 (2014) para
  122.158 (2015), 96.362 (2016) e 89.567 (2017). Os acidentes graves variam bem menos (−13% e
  −11% nas mesmas passagens), o que sustenta a hipótese de mudança no critério de registro
  (acidente sem vítima deixando de gerar boletim), e não de queda real. Comparar trechos através
  da quebra pede cuidado na E3: a persistência deve ser medida pela posição relativa do trecho em
  cada ano (ranking ou percentil), e não pela contagem absoluta.
- **Os vocabulários são diferentes** (`Morto` × `Óbito`, `Ferido Grave` × `Lesões Graves`, 11 ×
  92 causas). A origem guarda o que cada sistema publicou, e a harmonização é transformação (E3).
- **O BR-Brasil não tem coordenada** ([ADR 0002](0002-banco-espacial-postgis.md)). De 2007 a 2016,
  o único referencial é BR + km.

## Alternativas

### A. Manter o recorte BAT 2017–2025 (E1)

- **A favor:** um formato só; nada a mudar.
- **Contra:** descarta 10 dos 20 anos publicados (1,56 milhão de ocorrências e 3,37 milhões de
  pessoas) por um motivo de formato, que é justamente o que a disciplina pede para tratar.
  Deixa a persistência com 9 anos.

### B. Converter o BR-Brasil para o formato do BAT antes de carregar (pré-processamento em arquivo)

Um script reescreveria os CSVs de 2007–2016 no formato do BAT, e a carga continuaria a mesma.

- **A favor:** a carga não muda.
- **Contra:** cria uma cópia intermediária dos dados, sem versão, entre o arquivo da PRF e o
  banco. O SHA-256 que o lote registra deixaria de ser o do arquivo publicado, e a rastreabilidade
  da E1 (que versão da PRF gerou esta linha?) se perde.

### C. Carregar os dois sistemas no mesmo esquema, tratando o formato na carga (adotada)

A carga lê cada arquivo como a PRF publica e converte para o esquema; o esquema aceita o que é
diferente de conteúdo (nulos e vocabulário do BR-Brasil).

- **A favor:** um único pipeline para os 50 arquivos, sem passo manual. O lote continua
  registrando o SHA-256 do arquivo publicado. O arquivo de todas as causas e tipos (BAT) também
  entra, e o dataset fica completo.
- **Contra:** algumas restrições ficam mais fracas, porque o BR-Brasil não as cumpre: `uf`, `br`,
  `km`, a causa e os campos descritivos passam a aceitar NULL, e a regra "sem veículo ⇔ pedestre,
  testemunha ou cavaleiro" sai do banco e fica só na carga, para o BAT.

### D. Um esquema por sistema (`br_brasil.ocorrencia`, `bat.ocorrencia`)

- **A favor:** cada esquema com as suas restrições, sem enfraquecer nenhuma.
- **Contra:** toda consulta de 2007 a 2025 vira um `UNION`, e as views de versão vigente, os
  índices e os testes se duplicam. A pergunta de gestão é uma só, sobre os 19 anos.

## Decisão

**Alternativa C.** Implementada em:

- [`V0010__dataset_completo.sql`](../../db/migrations/V0010__dataset_completo.sql): ano a partir
  de 2007, `lote_carga.sistema`, colunas que passam a aceitar NULL, vocabulário do BR-Brasil nos
  CHECKs, `nacionalidade` e `naturalidade` em `pessoa`;
- [`V0011__causas_e_tipos.sql`](../../db/migrations/V0011__causas_e_tipos.sql): `ocorrencia_causa` e
  `ocorrencia_tipo`, a partir do arquivo de todas as causas e tipos (BAT);
- [`V0012__visoes_vigentes.sql`](../../db/migrations/V0012__visoes_vigentes.sql): as views com as
  colunas novas;
- [`blackspot/load.py`](../../blackspot/load.py): leitura dos três formatos e dos 20 anos;
- `docker-compose.yml`: o `download` baixa os 50 arquivos.

As migrações da E1 (`V0001`–`V0008`) não foram editadas: um banco da E1 sobe para o esquema novo
aplicando só `V0009`–`V0012`.

**Sobre o arquivo de todas as causas e tipos.** Ele tem uma linha por pessoa × causa × tipo
(4,48 milhões de linhas no BAT). Medido em 2024: o conjunto de causas e o de tipos são os mesmos
para todas as pessoas da ocorrência, cada ocorrência tem exatamente uma causa principal, e a causa
principal e o tipo de ordem 1 são iguais aos do arquivo de ocorrência em 100% dos casos. O conteúdo
novo é, portanto, de nível de ocorrência, e é só ele que entra: as pessoas já vêm do arquivo de
pessoa.

## Consequências

**O que ganhamos**

- Os 20 anos publicados pela PRF no banco, com o mesmo controle de versão da E1.
- A série de 19 anos fechados para medir a persistência dos trechos.
- As causas e os tipos secundários do BAT, que antes ficavam fora.

**O que perdemos**

- **Restrições mais fracas** nas colunas que o BR-Brasil deixa sem valor. Quem consulta o ranking
  precisa filtrar `br IS NOT NULL AND br <> 0 AND km IS NOT NULL`.
- **Tempo de carga:** ~8 min do zero (467 s medidos em 2026-10-12), contra ~80 s na E1, para
  3,5 vezes mais ocorrências e o arquivo de todas as causas (4,5 milhões de linhas).
- **Espaço:** o banco passa de 731 MB para 2,7 GB. O gatilho de 2 GB do ADR 0001 foi pensado para
  o crescimento por republicações do recorte; com o dataset completo, o ponto de partida já é
  maior, e o gatilho precisa ser revisto (sugestão: 5 GB).

**O que se torna irreversível**

- Nada. Voltar ao recorte é apagar os lotes de 2007–2016 e de 2026.

**Gatilho de revisão**

- A E3 concluir que a quebra 2016/2017 impede comparar os sistemas mesmo por ranking relativo:
  aí a persistência passa a ser medida dentro de cada sistema.
- A PRF republicar o BR-Brasil num formato novo (a última gravação é de 24/11/2022).
