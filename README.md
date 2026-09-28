# Engenharia-Dados-Seguranca-Viaria
Engenharia de Dados aplicada à Segurança Viária — BD2 / FCTE-UnB

## Sobre o projeto

O **BlackSpot** constrói um pipeline de dados sobre os acidentes registrados pela Polícia
Rodoviária Federal (PRF) nas rodovias federais brasileiras, de 2007 até hoje. O nome vem de
*black spot* ("ponto negro"), termo de segurança viária para os trechos de via onde os
acidentes se concentram. O objetivo é organizar esses dados num banco PostgreSQL para que
esses trechos possam ser identificados e analisados.

Os dados abertos da PRF não chegam prontos para análise. Eles vêm de dois sistemas de
registro diferentes (BR-Brasil até 2016 e BAT a partir de 2017), mudam de formato ao longo
dos anos e são republicados pela própria PRF sem aviso. Por isso o projeto é dividido em
etapas: aquisição reproduzível dos arquivos, perfilamento da qualidade, modelagem e carga
no banco.

**Pergunta de gestão:** quais trechos de 10 km das rodovias federais concentraram mais
acidentes com mortos ou feridos graves entre 2017 e 2025, e esses trechos se mantêm de um ano
para o outro?

**Recorte:** sistema BAT, 2017–2025, conjuntos de ocorrência e pessoa (cerca de 630 mil
ocorrências e 1,65 milhão de registros de pessoa). Justificativa e alternativas descartadas em
[`docs/pergunta-e-recorte.md`](docs/pergunta-e-recorte.md).


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

Testes (sem rede): `python -m unittest discover tests`.

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
| `db` | PostgreSQL 18.6 | — |
| `migrate` | Aplica as migrações de [`db/migrations/`](db/migrations/) em ordem, com Flyway | `db` saudável |
| `download` | Baixa o recorte (BAT 2017–2025, ocorrência e pessoa: 18 arquivos, ~108 MB) e compara os SHA-256 com o `sources.yaml` (divergência é aviso, ver abaixo) | — |
| `load` | Carrega os arquivos no banco | `migrate` e `download` terminarem sem erro |

Termina quando o log mostra `load-1 exited with code 0`. O banco continua no ar; `Ctrl+C` o
desliga. Para rodar em segundo plano: `docker compose up --build -d` e `docker compose wait load`.

Tempos medidos em 2026-09-27 (o download depende da conexão):

| Situação | Tempo |
|---|---|
| Primeira vez na máquina, baixando as imagens do Docker (PostgreSQL, Flyway, Python) e os dados | ~1 min |
| Clone novo, com as imagens do Docker já baixadas, baixando os dados | ~26 s |
| Subidas seguintes (não baixa de novo os arquivos já íntegros) | ~12 s |

**Conferir.** Com o banco no ar:

```bash
docker compose exec db psql -U blackspot -d blackspot -c '\dt' -c '\dv'
docker compose exec db psql -U blackspot -d blackspot -c 'SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;'
```

> O esquema (issue #3) já é o real: ocorrência, veículo, pessoa, domínios de causa e tipo,
> controle de lotes e linhas rejeitadas. O raciocínio e a evidência da modelagem, incluindo a
> decisão de guardar histórico (insert-only versionado por lote), estão em
> [`docs/modelagem-origem.md`](docs/modelagem-origem.md).
> A carga ainda é **provisória**: confere o esquema e conta os registros de cada arquivo
> (632.713 ocorrências e 1.654.197 registros de pessoa), sem gravar. A carga real é a issue #4.

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

**Configuração.** Sem `.env`, o banco sobe com usuário, banco e senha `blackspot`, só em
`127.0.0.1:5432`. Para trocar algum valor, copie `.env.example` para `.env` e ajuste.

**Problemas comuns.**
- *Senha recusada* depois de trocar a senha no `.env`: o volume foi criado com a anterior.
  Recrie com `docker compose down -v`.
- *Começar do zero*: `docker compose down -v` apaga o banco e os arquivos baixados.
