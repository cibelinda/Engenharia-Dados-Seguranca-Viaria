# Controle de acesso

Issue #52. Migração [`V0020__acesso.sql`](../../db/migrations/V0020__acesso.sql). A análise de
LGPD que motiva estes recortes está em [`lgpd.md`](lgpd.md).

Até a E3, todos os serviços usavam o mesmo usuário, com acesso total ao banco. A E4 aplica
**privilégio mínimo**: cada papel acessa só o que precisa.

## Os papéis

| Papel | Quem usa | Pode ler | Não pode |
|---|---|---|---|
| `blackspot` (principal) | migrações, carga, dbt, orquestração | tudo | — |
| `painel_leitor` | o painel | só as tabelas de `analitico_marts` | a origem, o staging, escrever |
| `analista_regional` (grupo) | quem analisa uma UF | `ocorrencia` da **própria UF**; de `pessoa`, só as colunas sem dado pessoal | idade, sexo, nacionalidade e naturalidade; outras UFs; escrever |
| `analista_df`, `analista_sc` | dois usuários de exemplo do grupo | DF e SC | — |

As senhas da migração são só para desenvolvimento, como a do usuário principal: o banco escuta
apenas em `127.0.0.1`. A do painel pode ser trocada com `PAINEL_DB_PASSWORD`.

## Recorte de linha: cada analista vê a própria UF

Política de segurança por linha (*row level security*) na `ocorrencia`: a linha só aparece se a
UF for a do usuário. A UF de cada analista fica na tabela `acesso.analista_uf`, que os analistas
não conseguem ler. A política consulta essa tabela por uma função que roda com a permissão de
quem a criou. A `pessoa` segue a mesma regra: só aparecem as pessoas dos acidentes que o analista
vê.

O mesmo `SELECT`, com três usuários (24/11/2026):

```sql
SELECT count(DISTINCT uf) AS ufs, string_agg(DISTINCT uf, ',') AS quais, count(*) FROM ocorrencia;
```

| Usuário | `ufs` | `quais` | `count` |
|---|---|---|---|
| `blackspot` | 27 | todas | 2.256.084 |
| `analista_df` | 1 | DF | 22.647 |
| `analista_sc` | 1 | SC | 248.563 |

Os 22.647 e os 248.563 batem com `count(*) WHERE uf = 'DF'` e `WHERE uf = 'SC'` rodados pelo
usuário principal.

## Recorte de coluna: a pessoa sem dado pessoal

O grupo `analista_regional` recebe `SELECT` só em `id_lote`, `pesid`, `id`, `id_veiculo`,
`tipo_envolvido` e `estado_fisico` da `pessoa`.

```
analista_df=> SELECT estado_fisico, count(*) FROM pessoa GROUP BY 1 ORDER BY 2 DESC LIMIT 4;
 estado_fisico | count
---------------+-------
 Ileso         | 29994
 Lesões Leves  |  8855
 Ferido Leve   |  8492
 Ferido Grave  |  2278

analista_df=> SELECT idade FROM pessoa LIMIT 1;
ERROR:  permission denied for table pessoa

analista_df=> SELECT * FROM pessoa LIMIT 1;
ERROR:  permission denied for table pessoa
```

O `SELECT *` também falha, porque pede colunas que o papel não pode ler.

## Sem escrita e sem o mapeamento

```
analista_df=> DELETE FROM ocorrencia WHERE false;
ERROR:  permission denied for table ocorrencia

analista_df=> SELECT * FROM acesso.analista_uf;
ERROR:  permission denied for table analista_uf
```

## O painel só lê as tabelas de consumo

O serviço `painel` ([`compose/painel.yml`](../../compose/painel.yml)) conecta como
`painel_leitor`.

```
painel_leitor=> SELECT count(*) FROM analitico_marts.mart_risco_trecho_ano;
 count
--------
 106192

painel_leitor=> SELECT count(*) FROM ocorrencia;
ERROR:  permission denied for table ocorrencia

painel_leitor=> SELECT count(*) FROM pessoa;
ERROR:  permission denied for table pessoa

painel_leitor=> SELECT count(*) FROM analitico_staging.stg_pessoa;
ERROR:  permission denied for schema analitico_staging
```

**O acesso continua valendo depois do dbt.** O dbt apaga e recria as tabelas a cada `build`, e
um `GRANT` feito na tabela se perderia. Por isso, a migração dá a permissão **por padrão no
schema** (`ALTER DEFAULT PRIVILEGES`): toda tabela que o usuário principal cria em
`analitico_marts` já nasce legível pelo painel. Testado com dois `dbt build` seguidos (um pelo
terminal e outro pela esteira do Dagster): o painel continuou lendo, e respondeu HTTP 200.

**O que fica de fora do privilégio mínimo:** o painel lê todas as tabelas de `analitico_marts`,
e não só as três que usa. Nenhuma delas tem linha por pessoa, e dar a permissão tabela por tabela
exigiria mexer na configuração dos modelos de cada parte.

## Como testar

Com o projeto no ar (`docker compose up --build -d` e `docker compose run --rm dbt build`):

```bash
docker compose exec db psql -U analista_df -d blackspot -c "SELECT count(DISTINCT uf), count(*) FROM ocorrencia"
docker compose exec db psql -U analista_df -d blackspot -c "SELECT idade FROM pessoa LIMIT 1"
docker compose exec db psql -U painel_leitor -d blackspot -c "SELECT count(*) FROM ocorrencia"
```

Dentro do container, a conexão local não pede senha.
