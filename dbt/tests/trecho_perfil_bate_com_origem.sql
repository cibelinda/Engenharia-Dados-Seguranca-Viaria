-- Os percentuais e os principais do perfil, recontados por outro caminho: direto da stg_ocorrencia,
-- com a regra de cada atributo escrita à mão, sem a int_grave_atributo nem as macros.
with grave as (
    select
        lpad(o.br::text, 3, '0') || '-' || o.uf || '-' || lpad((floor(o.km / 10) * 10)::int::text, 4, '0') as chave_trecho,
        o.ano, o.mortos, o.tracado_via, o.tipo_pista, o.uso_solo_urbano, o.fase_dia,
        o.condicao_meteorologica, c.causa, t.descricao as tipo
    from {{ ref('stg_ocorrencia') }} o
    left join {{ ref('dim_causa') }} c using (id_causa)
    left join {{ ref('stg_tipo') }} t using (id_tipo)
    where (o.mortos > 0 or o.feridos_graves > 0) and o.br <> 0 and o.uf is not null and o.km is not null
),

pct as (
    select
        chave_trecho,
        round(100.0 * count(*) filter (where tracado_via @> array['Curva'])
              / nullif(count(tracado_via), 0), 1) as curva,
        round(100.0 * count(*) filter (where ano >= 2017 and tracado_via @> array['Declive'])
              / nullif(count(tracado_via) filter (where ano >= 2017), 0), 1) as declive,
        round(100.0 * count(*) filter (where tipo_pista = 'Simples')
              / nullif(count(tipo_pista), 0), 1) as simples,
        round(100.0 * count(*) filter (where uso_solo_urbano)
              / nullif(count(uso_solo_urbano), 0), 1) as urbano,
        round(100.0 * count(*) filter (where fase_dia = 'Plena noite')
              / nullif(count(fase_dia), 0), 1) as noite,
        round(100.0 * count(*) filter (where condicao_meteorologica in ('Chuva', 'Garoa/Chuvisco'))
              / nullif(count(condicao_meteorologica), 0), 1) as chuva
    from grave
    group by chave_trecho
),

-- Quantas vezes aparece a causa (ou o tipo) que o mart escolheu, e quantas a mais frequente.
contagem as (
    select chave_trecho, 'causa_principal' as coluna, causa as valor, count(*) as vezes
    from grave where ano >= 2017 and causa is not null group by 1, 3
    union all
    select chave_trecho, 'causa_principal_desde_2021', causa, count(*)
    from grave where ano >= 2021 and causa is not null group by 1, 3
    union all
    select chave_trecho, 'tipo_principal', tipo, count(*)
    from grave where ano >= 2017 and tipo is not null group by 1, 3
),

esperado as (
    select chave_trecho, coluna, max(vezes) as maior, sum(vezes) as total
    from contagem group by 1, 2
),

no_mart as (
    select m.chave_trecho, v.coluna, v.valor
    from {{ ref('mart_perfil_trecho') }} m
    cross join lateral (values
        ('causa_principal', m.causa_principal),
        ('causa_principal_desde_2021', m.causa_principal_desde_2021),
        ('tipo_principal', m.tipo_principal)
    ) as v (coluna, valor)
)

select m.chave_trecho, 'percentual' as problema
from {{ ref('mart_perfil_trecho') }} m
left join pct p using (chave_trecho)
where (m.pct_curva, m.pct_declive, m.pct_pista_simples, m.pct_urbano, m.pct_noite, m.pct_chuva)
      is distinct from (p.curva, p.declive, p.simples, p.urbano, p.noite, p.chuva)
union all
select m.chave_trecho, m.coluna
from no_mart m
left join esperado e using (chave_trecho, coluna)
left join contagem c using (chave_trecho, coluna, valor)
where (m.valor is not null) <> (coalesce(e.total, 0) >= 10)
   or (m.valor is not null and c.vezes is distinct from e.maior)
