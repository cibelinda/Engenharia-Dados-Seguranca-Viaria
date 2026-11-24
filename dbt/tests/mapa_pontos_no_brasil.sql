-- Distribuição (issue #57): todo ponto do mapa (trecho e acidente) cai dentro do retângulo do
-- Brasil. Um ponto fora é coordenada trocada ou SRID errado na conversão para WGS 84.
select 'trecho' as origem, chave_trecho as chave, longitude, latitude
from {{ ref('mapa_trecho') }}
where longitude not between -74 and -28 or latitude not between -34 and 5.5
union all
select 'acidente', ano::text, longitude, latitude
from {{ ref('mapa_acidente_grave') }}
where longitude not between -74 and -28 or latitude not between -34 and 5.5
