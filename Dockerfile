# Imagem do código Python do BlackSpot, usada pelos serviços `download` e `load`
# do docker-compose.yml. Quem roda o projeto não precisa de Python instalado.
FROM python:3.10-slim

WORKDIR /app

# Dependências primeiro: esta camada só é refeita quando o requirements.txt muda,
# e não a cada alteração no código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sources.yaml .
COPY blackspot/ blackspot/

# Não rodar como root dentro do container.
RUN useradd --create-home --uid 1000 blackspot \
    && mkdir -p data/raw \
    && chown -R blackspot:blackspot /app
USER blackspot
