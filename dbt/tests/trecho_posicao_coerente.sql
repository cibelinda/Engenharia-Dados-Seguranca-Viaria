-- Coerência do ranking, em cada ano:
--   * a posição 1 é o trecho com mais graves;
--   * trecho sem grave não tem posição, e trecho com grave tem;
--   * quem tem mais graves nunca fica atrás de quem tem menos;
--   * empate no número de graves é empate na posição.
-- Pega um rank particionado ou ordenado errado.
with m as (
    select chave_trecho, ano, graves, posicao,
           max(graves) over (partition by ano) as max_graves,
           lag(posicao) over (partition by ano order by graves desc, posicao) as posicao_anterior,
           min(posicao) over (partition by ano, graves) as menor_no_empate,
           max(posicao) over (partition by ano, graves) as maior_no_empate
    from {{ ref('mart_risco_trecho_ano') }}
)
select chave_trecho, ano, graves, posicao
from m
where (posicao = 1 and graves <> max_graves)
   or (graves > 0) <> (posicao is not null)
   or posicao < posicao_anterior
   or menor_no_empate <> maior_no_empate
