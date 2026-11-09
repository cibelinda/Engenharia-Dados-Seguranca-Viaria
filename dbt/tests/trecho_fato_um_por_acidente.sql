-- Unicidade: o fato tem uma linha por acidente. A chave é composta (id_lote, id), por isso é
-- um teste singular, e não o `unique` do dbt. Um join errado com o lote ou com o ponto padrão
-- duplicaria acidentes aqui.
select id_lote, id, count(*) as vezes
from {{ ref('fct_ocorrencia') }}
group by 1, 2
having count(*) > 1
