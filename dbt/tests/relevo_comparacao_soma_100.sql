-- Os percentuais de cada grupo (pontos negros e demais trechos) somam 100%, com folga para o
-- arredondamento de cada linha.
select 'pontos_negros' as grupo, sum(pct_pontos_negros) as soma
from {{ ref('mart_relevo_comparacao') }}
having abs(sum(pct_pontos_negros) - 100) > 1
union all
select 'demais_trechos', sum(pct_demais_trechos)
from {{ ref('mart_relevo_comparacao') }}
having abs(sum(pct_demais_trechos) - 100) > 1
