# Engenharia-Dados-Seguranca-Viaria
Engenharia de Dados aplicada à Segurança Viária — BD2 / FCTE-UnB

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

## Banco de dados

```bash
cp .env.example .env    # ajuste POSTGRES_PASSWORD
docker compose up -d    # PostgreSQL 18.6, ainda sem esquema nem carga
```
