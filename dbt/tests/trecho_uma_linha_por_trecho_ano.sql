-- Unicidade: uma linha por trecho por ano no ranking.
select chave_trecho, ano, count(*) as vezes
from {{ ref('mart_risco_trecho_ano') }}
group by 1, 2
having count(*) > 1
