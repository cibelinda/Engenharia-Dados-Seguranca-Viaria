-- Volume: os acidentes graves do ranking, somados aos que não acharam município, são
-- exatamente os acidentes graves da origem, ano a ano. Nada some e nada é contado duas vezes.
with origem as (
    select ano, count(*) filter (where mortos > 0 or feridos_graves > 0) as graves
    from {{ ref('stg_ocorrencia') }} group by 1
),
ranking as (
    select ano, sum(graves) as graves from {{ ref('mart_risco_municipio_ano') }} group by 1
),
sem_municipio as (
    select l.ano, count(*) as graves
    from {{ ref('int_ocorrencia_municipio') }} l
    join {{ ref('stg_ocorrencia') }} o using (id_lote, id)
    where l.cod_municipio is null and (o.mortos > 0 or o.feridos_graves > 0)
    group by 1
)
select o.ano, o.graves, coalesce(r.graves, 0) + coalesce(s.graves, 0) as somados
from origem o
left join ranking r using (ano)
left join sem_municipio s using (ano)
where o.graves <> coalesce(r.graves, 0) + coalesce(s.graves, 0)
