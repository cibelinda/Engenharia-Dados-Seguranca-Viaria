-- Distribuição: em todo ano, no máximo 0,5% dos acidentes graves ficam sem trecho (br = 0, ou
-- sem br, uf ou km). Medido em 2026-11-09: o pior ano é 2017, com 0,18% (33 de 18.663). Se a
-- PRF passar a publicar a BR zerada ou o km vazio, os graves somem do ranking sem erro nenhum;
-- este teste avisa antes.
select ano,
       count(*) filter (where grave) as graves,
       count(*) filter (where grave and chave_trecho is null) as graves_sem_trecho
from {{ ref('fct_ocorrencia') }}
group by ano
having count(*) filter (where grave and chave_trecho is null)
     > 0.005 * count(*) filter (where grave)
