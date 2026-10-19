---
title: Decisões
nav_order: 5
permalink: /decisoes/
---

# Decisões de arquitetura

Cada decisão foi tomada comparando com pelo menos uma alternativa, incluindo a **opção nula** (a
mais simples possível), e com o custo medido nos dados reais. Os registros completos (ADRs) estão
no [repositório](https://github.com/cibelinda/Engenharia-Dados-Seguranca-Viaria/tree/main/docs/adr).

<div class="cartoes" markdown="0">
  <div class="cartao">
    <span class="cartao-titulo">Histórico insert-only, versionado por lote</span>
    <span class="cartao-texto">A PRF regrava arquivos sem versão. Sobrescrever perderia o que mudou;
    guardar cada carga como um lote preserva tudo. Custa 2,7 GB e 2,8 s na consulta de persistência,
    contra 2,2 GB e 1,7 s da opção nula, muito abaixo da latência tolerada, que é de meses.</span>
    <span class="cartao-numero">Escolhido: modelo normalizado, insert-only</span>
  </div>
  <div class="cartao">
    <span class="cartao-titulo">Banco espacial: PostgreSQL com PostGIS</span>
    <span class="cartao-texto">Um ponto negro é, por definição, um lugar. Com tipo geométrico e índice
    espacial, "acidentes graves a menos de 2 km" leva 46 ms, contra 608 ms com a distância calculada
    à mão, e o agrupamento de pontos revelou as coordenadas padrão repetidas.</span>
    <span class="cartao-numero">Escolhido: PostGIS 3.6, SIRGAS 2000</span>
  </div>
  <div class="cartao">
    <span class="cartao-titulo">Dataset completo, dois sistemas</span>
    <span class="cartao-texto">Formato diferente não justifica descartar dado: tratar formatos
    heterogêneos é o trabalho da engenharia de dados. Com o BR-Brasil, a série histórica passa de 9
    para 19 anos completos, e a pergunta de persistência fica muito mais forte.</span>
    <span class="cartao-numero">Escolhido: 2007–2026 no mesmo esquema</span>
  </div>
  <div class="cartao">
    <span class="cartao-titulo">Lote incremental em Delta, CDC como trilha</span>
    <span class="cartao-texto">A fonte muda uma vez por mês. Reescrever só a partição do ano
    republicado custa 3,3 s e 6,3 MB, contra 85 s e 132 MB da recarga completa. O CDC tem latência
    de segundos, mas três serviços a mais; ele fica para as mudanças que não criam lote novo.</span>
    <span class="cartao-numero">Escolhido: lote por ano + CDC, Delta com zstd</span>
  </div>
</div>

## A escolha da ingestão em números

| | Recarga no banco | Recarga completa em Delta | **Lote incremental** | CDC |
|---|---|---|---|---|
| Republicar um ano | 11 s | 85 s | **3,3 s** | 627 mil eventos |
| Histórico por republicação | nenhum | 132 MB | **6,3 MB** | — |
| Formato aberto | não | sim | **sim** | sim |
| Serviços a operar | 0 | 1 | **1** | +3, com estado |
| Latência até a camada | agendamento | agendamento + 85 s | **3–7 s após a carga** | ~1 s |

## Delta ou Iceberg

| | Delta | Iceberg |
|---|---|---|
| Tamanho (ocorrência, zstd) | 54,5 MB | 52,4 MB |
| Precisa de catálogo | **não: a pasta é a tabela** | sim |
| Acrescentar coluna | sim | sim |
| Renomear, remover ou alargar coluna | não | **sim** |

O Iceberg é melhor na evolução de esquema. O Delta venceu porque dispensa um serviço de catálogo, e
as mudanças de esquema que chegam à camada analítica, até aqui, só acrescentaram colunas, o que o
Delta faz.
