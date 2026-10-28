-- Distribuição: em todo ano, no máximo 0,5% dos acidentes ficam sem município. Se a PRF
-- passar a escrever o nome de outro jeito, ou a coordenada vier errada, a taxa sobe e o teste
-- avisa antes de o ranking ficar errado em silêncio.
select ano,
       round(100.0 * avg((metodo = 'sem_ligacao')::int), 2) as pct_sem_municipio
from {{ ref('int_ocorrencia_municipio') }}
group by ano
having avg((metodo = 'sem_ligacao')::int) > 0.005
