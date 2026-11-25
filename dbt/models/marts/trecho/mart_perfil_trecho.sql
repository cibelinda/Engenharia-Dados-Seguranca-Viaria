-- Como são os acidentes graves de cada trecho (issue #58): o ranking diz ONDE, o perfil ajuda a
-- entender POR QUÊ. Contrato das colunas na issue; explicação e limites em docs/e4/perfil.md.
-- Granularidade: UM TRECHO, todos os da dim_trecho (o que nunca teve acidente grave tem
-- graves = 0 e o resto NULL).
--
--   graves     : todos os anos, inclusive o corrente, parcial, como em anos_no_top_50.
--   graves_bat : dos graves, os do BAT (2017 em diante). É a base de pct_declive, causa_principal
--                e tipo_principal, que não existem (ou não se comparam) no BR-Brasil.
--   pct_*      : % dos graves com o atributo, entre os que têm a informação. As regras de cada
--                atributo estão na int_grave_atributo.
--   causa_principal, tipo_principal : o mais frequente nos graves do BAT, com ao menos 10 graves
--                (metrica_perfil_min_graves). Com menos que isso, o "mais frequente" é um ou dois
--                acidentes, e a causa de um acidente só é quase um dado do condutor (lgpd.md).
--                Empate: o que matou mais; depois, a ordem alfabética, para o build ser repetível.
--   causa_principal_desde_2021 : o mesmo, sem os anos do vocabulário antigo de causas. A PRF deixou
--                de usar 'Falta de atenção à condução' em 2020, e a soma desde 2017 ainda
--                a põe em primeiro em dois terços dos pontos negros.
{{ config(indexes=[{'columns': ['chave_trecho'], 'unique': True}]) }}

{%- set principais = [
    ('causa_principal',            'causa', "sistema = 'bat'"),
    ('causa_principal_desde_2021', 'causa', "ano >= 2021"),
    ('tipo_principal',             'tipo',  "sistema = 'bat'"),
] %}

with grave as materialized (
    select * from {{ ref('int_grave_atributo') }}
),

perfil as (
    select
        chave_trecho,
        count(*)                                as graves,
        count(*) filter (where sistema = 'bat') as graves_bat,
        {{ metrica_pct('curva') }}              as pct_curva,
        {{ metrica_pct('declive') }}            as pct_declive,
        {{ metrica_pct('pista_simples') }}      as pct_pista_simples,
        {{ metrica_pct('urbano') }}             as pct_urbano,
        {{ metrica_pct('noite') }}              as pct_noite,
        {{ metrica_pct('chuva') }}              as pct_chuva
    from grave
    group by chave_trecho
)
{%- for coluna, campo, filtro in principais %},

{{ coluna }} as (
    select distinct on (chave_trecho) chave_trecho, {{ campo }} as valor
    from (
        select
            chave_trecho,
            {{ campo }},
            count(*)                                        as vezes,
            sum(mortos)                                     as mortos,
            sum(count(*)) over (partition by chave_trecho)  as total
        from grave
        where {{ filtro }} and {{ campo }} is not null
        group by chave_trecho, {{ campo }}
    ) contagem
    where total >= {{ metrica_perfil_min_graves() }}
    order by chave_trecho, vezes desc, mortos desc, {{ campo }}
)
{%- endfor %}

select
    t.chave_trecho::text                    as chave_trecho,
    coalesce(p.graves, 0)::integer          as graves,
    coalesce(p.graves_bat, 0)::integer      as graves_bat,
    p.pct_curva,
    p.pct_declive,
    p.pct_pista_simples,
    p.pct_urbano,
    p.pct_noite,
    p.pct_chuva,
    {%- for coluna, campo, filtro in principais %}
    {{ coluna }}.valor::text as {{ coluna }}{{ "," if not loop.last }}
    {%- endfor %}
from {{ ref('dim_trecho') }} t
left join perfil p using (chave_trecho)
{%- for coluna, campo, filtro in principais %}
left join {{ coluna }} using (chave_trecho)
{%- endfor %}
