-- Polígonos de relevo do IBGE com os nomes de coluna do projeto. Um polígono por linha.
--
-- tipo_relevo é o compartimento do IBGE (Planícies, Planaltos, Serras, Depressões,
-- Tabuleiros, Chapadas, Patamares), sem tradução, para bater com o mapa do IBGE.
-- Os polígonos de água ("Corpo d'água continental") ficam aqui e saem na dim_trecho_relevo:
-- a rodovia passa por eles em pontes, mas não tem relevo.
select
    id1                as id_modelado,
    compartimento      as tipo_relevo,
    nm_unidade         as unidade_relevo,
    nm_regiao          as regiao_relevo,
    nm_dominio         as dominio_relevo,
    natureza           as natureza_modelado,
    compartimento = 'Corpo d''água continental' as agua,
    geom
from {{ source('relevo', 'modelado') }}
