-- Ocorrências, na versão vigente de cada ano (view ocorrencia_vigente). Uma linha por acidente.
--
-- Limpeza (issue #43). Os nomes das colunas são os da origem, porque as outras partes dependem
-- deles, e as colunas que a parte do IBGE usa (id_lote, id, ano, uf, municipio, geom, mortos,
-- feridos_graves) passam sem mudança de valor. O que muda:
--   * vocabulário do BR-Brasil (2007–2016) e do BAT (2017+) num só: 'Ceu Claro' e 'Céu Claro',
--     'Plena Noite' e 'Plena noite', 'Nevoeiro/neblina' e 'Nevoeiro/Neblina';
--   * "não sei" vira NULL, e não um valor: 'Ignorado'/'Ignorada' na condição meteorológica e na
--     classificação, 'Não Informado' no sentido da via;
--   * texto livre sem espaços nas pontas.
-- A origem guarda o que a PRF publicou (docs/modelagem-origem.md); a harmonização é daqui.
select
    id_lote,
    id,
    ocorrido_em,
    ano,
    uf,
    br,
    km,
    municipio,
    latitude,
    longitude,
    id_causa,
    id_tipo,
    nullif(classificacao_acidente, 'Ignorado') as classificacao_acidente,
    case trim(fase_dia)
        when 'Plena Noite' then 'Plena noite'
        else nullif(trim(fase_dia), '')
    end as fase_dia,
    nullif(trim(sentido_via), 'Não Informado') as sentido_via,
    case trim(condicao_meteorologica)
        when 'Ceu Claro'        then 'Céu Claro'
        when 'Nevoeiro/neblina' then 'Nevoeiro/Neblina'
        when 'Ignorado'         then null
        when 'Ignorada'         then null
        when ''                 then null
        else trim(condicao_meteorologica)
    end as condicao_meteorologica,
    nullif(trim(tipo_pista), '') as tipo_pista,
    tracado_via,
    uso_solo_urbano,
    pessoas,
    mortos,
    feridos_leves,
    feridos_graves,
    feridos,
    ilesos,
    ignorados,
    veiculos,
    nullif(trim(regional), '') as regional,
    nullif(trim(delegacia), '') as delegacia,
    nullif(trim(uop), '') as uop,
    geom
from {{ source('origem', 'ocorrencia_vigente') }}
