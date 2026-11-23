-- Coerência da mart_persistencia_trecho:
--   * anos_no_top_50 vai de 0 ao número de anos da série, e não passa do número de anos entre
--     o primeiro e o último ano no top;
--   * primeiro e último ano no top existem se, e só se, o trecho já ficou no top;
--   * cada ano no top tem ao menos um acidente grave, então graves_no_total >= anos_no_top_50,
--     e trecho que nunca ficou no top tem graves_no_total = 0;
--   * anos_completos_no_top_50 fica entre 0 e anos_no_top_50;
--   * a soma de anos_no_top_50 é o número de linhas com no_top_50 na mart_risco_trecho_ano;
--   * ano a ano, há ao menos 50 trechos no top (o rank empata, então pode ter mais), ou todos os
--     trechos com grave, se o ano tiver menos de 50. Conferido por ano, e não pela soma: um
--     empate num ano esconderia um trecho faltando em outro.
with anos as (
    select count(distinct ano) as n from {{ ref('mart_risco_trecho_ano') }}
),

linha as (
    select p.chave_trecho, p.anos_no_top_50, p.graves_no_total,
           p.primeiro_ano_no_top_50, p.ultimo_ano_no_top_50
    from {{ ref('mart_persistencia_trecho') }} p
    cross join anos a
    where p.anos_no_top_50 < 0 or p.anos_no_top_50 > a.n
       or p.anos_no_top_50 > p.ultimo_ano_no_top_50 - p.primeiro_ano_no_top_50 + 1
       or (p.anos_no_top_50 > 0) <> (p.primeiro_ano_no_top_50 is not null)
       or (p.anos_no_top_50 > 0) <> (p.ultimo_ano_no_top_50 is not null)
       or p.graves_no_total < p.anos_no_top_50
       or (p.anos_no_top_50 = 0 and p.graves_no_total <> 0)
       or p.anos_completos_no_top_50 < 0 or p.anos_completos_no_top_50 > p.anos_no_top_50
),

soma as (
    select 'soma' as chave_trecho, sum(p.anos_no_top_50)::integer as anos_no_top_50,
           null::integer as graves_no_total, null::smallint as primeiro_ano_no_top_50,
           null::smallint as ultimo_ano_no_top_50
    from {{ ref('mart_persistencia_trecho') }} p
    having sum(p.anos_no_top_50) <> (select count(*) filter (where no_top_50)
                                     from {{ ref('mart_risco_trecho_ano') }})
),

por_ano as (
    select 'ano ' || ano as chave_trecho, (count(*) filter (where no_top_50))::integer as anos_no_top_50,
           null::integer as graves_no_total, null::smallint as primeiro_ano_no_top_50,
           null::smallint as ultimo_ano_no_top_50
    from {{ ref('mart_risco_trecho_ano') }}
    group by ano
    having count(*) filter (where no_top_50) < least(50, count(*) filter (where graves > 0))
)

select * from linha
union all
select * from soma
union all
select * from por_ano
