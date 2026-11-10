-- Limpeza da dim_causa: duas descrições da PRF que só diferem em maiúscula ou acento são a
-- mesma causa e têm de ficar com o mesmo valor em `causa`. Falha quando a PRF publica uma
-- variante nova ('Velocidade incompatível' e 'Velocidade Incompatível') que ninguém juntou.
with normalizada as (
    select id_causa, descricao, causa, lower(unaccent(causa)) as chave
    from {{ ref('dim_causa') }}
)
select chave, array_agg(distinct causa) as causas
from normalizada
group by chave
having count(distinct causa) > 1
