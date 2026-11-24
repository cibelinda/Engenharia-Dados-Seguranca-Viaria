-- Fato do acidente. Granularidade: UMA LINHA POR ACIDENTE na versão vigente de cada ano, com a
-- chave (id_lote, id) do banco. 2007 a 2026, BR-Brasil e BAT juntos.
--
-- Chaves das dimensões:
--   data         -> dim_tempo   (dia do acidente, hora local da PRF, sem fuso)
--   chave_trecho -> dim_trecho  (BR + UF + faixa de 10 km). NULL quando não dá para montar o
--                                trecho: br = 0 (rodovia não identificada), br, uf ou km nulos.
--   id_causa     -> dim_causa   (causa principal; NULL em 2 acidentes do BR-Brasil)
--
-- A coordenada (só BAT, 2017+) vem com duas marcas, porque nem todo ponto é o local do acidente
-- (ADR 0002, item 4):
--   coordenada_padrao    : o ponto exato é compartilhado por 10 ou mais acidentes de kms
--                          diferentes. É o "ponto padrão" que cobre metade de 2019–2024;
--   coordenada_confiavel : tem ponto, não é padrão e cai dentro do retângulo do Brasil.
-- Análise espacial (agrupamento, distância) deve usar só coordenada_confiavel.
{{ config(indexes=[
    {'columns': ['id_lote', 'id'], 'unique': True},
    {'columns': ['chave_trecho', 'ano']},
]) }}

with ocorrencia as (
    select * from {{ ref('stg_ocorrencia') }}
),

ponto_padrao as (
    select latitude, longitude
    from ocorrencia
    where latitude is not null
    group by latitude, longitude
    having count(*) >= 10 and count(distinct km) > 1
)

select
    o.id_lote,
    o.id,
    l.sistema,
    o.ocorrido_em::date as data,
    extract(hour from o.ocorrido_em)::smallint as hora,
    o.ano,
    -- Mesma regra do contrato (docs/e3/README.md): floor(km / 10) * 10.
    case when o.br <> 0 and o.uf is not null and o.km is not null then
        lpad(o.br::text, 3, '0') || '-' || o.uf || '-' || lpad((floor(o.km / 10) * 10)::int::text, 4, '0')
    end as chave_trecho,
    o.id_causa,
    o.id_tipo,
    o.uf,
    o.br,
    o.km,
    o.municipio,
    o.uso_solo_urbano,
    o.fase_dia,
    o.condicao_meteorologica,
    o.tipo_pista,
    o.sentido_via,
    o.classificacao_acidente,
    -- Medidas
    o.pessoas,
    o.veiculos,
    o.mortos,
    o.feridos_graves,
    o.feridos_leves,
    o.ilesos,
    -- Regra única da métrica (macros/metricas.sql).
    {{ metrica_grave('o.mortos', 'o.feridos_graves') }} as grave,
    -- Coordenada
    o.geom,
    (p.latitude is not null) as coordenada_padrao,
    (o.geom is not null and p.latitude is null
        and o.longitude between -74 and -28 and o.latitude between -34 and 5.5) as coordenada_confiavel
from ocorrencia o
join {{ ref('stg_lote') }} l using (id_lote)
left join ponto_padrao p
  on p.latitude = o.latitude and p.longitude = o.longitude
