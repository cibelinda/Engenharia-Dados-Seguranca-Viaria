-- Domínio de causas de acidente (tabela causa_acidente, sem versão).
-- A limpeza é da issue do dbt (#43); os nomes das colunas não mudam, porque as outras
-- partes dependem deles.
select * from {{ source('origem', 'causa_acidente') }}
