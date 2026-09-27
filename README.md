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

## Banco de dados

```bash
docker compose up -d    # PostgreSQL 18.6, ainda sem esquema nem carga
```

Sem `.env`, o banco sobe com usuário, banco e senha `blackspot`, só em `127.0.0.1:5432`.
Para trocar algum valor, copie `.env.example` para `.env` e ajuste. Se o volume já tiver
sido criado com outra senha, recrie-o com `docker compose down -v`.
