-- Contorno de cada município para o mapa do painel (issue #57). Granularidade: UM MUNICÍPIO.
--
--   geom, geojson : o contorno do IBGE simplificado (tolerância de 0,01 grau, cerca de 1 km) e
--                   convertido para WGS 84 (SRID 4326), o sistema que os mapas da web usam. Sem
--                   simplificar, os 5.570 contornos passam de 100 MB; assim, ficam em 3 MB.
--   graves, graves_por_100_mil : do último ano completo (ano_referencia), vindos da
--                   mart_risco_municipio_ano. Para outro ano, o painel junta pelo cod_municipio
--                   com a mart_risco_municipio_ano, sem recalcular nada.
{{ config(indexes=[{'columns': ['cod_municipio'], 'unique': True}, {'columns': ['uf']}]) }}

with referencia as (
    select max(ano) as ano
    from (select ano from {{ ref('dim_tempo') }} group by ano having bool_and(ano_completo)) a
),

contorno as (
    select
        cod_municipio,
        st_transform(st_simplifypreservetopology(geom, 0.01), 4326) as geom
    from {{ source('ibge', 'malha_municipal') }}
)

select
    m.cod_municipio,
    m.nome,
    m.uf,
    c.geom::geometry(Geometry, 4326)          as geom,
    st_asgeojson(c.geom, 4)                   as geojson,
    r.ano::smallint                           as ano_referencia,
    coalesce(a.graves, 0)::integer            as graves,
    a.graves_por_100_mil
from {{ ref('stg_ibge_municipio') }} m
join contorno c using (cod_municipio)
cross join referencia r
left join {{ ref('mart_risco_municipio_ano') }} a
       on a.cod_municipio = m.cod_municipio and a.ano = r.ano
