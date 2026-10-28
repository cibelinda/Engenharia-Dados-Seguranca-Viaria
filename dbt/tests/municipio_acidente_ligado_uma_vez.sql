-- Unicidade: cada acidente aparece uma vez só na ligação com o município.
select id_lote, id, count(*) as vezes
from {{ ref('int_ocorrencia_municipio') }}
group by 1, 2
having count(*) > 1
