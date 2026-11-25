-- A mart_perfil_comparacao recontada direto da fct_ocorrencia, com o critério de ponto negro
-- escrito à mão (3 ou mais anos com posicao <= 50): os percentuais e os denominadores. São seis
-- linhas, uma por atributo; um atributo a mais ou a menos também falha.
with ponto_negro as (
    select chave_trecho
    from {{ ref('mart_risco_trecho_ano') }}
    where posicao <= 50
    group by chave_trecho
    having count(*) >= 3
),

grave as (
    select f.*, (n.chave_trecho is not null) as negro
    from {{ ref('fct_ocorrencia') }} f
    left join ponto_negro n using (chave_trecho)
    where f.grave and f.chave_trecho is not null
),

soma as (
    select 'Curva' as atributo, negro, count(*) filter (where tracado_via @> array['Curva']) as sim,
           count(tracado_via) as n from grave group by negro
    union all
    select 'Declive', negro, count(*) filter (where tracado_via @> array['Declive']),
           count(tracado_via) from grave where ano >= 2017 group by negro
    union all
    select 'Pista simples', negro, count(*) filter (where tipo_pista = 'Simples'),
           count(tipo_pista) from grave group by negro
    union all
    select 'Área urbana', negro, count(*) filter (where uso_solo_urbano),
           count(uso_solo_urbano) from grave group by negro
    union all
    select 'Noite', negro, count(*) filter (where fase_dia = 'Plena noite'),
           count(fase_dia) from grave group by negro
    union all
    select 'Chuva', negro, count(*) filter (where condicao_meteorologica in ('Chuva', 'Garoa/Chuvisco')),
           count(condicao_meteorologica) from grave group by negro
),

esperado as (
    select
        atributo,
        max(round(100.0 * sim / nullif(n, 0), 1)) filter (where negro)     as pct_negros,
        max(round(100.0 * sim / nullif(n, 0), 1)) filter (where not negro) as pct_demais,
        max(n) filter (where negro)     as n_negros,
        max(n) filter (where not negro) as n_demais
    from soma
    group by atributo
)

select atributo, m.pct_pontos_negros, e.pct_negros, m.pct_demais_trechos, e.pct_demais
from {{ ref('mart_perfil_comparacao') }} m
full join esperado e using (atributo)
where m.pct_pontos_negros     is distinct from e.pct_negros
   or m.pct_demais_trechos    is distinct from e.pct_demais
   or m.graves_pontos_negros  is distinct from e.n_negros
   or m.graves_demais_trechos is distinct from e.n_demais
