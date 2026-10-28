-- Em qual município aconteceu cada acidente. Uma linha por acidente.
--   1. Pela coordenada (2017 em diante): o ponto do acidente cai dentro do contorno do município.
--   2. Pelo nome (quando não há coordenada, como em 2007–2016): o nome do município da PRF,
--      normalizado, igual ao do IBGE na mesma UF.
--   3. Pelo nome antigo: municípios que mudaram de nome (ex.: Embu virou Embu das Artes), na
--      tabela fixa municipio_nome_antigo.
-- Fica como tabela (e não view) porque a busca pelo contorno é pesada.
{{ config(materialized='table', indexes=[{'columns': ['id_lote', 'id'], 'unique': True}]) }}

with ocorrencia as (
    select id_lote, id, ano, uf, municipio, geom
    from {{ ref('stg_ocorrencia') }}
),

pela_coordenada as (
    select distinct on (o.id_lote, o.id) o.id_lote, o.id, m.cod_municipio
    from ocorrencia o
    join {{ source('ibge', 'malha_municipal') }} m
      on o.geom is not null and st_intersects(m.geom, o.geom)
    order by o.id_lote, o.id, m.cod_municipio
),

pelo_nome as (
    select distinct on (o.id_lote, o.id) o.id_lote, o.id, mu.cod_municipio
    from ocorrencia o
    join {{ ref('stg_ibge_municipio') }} mu
      on mu.uf = o.uf
     and mu.nome_normalizado = trim(regexp_replace(
            regexp_replace(upper(unaccent(replace(o.municipio, '''', ''))), '[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g'))
    order by o.id_lote, o.id, mu.cod_municipio
),

pelo_nome_antigo as (
    select o.id_lote, o.id, a.cod_municipio
    from ocorrencia o
    join {{ ref('municipio_nome_antigo') }} a
      on a.uf = o.uf
     and a.nome_prf = trim(regexp_replace(
            regexp_replace(upper(unaccent(replace(o.municipio, '''', ''))), '[^A-Z0-9 -]', ' ', 'g'), ' +', ' ', 'g'))
)

select
    o.id_lote,
    o.id,
    o.ano,
    coalesce(c.cod_municipio, n.cod_municipio, a.cod_municipio) as cod_municipio,
    case
        when c.cod_municipio is not null then 'coordenada'
        when n.cod_municipio is not null then 'nome'
        when a.cod_municipio is not null then 'nome_antigo'
        else 'sem_ligacao'
    end as metodo,
    -- Quando as duas formas ligam, elas concordam? Serve para conferir a ligação pelo nome.
    (c.cod_municipio is not null and n.cod_municipio is not null
        and c.cod_municipio <> n.cod_municipio) as coordenada_e_nome_divergem
from ocorrencia o
left join pela_coordenada c using (id_lote, id)
left join pelo_nome n using (id_lote, id)
left join pelo_nome_antigo a using (id_lote, id)
