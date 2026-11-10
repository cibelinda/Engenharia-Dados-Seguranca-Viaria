-- A métrica anos_no_top_50 dá o mesmo número nos três lugares em que ela aparece, trecho a
-- trecho:
--   * na mart_persistencia_trecho (o que o painel e o ETL reverso leem);
--   * na camada semântica (models/metricas/_metricas.yml): a soma de no_top_50 por trecho na
--     mart_risco_trecho_ano, que é como o MetricFlow agrega a medida anos_no_top_50;
--   * na regra do contrato, escrita aqui à mão: posicao <= 50 (docs/e4/README.md).
-- O mesmo para graves_no_total (graves somados nos anos no top). Pega a coluna no_top_50 fora
-- da regra, a macro mudada sem querer e trecho que some ou aparece na persistência.
with semantica as (
    select chave_trecho,
           sum(case when no_top_50 then 1 else 0 end)          as anos,
           coalesce(sum(graves) filter (where no_top_50), 0)   as graves
    from {{ ref('mart_risco_trecho_ano') }}
    group by chave_trecho
),

contrato as (
    select chave_trecho,
           count(*) filter (where posicao <= 50)                   as anos,
           coalesce(sum(graves) filter (where posicao <= 50), 0)   as graves
    from {{ ref('mart_risco_trecho_ano') }}
    group by chave_trecho
)

select coalesce(p.chave_trecho, s.chave_trecho) as chave_trecho,
       p.anos_no_top_50, s.anos as anos_semantica, c.anos as anos_contrato,
       p.graves_no_total, s.graves as graves_semantica, c.graves as graves_contrato
from {{ ref('mart_persistencia_trecho') }} p
full join semantica s using (chave_trecho)
full join contrato c using (chave_trecho)
where p.chave_trecho is null or s.chave_trecho is null or c.chave_trecho is null
   or p.anos_no_top_50 <> s.anos or p.anos_no_top_50 <> c.anos
   or p.graves_no_total <> s.graves or p.graves_no_total <> c.graves
