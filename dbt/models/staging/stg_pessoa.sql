-- Pessoas, na versão vigente de cada ano (view pessoa_vigente).
-- A limpeza é da issue do dbt (#43); os nomes das colunas não mudam, porque as outras
-- partes dependem deles.
select * from {{ source('origem', 'pessoa_vigente') }}
