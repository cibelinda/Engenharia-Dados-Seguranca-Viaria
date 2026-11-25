-- Os graves do perfil são a métrica graves: por trecho, a soma da mart_risco_trecho_ano. Nenhum
-- trecho sobra nem falta.
with risco as (
    select chave_trecho, sum(graves) as graves
    from {{ ref('mart_risco_trecho_ano') }}
    group by chave_trecho
)
select coalesce(m.chave_trecho, r.chave_trecho) as chave_trecho, m.graves as no_perfil, r.graves as no_risco
from {{ ref('mart_perfil_trecho') }} m
full join risco r using (chave_trecho)
where m.graves is distinct from r.graves
