-- Unicidade: uma linha por município por ano no ranking.
select cod_municipio, ano, count(*) as vezes
from {{ ref('mart_risco_municipio_ano') }}
group by 1, 2
having count(*) > 1
