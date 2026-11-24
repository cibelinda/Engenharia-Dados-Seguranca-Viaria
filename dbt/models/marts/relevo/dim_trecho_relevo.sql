-- Relevo de cada trecho (#59). Granularidade: UM TRECHO, para cada trecho da dim_trecho que
-- tem geom_centro (o centro dos acidentes com coordenada confiável, desde 2017).
--
-- O relevo é o do polígono do IBGE mais próximo do centro do trecho, sem contar os de água:
--   - distância 0 (o caso de 99% dos trechos): o centro cai dentro do polígono;
--   - distância > 0: o centro cai na água (ponte, represa) ou fora do mapa do IBGE (litoral,
--     fronteira), e aí vale o polígono de terra mais perto. distancia_m mostra quanto.
-- O "mais próximo" usa o índice espacial (operador <->), então não varre os 120 mil polígonos.
{{ config(indexes=[{'columns': ['chave_trecho'], 'unique': True}]) }}

select
    t.chave_trecho,
    r.tipo_relevo,
    r.unidade_relevo,
    r.regiao_relevo,
    r.dominio_relevo,
    r.natureza_modelado,
    round(st_distance(r.geom::geography, t.geom_centro::geography)::numeric, 0) as distancia_m
from {{ ref('dim_trecho') }} t
cross join lateral (
    select *
    from {{ ref('stg_relevo_modelado') }} m
    where not m.agua
    order by m.geom <-> t.geom_centro
    limit 1
) r
where t.geom_centro is not null
