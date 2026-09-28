# Commits

### criei o repositório
**autor:** Cibelly

Criei o repositório no GitHub e o `.gitignore` padrão de Python.

### aquisição dos dados
**autor:** Cibelly

- Fiz o reconhecimento dos dados abertos de acidentes da PRF (2007–2026) e registrei os achados em `docs/fontes/README.md`: os dois sistemas de registro (BR-Brasil e BAT), as mudanças de formato ao longo dos anos, os problemas nos identificadores, as divergências com o dicionário oficial e a dúvida sobre a licença. Os arquivos brutos da investigação ficaram em `docs/fontes/reconhecimento-2026-09-27/`.
- Criei o `sources.yaml`, com os 50 arquivos da PRF, os IDs do Google Drive conferidos um a um e o SHA-256 de referência de cada arquivo, via IA.
- Escrevi o downloader `blackspot/download.py`, que baixa os arquivos para `data/raw/`, confere os hashes e avisa quando a PRF republica um arquivo, sem interromper o processo.
- Subi o PostgreSQL com `docker-compose.yml` e `.env.example`, ainda sem esquema nem carga.
- Documentei no README como baixar os dados e subir o banco.

### correção do commit anterior
**autor:** Cibelly

Corrigi problemas encontrados numa revisão do projeto e criei os testes:
- O downloader não trava mais quando a conexão cai no meio de um arquivo: o arquivo é marcado
  como erro e os outros continuam.
- Ao aceitar um novo hash de um arquivo que já estava baixado, a data antiga do Drive deixa de ficar associada ao hash novo.
- O `BLACKSPOT_RAW_DIR` passou a ser relativo à raiz do repositório.
- O PostgreSQL agora aceita conexões só da própria máquina (`127.0.0.1`).
- Criei `tests/test_download.py`, com 5 testes que rodam sem internet, e expliquei no README como executá-los.

### alteração do readme e criação de commits.md
**autor:** Cibelly

- Coloquei a introdução do projeto no readme
- Criei esse arquivo para termos controle dos commits no repositório.

### pergunta de gestão e recorte dos dados
**autor:** Ana Luiza Komatsu

- Defini a pergunta de gestão (issue #1) e o recorte dos dados (issue #2) em `docs/pergunta-e-recorte.md`, com as justificativas e as alternativas descartadas, e coloquei um resumo no README.
- O recorte (BAT 2017–2025, conjuntos de ocorrência e pessoa) foi escolhido com o uso de IA, a partir dos números do reconhecimento em `docs/fontes/`.
- Atribuí as issues da E1 entre mim e a Cibelly; as da Maria ficam para quando ela aceitar o convite do repositório.

### esteira do docker compose (issue #5)
**autor:** Ana Luiza Komatsu

- O `docker compose up` agora sobe tudo sozinho: `db` (PostgreSQL), `migrate` (Flyway, aplica `db/migrations/`), `download` (baixa o recorte BAT 2017–2025, ocorrência e pessoa) e `load` (carga no banco), nessa ordem.
- Criei o `Dockerfile` do código Python, para ninguém precisar de Python instalado, e o `.dockerignore`.
- A migração (`V1__placeholder.sql`) e a carga (`blackspot/load.py`) são provisórias: a carga só conta os registros de cada arquivo. Elas serão trocadas pelo esquema real (#3) e pela carga real (#4).
- Coloquei uma senha padrão de desenvolvimento no compose, para não precisar criar o `.env`.
- Testei do zero: cerca de 1 min na primeira vez (baixando as imagens do Docker), cerca de 26 s num clone novo com as imagens já baixadas e cerca de 12 s nas subidas seguintes. 18 arquivos com SHA-256 conferido, 632.713 ocorrências e 1.654.197 registros de pessoa. Rodar de novo não duplica nada.
- Atualizei o README com a seção "Como subir o projeto".
- Esta issue foi feita com o uso de IA (configuração do Docker, scripts e README).
