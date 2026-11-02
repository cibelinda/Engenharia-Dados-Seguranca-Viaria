# Painel da E3 (issue #45). Imagem própria, para as bibliotecas do painel não entrarem na
# imagem do resto do projeto.
FROM python:3.10-slim
WORKDIR /painel
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN useradd --create-home --uid 1000 painel
USER painel
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
