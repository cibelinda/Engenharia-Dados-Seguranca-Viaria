-- A métrica graves dá o mesmo número em todo lugar:
--   1. a coluna grave do fato segue a regra do contrato (mortos > 0 or feridos_graves > 0),
--      acidente a acidente;
--   2. os graves da mart_risco_trecho_ano, trecho a trecho e ano a ano, são a medida graves da
--      camada semântica (soma de grave no fct_ocorrencia) agrupada por trecho e ano;
--   3. os graves da mart_risco_municipio_ano, município a município e ano a ano, são a mesma
--      regra contada nos acidentes ligados ao município.
with fato_fora_da_regra as (
    select 'fato' as onde, chave_trecho as chave, ano, null::bigint as no_mart, null::bigint as na_definicao
    from {{ ref('fct_ocorrencia') }}
    where grave is distinct from (mortos > 0 or feridos_graves > 0)
),

trecho_definicao as (
    select chave_trecho, ano, sum(case when grave then 1 else 0 end) as graves
    from {{ ref('fct_ocorrencia') }}
    where chave_trecho is not null
    group by chave_trecho, ano
),

trecho as (
    select 'trecho' as onde, coalesce(m.chave_trecho, d.chave_trecho) as chave,
           coalesce(m.ano, d.ano) as ano, m.graves::bigint as no_mart, d.graves::bigint as na_definicao
    from {{ ref('mart_risco_trecho_ano') }} m
    full join trecho_definicao d on d.chave_trecho = m.chave_trecho and d.ano = m.ano
    where m.graves is distinct from d.graves
),

municipio_definicao as (
    select l.cod_municipio, l.ano, count(*) filter (where o.mortos > 0 or o.feridos_graves > 0) as graves
    from {{ ref('int_ocorrencia_municipio') }} l
    join {{ ref('stg_ocorrencia') }} o using (id_lote, id)
    where l.cod_municipio is not null
    group by l.cod_municipio, l.ano
),

municipio as (
    select 'municipio' as onde, coalesce(m.cod_municipio, d.cod_municipio)::text as chave,
           coalesce(m.ano, d.ano) as ano, m.graves::bigint as no_mart, d.graves::bigint as na_definicao
    from {{ ref('mart_risco_municipio_ano') }} m
    full join municipio_definicao d on d.cod_municipio = m.cod_municipio and d.ano = m.ano
    where m.graves is distinct from d.graves
)

select * from fato_fora_da_regra
union all select * from trecho
union all select * from municipio
