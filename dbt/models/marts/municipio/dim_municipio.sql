-- Dimensão de município com histórico (variação lenta). Uma linha por município por versão:
-- se o IBGE muda o nome ou a UF, a versão antiga continua aqui, com o período em que valeu.
select
    dbt_scd_id      as chave_municipio,
    cod_municipio,
    nome,
    uf,
    dbt_valid_from  as valido_de,
    dbt_valid_to    as valido_ate,
    dbt_valid_to is null as atual
from {{ ref('snap_municipio') }}
