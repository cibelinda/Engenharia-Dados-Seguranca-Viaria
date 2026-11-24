-- Volume (issue #57): o mapa tem, ano a ano, exatamente os acidentes graves com coordenada
-- confiável do fato. Falha com os anos em que os números diferem.
with fato as (
    select ano, count(*) as n from {{ ref('fct_ocorrencia') }}
    where grave and coordenada_confiavel group by ano
),
mapa as (
    select ano, count(*) as n from {{ ref('mapa_acidente_grave') }} group by ano
)
select coalesce(f.ano, m.ano) as ano, f.n as no_fato, m.n as no_mapa
from fato f full join mapa m using (ano)
where f.n is distinct from m.n
