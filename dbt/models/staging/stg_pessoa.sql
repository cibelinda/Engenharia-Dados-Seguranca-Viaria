-- Versão vigente de pessoa_vigente (base da E3). A limpeza desta camada é da issue do dbt;
-- os nomes das colunas não mudam, porque as outras partes dependem deles.
select * from {{ source('origem', 'pessoa_vigente') }}
