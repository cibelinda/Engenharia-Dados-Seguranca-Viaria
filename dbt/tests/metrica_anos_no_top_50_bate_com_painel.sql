-- A métrica mudou de lugar, e não de valor: os trechos que o painel da E3 listava (painel/app.py,
-- "em quantos anos ficaram entre os 50 mais graves") têm, na mart_persistencia_trecho, os
-- mesmos anos_no_top_50 e graves_no_total que o painel calculava sozinho.
-- A consulta abaixo é a do painel, copiada como estava (com o 50 no lugar do parâmetro), sem o
-- LIMIT 20: confere todos os trechos que já ficaram no top, e não só os 20 primeiros.
with painel as (
    with ranking as (
        select br, uf, km_inicio, ano, graves,
               rank() over (partition by ano order by graves desc) as posicao
        from {{ ref('mart_risco_trecho_ano') }} where br <> 0)
    select br, uf, km_inicio, count(*) as anos_no_top, sum(graves) as graves_no_total
    from ranking where posicao <= 50
    group by 1, 2, 3
)

select coalesce(p.br, m.br) as br, coalesce(p.uf, m.uf) as uf, coalesce(p.km_inicio, m.km_inicio) as km_inicio,
       p.anos_no_top, m.anos_no_top_50, p.graves_no_total as graves_painel, m.graves_no_total
from painel p
full join (select * from {{ ref('mart_persistencia_trecho') }} where anos_no_top_50 > 0) m
  on m.br = p.br and m.uf = p.uf and m.km_inicio = p.km_inicio
where p.br is null or m.br is null
   or p.anos_no_top <> m.anos_no_top_50
   or p.graves_no_total <> m.graves_no_total
