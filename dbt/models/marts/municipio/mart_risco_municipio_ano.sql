-- Qual município é mais perigoso. Uma linha por município por ano.
-- "Grave" = acidente com morto ou ferido grave. A taxa é por 100 mil habitantes, com a
-- população do mesmo ano ou, se o IBGE não tiver (2007 e 2023), a do ano mais próximo.
-- A posição pela taxa só vale para municípios com pelo menos 10 acidentes graves no ano:
-- abaixo disso, um único acidente numa cidade pequena distorce o ranking.
-- As regras de "grave" e da taxa vêm da camada de métricas (macros/metricas.sql, issue #53).
{{ config(indexes=[{'columns': ['ano', 'cod_municipio'], 'unique': True}]) }}

with por_municipio as (
    select
        l.cod_municipio,
        l.ano,
        count(*) as acidentes,
        count(*) filter (where {{ metrica_grave('o.mortos', 'o.feridos_graves') }}) as graves,
        sum(o.mortos) as mortos
    from {{ ref('int_ocorrencia_municipio') }} l
    join {{ ref('stg_ocorrencia') }} o using (id_lote, id)
    where l.cod_municipio is not null
    group by 1, 2
),

com_populacao as (
    select m.*, p.populacao, p.ano as ano_populacao
    from por_municipio m
    left join lateral (
        select populacao, ano
        from {{ ref('stg_ibge_populacao') }} p
        where p.cod_municipio = m.cod_municipio
        order by abs(p.ano - m.ano), p.ano desc
        limit 1
    ) p on true
)

select
    c.cod_municipio,
    d.nome,
    d.uf,
    c.ano,
    c.acidentes,
    c.graves,
    c.mortos,
    c.populacao,
    c.ano_populacao,
    {{ metrica_graves_por_100_mil('c.graves', 'c.populacao') }} as graves_por_100_mil,
    rank() over (partition by c.ano order by c.graves desc) as posicao_graves,
    case when c.graves >= 10 then
        rank() over (partition by c.ano, (c.graves >= 10)
                     order by c.graves * 1.0 / nullif(c.populacao, 0) desc)
    end as posicao_taxa
from com_populacao c
left join {{ ref('dim_municipio') }} d
  on d.cod_municipio = c.cod_municipio and d.atual
