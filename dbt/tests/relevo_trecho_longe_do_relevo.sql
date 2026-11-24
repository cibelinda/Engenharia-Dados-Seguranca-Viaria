-- Um trecho a mais de 5 km do polígono de relevo mais próximo tem coordenada suspeita (no mar,
-- fora do Brasil), e o relevo dele não vale. Avisa, sem parar a esteira.
{{ config(severity='warn') }}
select chave_trecho, tipo_relevo, distancia_m
from {{ ref('dim_trecho_relevo') }}
where distancia_m > 5000
