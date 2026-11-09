-- Dimensão de tempo. Granularidade: UM DIA. Todos os dias do primeiro ao último acidente da
-- origem, inclusive os dias sem acidente (para que "zero acidentes no dia" seja uma linha, e não
-- uma ausência). A hora do acidente fica no fato (coluna hora), porque é hora local sem fuso.
-- `ano_completo` = false no ano corrente, que a PRF publica até o mês anterior: rankings
-- e comparações entre anos usam só os anos completos.
{{ config(indexes=[{'columns': ['data'], 'unique': True}]) }}

with limites as (
    select min(ocorrido_em)::date as primeiro, max(ocorrido_em)::date as ultimo
    from {{ ref('stg_ocorrencia') }}
),

dia as (
    select generate_series(primeiro, ultimo, interval '1 day')::date as data
    from limites
)

select
    d.data,
    extract(year from d.data)::smallint                as ano,
    extract(quarter from d.data)::smallint             as trimestre,
    extract(month from d.data)::smallint               as mes,
    (array['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
           'setembro', 'outubro', 'novembro', 'dezembro'])[extract(month from d.data)] as nome_mes,
    extract(day from d.data)::smallint                 as dia,
    -- ISO: 1 = segunda ... 7 = domingo
    extract(isodow from d.data)::smallint              as dia_semana,
    (array['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'])[extract(isodow from d.data)]
                                                       as nome_dia_semana,
    extract(isodow from d.data) in (6, 7)              as fim_de_semana,
    -- O ano está completo quando a origem tem acidente em 31/12 dele (a PRF publica o ano
    -- corrente parcial e o regrava todo mês).
    extract(year from d.data) < extract(year from l.ultimo)
        or l.ultimo = make_date(extract(year from l.ultimo)::int, 12, 31) as ano_completo
from dia d
cross join limites l
