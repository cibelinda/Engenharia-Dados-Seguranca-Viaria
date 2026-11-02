-- População por município e ano (estimativas anuais e censos 2010 e 2022).
select cod_municipio, ano, populacao, fonte
from {{ source('ibge', 'populacao') }}
