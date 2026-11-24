-- Todo trecho com geom_centro tem relevo: o polígono mais próximo sempre existe, então nenhum
-- trecho com coordenada pode faltar na dim_trecho_relevo.
select t.chave_trecho
from {{ ref('dim_trecho') }} t
left join {{ ref('dim_trecho_relevo') }} r using (chave_trecho)
where t.geom_centro is not null and r.chave_trecho is null
