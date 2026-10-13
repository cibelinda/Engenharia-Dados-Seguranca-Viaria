---
title: Decisões (ADRs)
nav_order: 5
has_children: true
has_toc: false
nav_exclude: false
---

# Decisões de arquitetura (ADRs)

Cada ADR registra uma decisão: o contexto, as alternativas, o que foi medido, o que se ganha e o
que se perde, e quando revisar.

| ADR | Decisão | Situação |
|---|---|---|
| [0001](0001-modelo-normalizado-insert-only-versionado-por-lote.md) | Origem normalizada e insert-only, versionada por lote de carga | Aceito; revisado em 13/10/2026 com o dataset completo |
| [0002](0002-banco-espacial-postgis.md) | Banco espacial: PostgreSQL com PostGIS | Aceito (correção da E1) |
| [0003](0003-dataset-completo-br-brasil-e-bat.md) | Dataset completo da PRF, BR-Brasil e BAT no mesmo esquema | Aceito (correção da E1) |
