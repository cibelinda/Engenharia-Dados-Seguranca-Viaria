-- Municípios do IBGE, com o nome "normalizado" (sem acento, sem apóstrofo, maiúsculo, sem
-- pontuação),
-- que é como o nome é comparado com o da PRF.
select
    cod_municipio,
    nome,
    uf,
    trim(regexp_replace(
        regexp_replace(upper(unaccent(replace(nome, '''', ''))), '[^A-Z0-9 ]', ' ', 'g'),
        ' +', ' ', 'g')) as nome_normalizado
from {{ source('ibge', 'municipio') }}
