-- Acidentes graves com coordenada confiável, para a camada de densidade do mapa (issue #57).
-- Granularidade: UM ACIDENTE GRAVE com coordenada confiável (BAT, 2017 em diante).
--
-- Só o ano, a UF e o ponto: sem data, hora nem pessoa. O mapa mostra onde os graves se
-- concentram, e o ano é o filtro do painel (docs/e4/lgpd.md). De 2019 a 2024, metade das
-- coordenadas é um ponto padrão da PRF, e não o local do acidente: esses ficam de fora
-- (coordenada_confiavel, da fct_ocorrencia).
{{ config(indexes=[{'columns': ['ano', 'uf']}]) }}

select
    ano::smallint                                                          as ano,
    uf::text                                                               as uf,
    round(st_x(st_transform(geom, 4326))::numeric, 5)::double precision   as longitude,
    round(st_y(st_transform(geom, 4326))::numeric, 5)::double precision   as latitude
from {{ ref('fct_ocorrencia') }}
where grave and coordenada_confiavel
