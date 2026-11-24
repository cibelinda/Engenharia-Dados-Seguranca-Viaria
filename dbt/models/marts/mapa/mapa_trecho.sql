-- Onde fica cada trecho no mapa (issue #57). Granularidade: UM TRECHO com geom_centro.
--
-- O ponto é o centro dos acidentes com coordenada confiável do trecho (dim_trecho.geom_centro,
-- só do BAT, 2017 em diante), em WGS 84. Trecho sem coordenada confiável fica fora do mapa.
-- Os números de cada ano (graves, anos no top 50) o painel lê das tabelas da pergunta de
-- gestão, juntando pela chave_trecho.
{{ config(indexes=[{'columns': ['chave_trecho'], 'unique': True}]) }}

select
    chave_trecho,
    rotulo,
    br,
    uf,
    round(st_x(st_transform(geom_centro, 4326))::numeric, 5)::double precision as longitude,
    round(st_y(st_transform(geom_centro, 4326))::numeric, 5)::double precision as latitude
from {{ ref('dim_trecho') }}
where geom_centro is not null
