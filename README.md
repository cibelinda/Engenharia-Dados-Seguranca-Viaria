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
docker compose up
```

O comando sobe quatro serviços, definidos no [`docker-compose.yml`](docker-compose.yml):

| Serviço | O que faz | Espera |
|---|---|---|
| `db` | PostgreSQL 18.6 | — |
| `migrate` | Aplica as migrações de [`db/migrations/`](db/migrations/) em ordem, com Flyway | `db` saudável |
| `download` | Baixa o recorte (BAT 2017–2025, ocorrência e pessoa: 18 arquivos, ~108 MB) e confere os SHA-256 | — |
| `load` | Carrega os arquivos no banco | `migrate` e `download` terminarem sem erro |

Termina quando o log mostra `load-1 exited with code 0`. O banco continua no ar; `Ctrl+C` o
desliga. Para rodar em segundo plano: `docker compose up -d` e `docker compose wait load`.

Tempo medido em 2026-09-27: cerca de 1 min do zero (incluindo o download) e cerca de 12 s nas
subidas seguintes, que não baixam de novo os arquivos já íntegros. O download depende da conexão.

**Conferir.** Com o banco no ar:

```bash
docker compose exec db psql -U blackspot -d blackspot -c "SELECT * FROM placeholder_contagem ORDER BY arquivo;"
```

> A carga atual é **provisória**: conta os registros de cada arquivo (632.713 ocorrências e
> 1.654.197 registros de pessoa). A carga no esquema real é a issue #4.

**Configuração.** Sem `.env`, o banco sobe com usuário, banco e senha `blackspot`, só em
`127.0.0.1:5432`. Para trocar algum valor, copie `.env.example` para `.env` e ajuste.

**Problemas comuns.**
- *Senha recusada* depois de trocar a senha no `.env`: o volume foi criado com a anterior.
  Recrie com `docker compose down -v`.
- *Começar do zero*: `docker compose down -v` apaga o banco e os arquivos baixados.
