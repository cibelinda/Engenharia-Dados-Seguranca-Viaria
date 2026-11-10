-- Distribuição do km: os acidentes em trecho isolado (km_isolado, provável km digitado errado)
-- são no máximo 0,1% dos acidentes com trecho. Medido em 2026-11-09: 495 em 2,2 milhões
-- (338 trechos). Se a carga passar a ler o km com a vírgula no lugar errado (km 2005 em vez de
-- 200,5), esse número explode e o teste falha antes de o ranking ganhar trechos que não existem.
select count(*) filter (where t.km_isolado) as em_trecho_isolado, count(*) as com_trecho
from {{ ref('fct_ocorrencia') }} f
join {{ ref('dim_trecho') }} t using (chave_trecho)
having count(*) filter (where t.km_isolado) > 0.001 * count(*)
