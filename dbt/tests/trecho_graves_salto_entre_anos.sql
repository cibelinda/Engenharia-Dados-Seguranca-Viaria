-- Distribuição (salto de série): o número de acidentes graves de um ano completo não pode
-- variar mais de 20% em relação ao ano anterior. O total de acidentes cai pela metade na troca
-- do BR-Brasil para o BAT (2016 -> 2017), mas os graves não: de 2007 a 2025 a maior variação é
-- de 13% (2014 -> 2015). Um salto maior indica um ano carregado pela metade ou uma mudança na
-- definição de "grave", e não uma mudança nas estradas. O ano corrente (parcial) fica fora.
with por_ano as (
    select f.ano, count(*) filter (where f.grave) as graves
    from {{ ref('fct_ocorrencia') }} f
    join (select distinct ano from {{ ref('dim_tempo') }} where ano_completo) a using (ano)
    group by f.ano
)
select ano, graves, anterior,
       round(100.0 * (graves - anterior) / anterior, 1) as variacao_pct
from (select ano, graves, lag(graves) over (order by ano) as anterior from por_ano) t
where anterior is not null
  and abs(graves - anterior) > 0.20 * anterior
