-- Volume: os acidentes graves do ranking, somados aos graves que não têm trecho (br = 0, ou
-- sem br, uf ou km), são exatamente os graves da origem, ano a ano. Nada some e nada é
-- contado duas vezes entre a origem e a resposta da pergunta de gestão.
with origem as (
    select ano, count(*) filter (where mortos > 0 or feridos_graves > 0) as graves
    from {{ ref('stg_ocorrencia') }} group by ano
),
ranking as (
    select ano, sum(graves) as graves from {{ ref('mart_risco_trecho_ano') }} group by ano
),
sem_trecho as (
    select ano, count(*) as graves
    from {{ ref('fct_ocorrencia') }}
    where chave_trecho is null and grave
    group by ano
)
select o.ano, o.graves, coalesce(r.graves, 0) + coalesce(s.graves, 0) as somados
from origem o
left join ranking r using (ano)
left join sem_trecho s using (ano)
where o.graves <> coalesce(r.graves, 0) + coalesce(s.graves, 0)
