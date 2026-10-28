# Engenharia-Dados-Seguranca-Viaria
Engenharia de Dados aplicada à Segurança Viária — BD2 / FCTE-UnB

## Sobre o projeto

O **BlackSpot** constrói um pipeline de dados sobre os acidentes registrados pela Polícia
Rodoviária Federal (PRF) nas rodovias federais brasileiras, de 2007 até hoje. O nome vem de
*black spot* ("ponto negro"), termo de segurança viária para os trechos de via onde os
acidentes se concentram. O objetivo é organizar esses dados num banco **espacial**
(PostgreSQL com PostGIS) para que esses trechos possam ser identificados e analisados, pela
BR e pelo km e, desde 2017, pela coordenada de cada acidente.

Os dados abertos da PRF não chegam prontos para análise. Eles vêm de dois sistemas de
registro diferentes (BR-Brasil até 2016 e BAT a partir de 2017), mudam de formato ao longo
dos anos e são republicados pela própria PRF sem aviso. Por isso o projeto é dividido em
etapas: aquisição reproduzível dos arquivos, perfilamento da qualidade, modelagem e carga
no banco.

**Pergunta de gestão:** quais trechos de 10 km das rodovias federais concentraram mais
acidentes com mortos ou feridos graves entre 2007 e 2025, e esses trechos se mantêm de um ano
para o outro?

**Dados:** o dataset completo da PRF, os 50 arquivos de 2007 a 2026 (BR-Brasil até 2016, BAT
a partir de 2017), com ocorrência, pessoa e, no BAT, todas as causas e tipos: 2,2 milhões de
acidentes, 4 milhões de veículos e 5 milhões de pessoas. Justificativa em
[`docs/pergunta-e-recorte.md`](docs/pergunta-e-recorte.md) e nos ADRs
[0002 (PostGIS)](docs/adr/0002-banco-espacial-postgis.md) e
[0003 (dataset completo)](docs/adr/0003-dataset-completo-br-brasil-e-bat.md).


## Aquisição dos dados (Etapa 1)

Fonte: dados abertos de acidentes da PRF, 2007–2026, 50 arquivos. Os achados do
reconhecimento estão em [`docs/fontes/`](docs/fontes/README.md), e o manifesto com os
arquivos, IDs do Google Drive e SHA-256 de referência é o [`sources.yaml`](sources.yaml).

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m blackspot.download            # baixa para data/raw/ (~370 MB) e confere SHA-256
```

Filtros úteis: `--system bat`, `--dataset pessoa`, `--year 2024`, `--key bat_2024_pessoa`.
`--verify-only` só confere os arquivos já baixados, e `--force` rebaixa.

**Checksums e republicação.** A PRF regrava arquivos no mesmo ID e com o mesmo nome. Quando o
SHA-256 não bate com a referência, o downloader **mantém o arquivo, emite um aviso** e registra
o caso em `data/raw/_download_report.json`, sem interromper o pipeline. Para adotar a nova
versão como referência:

```bash
python -m blackspot.download --accept-new-hash bat_2024_pessoa   # uma entrada
python -m blackspot.download --accept-all-new-hashes             # todas as divergentes
```

Isso reescreve o bloco `reference` da entrada no `sources.yaml`; faça commit da mudança.
`--strict` faz divergências saírem com código 2 (para CI).

Testes do downloader (sem rede): `python -m unittest discover tests`. Sem banco acessível, os
testes de dados são pulados; para rodá-los, veja "Testes de dados" abaixo.

## Entrega 3: camada analítica transformada, testada e orquestrada

Em andamento. Divisão, contrato entre as partes e checklist em
[`docs/e3/README.md`](docs/e3/README.md). O projeto dbt fica em [`dbt/`](dbt/):
`docker compose run --rm dbt build`.

## Entrega 2: ingestão em lote e captura de mudanças

Em andamento. Divisão, contrato entre as partes e checklist em
[`docs/e2/README.md`](docs/e2/README.md): [ingestão em lote](docs/e2/lote.md) e
[captura de mudanças](docs/e2/cdc.md).

## Como subir o projeto

Pré-requisito: Docker com Compose v2. Não é preciso ter Python nem PostgreSQL instalados.

```bash
git clone git@github.com:cibelinda/Engenharia-Dados-Seguranca-Viaria.git
cd Engenharia-Dados-Seguranca-Viaria
docker compose up --build
```

O `--build` reconstrói a imagem do código Python antes de subir, para nunca rodar uma versão
antiga do download ou da carga. O `docker-compose.yml` também força essa reconstrução
(`pull_policy: build`), então um `docker compose up` sem a flag tem o mesmo efeito.

O comando sobe quatro serviços, definidos no [`docker-compose.yml`](docker-compose.yml):

| Serviço | O que faz | Espera |
|---|---|---|
| `db` | PostgreSQL 18.6 com PostGIS 3.6 (imagem `postgis/postgis:18-3.6`) | — |
| `migrate` | Aplica as migrações de [`db/migrations/`](db/migrations/) em ordem, com Flyway | `db` saudável |
| `download` | Baixa o dataset completo (50 arquivos, ~370 MB) e compara os SHA-256 com o `sources.yaml` (divergência é aviso, ver abaixo) | — |
| `load` | Carrega os 20 anos no banco | `migrate` e `download` terminarem sem erro |

Termina quando o log mostra `load-1 exited with code 0`. O banco continua no ar; `Ctrl+C` o
desliga. Para rodar em segundo plano: `docker compose up --build -d` e `docker compose wait load`.

Tempos medidos em 2026-10-12, com as imagens do Docker já baixadas (o download depende da
conexão):

| Etapa | Tempo |
|---|---|
| Download dos 50 arquivos (~370 MB) | ~5 min |
| Carga dos 20 anos | ~8 min (467 s) |
| Subida do zero (`docker compose down -v` e `up`) | ~13 min |
| Subidas seguintes (nada é baixado nem carregado de novo) | ~10 s |

O banco carregado ocupa 2,7 GB.

**Conferir.** Com o banco no ar:

```bash
docker compose exec db psql -U blackspot -d blackspot -c "
  SELECT l.ano, l.sistema, a.dataset, a.linhas_lidas, a.linhas_rejeitadas
  FROM lote_vigente l JOIN lote_arquivo a USING (id_lote) ORDER BY 1, 3;"
```

**Consulta espacial.** As ocorrências do BAT têm o ponto em `geom` (PostGIS, SIRGAS 2000). Por
exemplo, os acidentes graves num raio de 2 km de um ponto da BR-040 em Brasília:

```bash
docker compose exec db psql -U blackspot -d blackspot -c "
  SELECT ano, count(*) FROM ocorrencia_vigente
  WHERE (mortos > 0 OR feridos_graves > 0)
    AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(-47.95, -15.87), 4674)::geography, 2000)
  GROUP BY ano ORDER BY ano;"
```

O esquema (issue #3) e o raciocínio da modelagem, incluindo a decisão de guardar histórico
(insert-only versionado por lote), estão em [`docs/modelagem-origem.md`](docs/modelagem-origem.md).

**Carga** ([`blackspot/load.py`](blackspot/load.py), issue #4). Carrega um ano por vez; cada ano
vira um lote com os seus arquivos: ocorrência e pessoa e, no BAT, também o de todas as causas e
tipos, que vira `ocorrencia_causa` e `ocorrencia_tipo`. Um ano só é carregado de novo quando
o SHA-256 de algum arquivo dele muda (republicação pela PRF), então rodar de novo não duplica nada.
Se um ano falha, nada dele fica gravado e a tentativa fica registrada como `falhou`.

Os dois sistemas da PRF publicam em formatos diferentes, e a carga lê os dois sem passo
manual: o separador (`,` no arquivo de pessoa de 2007–2015, `;` no resto) sai do cabeçalho, a
data é lida nos três formatos usados (`dd/mm/aaaa`, `aaaa-mm-dd`, `dd/mm/aa`) e o decimal com
ponto ou com vírgula.

Registros que não cabem no esquema vão para `linha_rejeitada`, com o motivo, e em cada arquivo
lidas = carregadas + rejeitadas. Conversões feitas na carga:

| Na fonte | No banco |
|---|---|
| `km`, `latitude`, `longitude` com vírgula ou ponto decimal | número |
| Latitude ou longitude fora do limite válido (33 ocorrências de 2017) | as duas `NULL`; a ocorrência entra |
| Sem colunas de coordenada (BR-Brasil, 2007–2016) | `latitude`, `longitude` e `geom` `NULL` |
| `(null)`, vazio, `NA` ou `N/A` em qualquer campo descritivo | `NULL` |
| `uf`, `br` e `km` `(null)` (12 ocorrências do BR-Brasil) ou `km` negativo (19) | `NULL`; a ocorrência entra, mas fica fora do ranking de trechos |
| Textos completados com espaços (BR-Brasil, ex.: `'Ileso       '`) | sem os espaços |
| `idade` 0, negativa ou acima de 110 | `NULL` (desconhecida) |
| `ano_fabricacao_veiculo` 0 ou depois do ano do arquivo + 1 (ex.: 9999) | `NULL` (desconhecido) |
| `uso_solo` Sim/Não (BAT) ou Urbano/Rural (BR-Brasil) | booleano `uso_solo_urbano` |
| `tracado_via` com `;` | lista |
| `pesid = 0` | só veículo, sem pessoa |
| `id_veiculo = 0` (BAT) ou `(null)`/`NA` (BR-Brasil) | pessoa sem veículo |
| ID em notação científica; `pesid = 0` e `id_veiculo = 0` juntos; pessoa sem ocorrência; ID de ocorrência repetido no arquivo (BR-Brasil) e as pessoas e veículos repetidos que vêm dele; ano de fabricação entre 1851 e 1899 | `linha_rejeitada` |

Os vocabulários dos dois sistemas são guardados como a PRF publica (`Óbito` × `Morto`,
`Lesões Graves` × `Ferido Grave`, `Céu Claro` × `Ceu Claro`); harmonizar é transformação (E3).

**Migrações.** Ficam em [`db/migrations/`](db/migrations/), no padrão do Flyway
(`V0001__nome.sql`, `V0002__...`), uma por conceito, e rodam em ordem num banco vazio. Uma
migração já aplicada não deve ser editada, porque o Flyway guarda o checksum de cada uma:
para mudar o esquema, crie a próxima. Durante o desenvolvimento, `docker compose down -v`
recria o banco do zero.

**Arquivo republicado pela PRF.** A PRF regrava arquivos no mesmo ID e com o mesmo nome. Se o
SHA-256 baixado não bater com o `sources.yaml`, o `download` **só avisa** (no log e em
`_download_report.json`) e a esteira segue, carregando a versão nova. É proposital: uma
republicação da PRF não pode impedir o projeto de subir, e a carga registra o SHA-256 de cada
arquivo carregado. Para adotar a versão nova como referência, rode `--accept-new-hash` **fora
do container**, com Python local (seção "Aquisição dos dados"), e faça commit do `sources.yaml`:
dentro do container a alteração se perde junto com ele.

**Testes de dados.** Com o Docker, sem precisar de Python local:

```bash
docker compose run --rm tests
```

Sobe o banco, as migrações e a carga, se ainda não estiverem no ar, e roda os 99 testes de
[`tests/`](tests/) (~80 s): os do downloader e os de dados (issue #8).

| Arquivo | O que confere |
|---|---|
| [`test_esquema.py`](tests/test_esquema.py) | Migrações aplicadas; PostGIS instalado, `geom` em SIRGAS 2000 com índice GiST e gerada das coordenadas; tabelas, PKs, FKs e carimbo de tempo no `COMMENT`; cada restrição recusa o dado inválido e aceita o vocabulário dos dois sistemas |
| [`test_versao_vigente.py`](tests/test_versao_vigente.py) | As views `*_vigente` mostram só o lote vigente; lotes em carga ou que falharam não entram |
| [`test_volume.py`](tests/test_volume.py) | Todo ano de 2007 a 2026 tem lote e linhas, e o BAT tem causas e tipos; em cada arquivo, lidas = carregadas + rejeitadas; as lidas batem com a contagem independente de [`bench/perfil_recorte.py`](bench/perfil_recorte.py); só há os motivos de rejeição conhecidos |
| [`test_distribuicao.py`](tests/test_distribuicao.py) | Variação anual e meses sem dado (2007–2025); nulos abaixo do limiar, por sistema; coordenada em todo o BAT e em nada do BR-Brasil, dentro do Brasil; mortos e feridos graves batem com as pessoas; `br = 0` continua no banco |
| [`test_dado_faltante.py`](tests/test_dado_faltante.py) | O que a carga faz com cada valor vazio ou inválido (tabela no próprio arquivo), nas funções da carga e no banco |
| [`test_reprocessamento.py`](tests/test_reprocessamento.py) | A segunda carga não grava nada; um arquivo com SHA-256 novo cria um lote novo e preserva o antigo |

Os testes não deixam nada gravado: os de esquema e o de republicação rodam numa transação
desfeita no fim, e os outros só leem. Os limiares de distribuição vêm do que foi medido na
carga e estão explicados no próprio teste. Os valores esperados de volume só são cobrados nos
anos cujo arquivo carregado tem o mesmo SHA-256 do perfilado: se a PRF republicar um ano, os
números dele mudam de propósito.

**Configuração.** Sem `.env`, o banco sobe com usuário, banco e senha `blackspot`, só em
`127.0.0.1:5432`. Para trocar algum valor, copie `.env.example` para `.env` e ajuste.

**Problemas comuns.**
- *Senha recusada* depois de trocar a senha no `.env`: o volume foi criado com a anterior.
  Recrie com `docker compose down -v`.
- *Começar do zero*: `docker compose down -v` apaga o banco e os arquivos baixados.
