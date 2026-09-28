---
title: Entrega 1
nav_order: 3
nav_exclude: false
---

# Entrega 1: fonte transacional modelada e populada

Tag [`e1`](https://github.com/cibelinda/Engenharia-Dados-Seguranca-Viaria/tree/e1) — 28/09/2026.

## Em uma frase

Um único `docker compose up` baixa os dados abertos de acidentes da PRF, cria o banco
PostgreSQL e carrega **632 mil acidentes e 1,5 milhão de pessoas** em cerca de 2 minutos.

## Pergunta de gestão

> **Quais trechos de 10 km das rodovias federais concentraram mais acidentes com mortos ou
> feridos graves entre 2017 e 2025, e esses trechos se mantêm de um ano para o outro?**

Mede **gravidade**, e não quantidade; agrupa por **BR + km**, que existe em todos os registros;
e a **persistência** entre os anos separa um ponto negro de um acidente isolado.
[Detalhes](pergunta-e-recorte.md)

## O que fizemos

| Etapa | O que foi feito | Issue |
|---|---|---|
| **Fonte** | Reconhecimento dos 50 arquivos da PRF (2007–2026) e downloader que confere o SHA-256 de cada arquivo | — |
| **Recorte** | Sistema BAT, 2017–2025, ocorrência e pessoa: formato único e anos completos | #2 |
| **Esteira** | Docker Compose com 4 serviços: banco, migrações (Flyway), download e carga | #5 |
| **Esquema** | 8 migrações: ocorrência, veículo e pessoa separados, com PKs, FKs e restrições | #3 |
| **Carga** | Ano a ano, com `COPY`; linhas inválidas vão para `linha_rejeitada` com o motivo | #4 |
| **Decisão** | ADR 0001: modelo normalizado, **insert-only, versionado por lote** | #6 |
| **Testes** | 80 testes: esquema, volume, distribuição, dado faltante e reprocessamento | #8 |
| **Evidência** | A PRF regrava arquivos, até de anos fechados; comparação direta em 26/10/2026 | #7 |

## A decisão central: guardar o histórico

A PRF **regrava** os arquivos no mesmo endereço, sem versão, inclusive de anos já fechados
(2024 foi regravado em 23/09/2026). Por isso a origem é **insert-only**: cada carga de um ano
vira um **lote**, e uma republicação entra como lote novo, sem apagar o anterior. As views
`*_vigente` mostram só a versão mais recente.

| | Opção nula (tabelas iguais ao CSV) | Adotada (normalizada, insert-only) |
|---|---|---|
| Guarda o histórico | Não | **Sim** |
| Tamanho em disco | 784 MB | **731 MB** |
| Consulta Q2 (mediana) | 618 ms | 708 ms |
| Custo de uma republicação de 2024 | — | +85 MB |

[ADR 0001 completo](adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md)

## Números da carga

| | Valor |
|---|---|
| Ocorrências carregadas | 632.708 |
| Veículos | 1.191.461 |
| Pessoas | 1.509.549 |
| Linhas rejeitadas (com motivo) | 29 |
| Coordenadas anuladas (fora do limite) | 33 |
| Subida do zero | ~2 min |
| Rodar de novo | ~4 s, sem duplicar nada |

## Carimbos de tempo

| Tempo | Onde |
|---|---|
| Evento (hora do acidente) | `ocorrencia.ocorrido_em` |
| Publicação na fonte | `lote_arquivo.drive_last_modified` |
| Ingestão (hora da carga) | `lote_carga.iniciado_em` / `finalizado_em` |
| Processamento | não existe na E1 |

## Checklist de aceite

- ✅ Domínio escolhido e pergunta de gestão em uma frase
- ✅ Esquema físico versionado com migrações, executáveis do zero em ordem
- ✅ Carga reprodutível com um comando, sem passo manual
- ✅ Volume: 632 mil ocorrências e 1,5 milhão de pessoas
- ✅ [Caracterização da carga](caracterizacao-da-carga.md) (volume, escrita, leitura, latência)
- ✅ Declaração de histórico: insert-only versionado por lote
- ✅ 1 ADR sobre a modelagem da origem
- ✅ README para terceiro subir com Docker Compose

## Limites e próximos passos

- A comparação direta entre versões dos arquivos da PRF está prevista para 26/10/2026 e vira
  insumo da E2 (captura de mudanças).
- O tamanho do trecho (10 km) e o critério de persistência serão calibrados na E3.
- A queda de 22,6% nas ocorrências em 2018 tem hipótese (mudança de critério de registro),
  ainda não verificada.
