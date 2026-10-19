---
title: Início
nav_order: 1
permalink: /
---

<div class="hero" markdown="0">
  <p class="hero-titulo">BlackSpot</p>
  <p class="hero-texto">Um pipeline de dados sobre os acidentes nas rodovias federais brasileiras: dos
  arquivos abertos da Polícia Rodoviária Federal a um banco espacial com histórico de versões e a
  uma camada analítica em formato aberto, alimentada em lote e por captura de mudanças.</p>
  <p class="hero-pergunta"><strong>Pergunta:</strong> quais trechos de 10 km das rodovias federais
  concentraram mais acidentes com mortos ou feridos graves entre 2007 e 2025, e esses trechos se
  mantêm de um ano para o outro?</p>
</div>

*Black spot* ("ponto negro") é o termo de segurança viária para os trechos onde os acidentes se
concentram. Encontrá-los separa o problema da via do acidente isolado e indica onde intervir
primeiro.

<div class="numeros" markdown="0">
  <div class="numero"><span class="valor">20 anos</span><span class="rotulo">de dados, 2007 a 2026, em 50 arquivos da PRF</span></div>
  <div class="numero"><span class="valor">2,2 mi</span><span class="rotulo">acidentes, com 4,0 mi de veículos e 5,0 mi de pessoas</span></div>
  <div class="numero"><span class="valor">13,2 mi</span><span class="rotulo">linhas no PostgreSQL com PostGIS (2,7 GB)</span></div>
  <div class="numero"><span class="valor">138 MB</span><span class="rotulo">a mesma informação em Delta com Parquet e zstd</span></div>
  <div class="numero"><span class="valor">~1 s</span><span class="rotulo">de uma mudança no banco até a camada analítica</span></div>
  <div class="numero"><span class="valor">1 comando</span><span class="rotulo">sobe tudo do zero: <code>docker compose up</code></span></div>
</div>

## O pipeline em uma imagem

<ol class="fluxo" markdown="0">
  <li><strong>Aquisição</strong>50 arquivos da PRF, com o SHA-256 conferido</li>
  <li><strong>Carga</strong>dois formatos tratados, um lote por ano</li>
  <li><strong>Banco espacial</strong>PostgreSQL + PostGIS, histórico versionado</li>
  <li><strong>Camada analítica</strong>Delta em Parquet, por lote e por CDC</li>
  <li><strong>Consulta</strong>DuckDB e SQL sobre formato aberto</li>
</ol>

Os dados da PRF não chegam prontos: vêm de **dois sistemas de registro** com formatos diferentes e
são **republicados sem aviso**, inclusive anos já fechados. Por isso cada etapa confere, versiona e
guarda o histórico em vez de sobrescrever.

## Explore

<div class="cartoes" markdown="0">
  <a class="cartao" href="{{ '/dados/' | relative_url }}">
    <span class="cartao-titulo">Os dados</span>
    <span class="cartao-texto">De onde vêm, o que mudou em 20 anos e por que eles são difíceis.</span>
  </a>
  <a class="cartao" href="{{ '/pipeline/' | relative_url }}">
    <span class="cartao-titulo">Pipeline e modelo</span>
    <span class="cartao-texto">Os serviços, o modelo relacional e o histórico versionado por lote.</span>
  </a>
  <a class="cartao" href="{{ '/camada-analitica/' | relative_url }}">
    <span class="cartao-titulo">Camada analítica</span>
    <span class="cartao-texto">Ingestão em lote e captura de mudanças para tabelas Delta.</span>
  </a>
  <a class="cartao" href="{{ '/decisoes/' | relative_url }}">
    <span class="cartao-titulo">Decisões</span>
    <span class="cartao-texto">As escolhas de arquitetura, cada uma com a alternativa medida.</span>
  </a>
</div>

## Tecnologias

<ul class="etiquetas" markdown="0">
  <li>PostgreSQL 18</li>
  <li>PostGIS 3.6</li>
  <li>Flyway</li>
  <li>Python</li>
  <li>Debezium</li>
  <li>Redpanda (Kafka)</li>
  <li>Delta Lake</li>
  <li>Parquet + zstd</li>
  <li>DuckDB</li>
  <li>Docker Compose</li>
</ul>

## Como rodar

Pré-requisito: Docker com Compose v2.

```bash
git clone https://github.com/cibelinda/Engenharia-Dados-Seguranca-Viaria.git
cd Engenharia-Dados-Seguranca-Viaria
docker compose up --build        # baixa, carrega e alimenta a camada analítica
docker compose run --rm tests    # 119 testes automatizados
```

Do zero, a subida leva cerca de 13 minutos: 5 de download e 8 de carga. Rodar de novo não duplica
nada.
