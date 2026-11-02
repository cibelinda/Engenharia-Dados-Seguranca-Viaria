-- Histórico: cada município tem exatamente uma versão atual.
select cod_municipio, count(*) filter (where atual) as versoes_atuais
from {{ ref('dim_municipio') }}
group by 1
having count(*) filter (where atual) <> 1
