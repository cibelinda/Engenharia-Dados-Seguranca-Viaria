-- O que os acidentes graves dos pontos negros têm de diferente (issue #58). É o que transforma o
-- ranking em diagnóstico. Explicação, números e limites em docs/e4/perfil.md.
-- Granularidade: UM ATRIBUTO.
--
--   ponto negro : coluna ponto_negro da mart_persistencia_trecho (regra em macros/metricas.sql).
--   pct_*       : % dos acidentes graves do grupo com o atributo, entre os que têm a informação.
--                 A conta é por ACIDENTE, com todos os graves do grupo somados, e não a média dos
--                 percentuais dos trechos: um trecho com 2 graves não pesa o mesmo que um com 2 mil.
--   graves_*    : o denominador de cada percentual. Muda por atributo (o declive só tem o BAT).
--   razao       : pct_pontos_negros / pct_demais_trechos, como na mart_relevo_comparacao (#59).
--
-- É comparação, e não causa: os pontos negros ficam onde há mais tráfego, e o tráfego não está aqui.
with atributo_do_grave as (
    select
        p.ponto_negro,
        a.atributo,
        a.valor
    from {{ ref('int_grave_atributo') }} g
    join {{ ref('mart_persistencia_trecho') }} p using (chave_trecho)
    cross join lateral (values
        ('Curva',         g.curva),
        ('Declive',       g.declive),
        ('Pista simples', g.pista_simples),
        ('Área urbana',   g.urbano),
        ('Noite',         g.noite),
        ('Chuva',         g.chuva)
    ) as a (atributo, valor)
),

por_atributo as (
    select
        atributo::text                                             as atributo,
        {{ metrica_pct('case when ponto_negro then valor end') }}     as pct_pontos_negros,
        {{ metrica_pct('case when not ponto_negro then valor end') }} as pct_demais_trechos,
        (count(valor) filter (where ponto_negro))::integer         as graves_pontos_negros,
        (count(valor) filter (where not ponto_negro))::integer     as graves_demais_trechos
    from atributo_do_grave
    group by atributo
)

select
    atributo,
    pct_pontos_negros,
    pct_demais_trechos,
    round(pct_pontos_negros / nullif(pct_demais_trechos, 0), 2)::numeric(6, 2) as razao,
    graves_pontos_negros,
    graves_demais_trechos
from por_atributo
