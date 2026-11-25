-- O critério de ponto negro mora num lugar só (macro metrica_ponto_negro). A coluna ponto_negro da
-- mart_persistencia_trecho é a regra do contrato da #58 escrita à mão: 3 ou mais anos com
-- posicao <= 50, trecho a trecho.
with regra as (
    select chave_trecho, count(*) filter (where posicao <= 50) >= 3 as ponto_negro
    from {{ ref('mart_risco_trecho_ano') }}
    group by chave_trecho
)
select coalesce(p.chave_trecho, r.chave_trecho) as chave_trecho, p.ponto_negro as no_mart, r.ponto_negro as na_regra
from {{ ref('mart_persistencia_trecho') }} p
full join regra r using (chave_trecho)
where p.ponto_negro is distinct from r.ponto_negro
