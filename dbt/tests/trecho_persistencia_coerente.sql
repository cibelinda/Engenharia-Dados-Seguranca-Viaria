-- Coerência da mart_persistencia_trecho:
--   * anos_no_top_50 vai de 0 ao número de anos da série, e não passa do número de anos entre
--     o primeiro e o último ano no top;
--   * primeiro e último ano no top existem se, e só se, o trecho já ficou no top;
--   * cada ano no top tem ao menos um acidente grave, então graves_no_total >= anos_no_top_50,
--     e trecho que nunca ficou no top tem graves_no_total = 0;
--   * cada ano tem ao menos 50 trechos no top (o rank empata, então pode ter mais): a soma de
--     anos_no_top_50 não fica abaixo de 50 por ano da série.
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
),

total as (
    select 'soma' as chave_trecho, sum(p.anos_no_top_50)::integer as anos_no_top_50,
           null::integer as graves_no_total, null::smallint as primeiro_ano_no_top_50,
           null::smallint as ultimo_ano_no_top_50
    from {{ ref('mart_persistencia_trecho') }} p
    having sum(p.anos_no_top_50) < 50 * (select n from anos)
)

select * from linha
union all
select * from total
