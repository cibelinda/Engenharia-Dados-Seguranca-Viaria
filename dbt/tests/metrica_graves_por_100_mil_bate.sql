-- A taxa da mart_risco_municipio_ano é a fórmula da métrica graves_por_100_mil (camada
-- semântica: graves * 100000 / populacao), com duas casas, em cada município e ano. Pega a
-- taxa calculada com outra escala (por mil, por 10 mil), com a população de outro ano ou sem
-- arredondar do mesmo jeito.
select cod_municipio, ano, graves, populacao, graves_por_100_mil,
       round(graves * 100000.0 / nullif(populacao, 0), 2) as pela_formula
from {{ ref('mart_risco_municipio_ano') }}
where graves_por_100_mil is distinct from round(graves * 100000.0 / nullif(populacao, 0), 2)
