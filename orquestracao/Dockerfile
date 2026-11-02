# Orquestrador da E3 (issue #44): Dagster com o código do projeto e o dbt. Imagem própria,
# para o Dagster não entrar na imagem do resto do projeto. As etapas rodam aqui dentro, com
# as mesmas bibliotecas da imagem principal (requirements.txt da raiz).
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt
COPY orquestracao/requirements.txt requirements-orquestracao.txt
RUN pip install --no-cache-dir -r requirements.txt -r requirements-orquestracao.txt

COPY sources.yaml .
COPY blackspot/ blackspot/
COPY orquestracao/ orquestracao/

# DAGSTER_HOME só tem a configuração (vem da imagem); o histórico das execuções fica no
# volume montado em /var/lib/dagster (ver orquestracao/dagster.yaml).
ENV DAGSTER_HOME=/app/orquestracao
RUN useradd --create-home --uid 1000 blackspot \
    && mkdir -p data/raw lake /var/lib/dagster \
    && chown -R blackspot:blackspot /app /var/lib/dagster
USER blackspot

EXPOSE 3000
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-m", "orquestracao.definitions"]
