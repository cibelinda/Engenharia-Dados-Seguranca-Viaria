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

### ajustes da revisão do documento de pergunta e recorte
**autor:** Ana Luiza Komatsu

- No exemplo "Só o DF", tirei o número de 2016, que é do BR-Brasil e está fora do recorte, e deixei só o de 2025.
- Acrescentei o critério de persistência (top-N, percentil ou número de anos) em "O que ainda precisa ser definido".
- Sugestões da revisão da Maria no PR #10. A anotação sobre o `km` com vírgula decimal ficou como comentário nas issues #3 e #4.
