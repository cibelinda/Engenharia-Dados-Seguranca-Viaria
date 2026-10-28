-- Causas de cada ocorrência, na versão vigente (view ocorrencia_causa_vigente).
-- A limpeza é da issue do dbt (#43); os nomes das colunas não mudam, porque as outras
-- partes dependem deles.
select * from {{ source('origem', 'ocorrencia_causa_vigente') }}
