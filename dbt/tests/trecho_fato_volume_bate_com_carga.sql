-- Volume: o fato tem, em cada ano, exatamente as ocorrências que a carga gravou no lote vigente
-- (linhas lidas do datatranAAAA menos as rejeitadas, como a carga registrou em lote_arquivo).
-- Pega o filtro que some com acidentes sem avisar e o join que duplica.
with carga as (
    select l.ano, a.linhas_lidas - a.linhas_rejeitadas as ocorrencias
    from {{ ref('stg_lote') }} l
    join {{ source('origem', 'lote_arquivo') }} a
      on a.id_lote = l.id_lote and a.dataset = 'ocorrencia'
),
fato as (
    select ano, count(*) as ocorrencias from {{ ref('fct_ocorrencia') }} group by ano
)
select c.ano, c.ocorrencias as na_carga, f.ocorrencias as no_fato
from carga c
full join fato f using (ano)
where c.ocorrencias is distinct from f.ocorrencias
