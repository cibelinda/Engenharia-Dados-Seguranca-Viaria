# Análise de LGPD

Issue #52. O que o BlackSpot guarda sobre pessoas, sob que base legal, por quanto tempo, como é
descartado e qual o risco de alguém ser reidentificado. O controle de acesso que acompanha esta
análise está em [`acesso.md`](acesso.md).

Esta é a leitura da Squad sobre a Lei 13.709/2018 (LGPD), feita para a disciplina, e não um
parecer jurídico.

## Qual dado é pessoal

A PRF publica os acidentes **sem nome, CPF ou placa**. Mesmo assim, a LGPD considera pessoal o
dado que torna uma pessoa **identificável** (art. 5º, I), e não só o que a identifica de cara. O
dado anonimizado só deixa de ser pessoal quando a reidentificação não é possível com meios
razoáveis (art. 12), e a medição abaixo mostra que aqui ela é.

| Dado | Onde | Por que importa |
|---|---|---|
| `idade`, `sexo`, `nacionalidade`, `naturalidade` | tabela `pessoa` (5.029.129 pessoas) | Características da pessoa envolvida |
| `estado_fisico` (ileso, lesão leve ou grave, óbito) | tabela `pessoa` | **Dado sensível**: é dado referente à saúde (art. 5º, II) |
| `tipo_envolvido` (condutor, passageiro, pedestre...) | tabela `pessoa` | Diz o papel da pessoa no acidente |
| Data e hora, BR, km, município e coordenada | tabela `ocorrencia`, ligada à pessoa | Não é pessoal sozinho, mas é o que permite achar a pessoa (quase-identificador) |
| Marca e ano de fabricação do veículo | tabela `veiculo`, ligada à pessoa | Quase-identificador |

**Não é dado pessoal:** as tabelas de consumo (`analitico_marts`), que só têm contagens por
trecho, por município e por ano, sem nenhuma linha por pessoa.

### Onde o dado pessoal fica guardado

| Lugar | O que tem | Volume do Docker |
|---|---|---|
| Arquivos da PRF (ZIP) | os arquivos originais, com as pessoas | `rawdata` (e `data/raw/` em quem baixou fora do Docker; a pasta é ignorada pelo git) |
| PostgreSQL, schema `public` | `pessoa`, `veiculo` e `ocorrencia`, em todas as versões (lotes) | `pgdata` |
| PostgreSQL, `analitico_staging.stg_pessoa` | uma view: não copia o dado, só lê a `pessoa_vigente` | `pgdata` |
| Delta (E2) | a tabela `pessoa` em Parquet, particionada por ano | `lakehouse` |
| Redpanda, tópico `blackspot.public.pessoa` (CDC da E2) | cada mudança na `pessoa`, **com retenção infinita** (`retention.ms = -1` em [`blackspot/cdc/conector.py`](../../blackspot/cdc/conector.py)) | `redpanda` |

Conferido com `git ls-files`: nenhum arquivo com dado de pessoa está versionado no repositório.

## Risco de reidentificação

**Pergunta:** quantas pessoas ficam sozinhas quando se cruza o que um jornal publicaria sobre um
acidente (o dia, o município, o sexo e a idade)? Se a combinação aponta para uma pessoa só, quem
leu a notícia descobre na base o estado físico dela e o dos outros envolvidos.

Medido em 24/11/2026, na versão vigente, nas 4.390.646 pessoas com sexo e idade informados:

| Combinação de quase-identificadores | Pessoas únicas na combinação |
|---|---|
| dia + município + sexo + idade | **93,1%** |
| mês + município + sexo + faixa de 10 anos | 17,8% |
| ano + município + sexo + faixa de 10 anos | 2,3% |
| ano + UF + sexo + faixa de 10 anos | 0,0% |

- **93,1% das pessoas são únicas** com só quatro informações. Das 120.163 mortes, 113.724
  (94,6%) são únicas. Das 395.144 pessoas com lesão grave, 372.222 (94,2%) são únicas.
- A notícia de um acidente fatal ("homem de 34 anos morre na BR-101 em Palhoça") costuma trazer
  exatamente essas quatro informações. A base da PRF, sozinha, não identifica ninguém. **Junto
  com outra fonte**, identifica quase todo mundo.
- **Generalizar resolve.** Com ano, UF, sexo e faixa de 10 anos, nenhuma pessoa fica sozinha. É
  esse o nível de detalhe que pode sair do projeto, se um dia algum dado por pessoa precisar sair.

### O cruzamento com o IBGE

A base do IBGE (E3) não tem dado pessoal, mas diz o tamanho de cada município. Isso pesa nas
tabelas de consumo: na `mart_risco_municipio_ano`, **3.936 das 36.475 linhas** são de município
com menos de 10 mil habitantes e com 1 ou 2 mortos no ano. Numa cidade pequena, "1 morto em 2019"
é uma pessoa que os vizinhos conhecem.

O risco aqui é baixo, porque a linha não diz quem, nem a idade, nem o dia, e a morte já foi
notícia local. Mesmo assim, o painel segue duas regras:

- o ranking pela taxa por 100 mil só mostra município com **10 ou mais acidentes graves no ano**;
- a lista com o número de mortos mostra só os 20 municípios com mais acidentes graves, que são
  os maiores.

## Base legal

| Tratamento | Base legal | Por quê |
|---|---|---|
| Dado pessoal comum (idade, sexo, nacionalidade, naturalidade) | **Art. 7º, IV**: realização de estudos por órgão de pesquisa | O projeto é feito na UnB, universidade pública, que é órgão de pesquisa (art. 5º, XVIII) |
| Dado sensível (estado físico) | **Art. 11, II, c**: estudos por órgão de pesquisa, garantida a anonimização sempre que possível | O estado físico é dado de saúde |
| Uso de dado que a PRF publicou | **Art. 7º, § 3º**: o dado de acesso público deve ser tratado considerando a finalidade, a boa-fé e o interesse público da publicação | A PRF publica para dar transparência à segurança viária, e o BlackSpot usa para encontrar os trechos que matam mais. A finalidade é a mesma |

**Finalidade e necessidade (art. 6º, I e III).** A pergunta de gestão é sobre trechos e
municípios, e não sobre pessoas. Por isso, nenhuma tabela de consumo tem linha por pessoa. A
`pessoa` só é carregada porque a E1 pedia a origem completa, e porque o estado físico confere os
totais de mortos e feridos graves (teste `trecho_estado_fisico_bate_com_mortos`, da E3).

## Retenção

**O dado pessoal fica até o fim da disciplina** (defesa da E4, Semana 16). Depois disso, a
finalidade de pesquisa acabou, e o dado é eliminado (art. 15, I, e art. 16).

O que pode continuar depois: o código, a documentação e as tabelas de consumo, que não têm dado
pessoal. Quem quiser reproduzir o projeto baixa de novo os arquivos públicos da PRF.

**Exceção a corrigir:** o tópico do CDC guarda a `pessoa` com retenção infinita. A recomendação
é limitar a retenção do tópico (ex.: `retention.ms` de 7 dias). O consumidor grava tudo no Delta
em cerca de 1 s, então o tópico não precisa guardar nada por muito tempo. Essa mudança é na parte
do CDC (E2) e fica registrada aqui como pendência.

## Descarte

Tudo o que tem dado pessoal está em volumes do Docker. Um comando apaga os volumes do projeto:

```bash
docker compose down -v        # apaga pgdata, rawdata, lakehouse, redpanda e orquestracao
rm -rf data/raw/*.zip         # só para quem baixou os arquivos fora do Docker
```

Depois do `down -v`, `docker volume ls` não deve listar nenhum volume do projeto. O descarte vale
para a máquina de cada pessoa da Squad que subiu o projeto.

## O que já protege

| Medida | Onde |
|---|---|
| O painel lê só as tabelas de consumo, que não têm linha por pessoa | papel `painel_leitor` ([`acesso.md`](acesso.md)) |
| Quem analisa uma UF não vê idade, sexo, nacionalidade e naturalidade, e só vê a própria UF | papel `analista_regional` ([`acesso.md`](acesso.md)) |
| Ranking por taxa só com 10 ou mais acidentes graves | `mart_risco_municipio_ano` (E3) |
| Nenhum dado pessoal no repositório | `.gitignore` em `data/raw/` |
| Banco acessível só na própria máquina | porta em `127.0.0.1` (`docker-compose.yml`) |

## Como refazer a medição

```sql
WITH p AS (
  SELECT o.ocorrido_em::date AS dia, o.uf, upper(o.municipio) AS mun,
         CASE WHEN p.sexo IN ('M', 'Masculino') THEN 'M' ELSE 'F' END AS sexo, p.idade
  FROM pessoa_vigente p JOIN ocorrencia_vigente o USING (id_lote, id)
  WHERE p.idade BETWEEN 1 AND 110 AND p.sexo IN ('Masculino', 'Feminino', 'M', 'F'))
SELECT round(100.0 * count(*) FILTER (WHERE k = 1) / count(*), 1) AS pct_unicas
FROM (SELECT count(*) OVER (PARTITION BY dia, uf, mun, sexo, idade) AS k FROM p) g;
```
