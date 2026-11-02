-- Valor que não cabe: população zero ou negativa, ou mais graves do que acidentes.
select *
from {{ ref('mart_risco_municipio_ano') }}
where populacao <= 0 or graves > acidentes or graves_por_100_mil < 0
