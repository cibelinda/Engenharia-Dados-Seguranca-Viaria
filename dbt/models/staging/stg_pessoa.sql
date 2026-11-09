-- Pessoas, na versão vigente de cada ano (view pessoa_vigente). Uma linha por pessoa envolvida.
--
-- Limpeza (issue #43), com os nomes de coluna da origem:
--   * estado_fisico no vocabulário do BAT: o BR-Brasil escreve 'Morto', 'Ferido Grave' e
--     'Ferido Leve' para 'Óbito', 'Lesões Graves' e 'Lesões Leves';
--   * sexo só 'Masculino' ou 'Feminino': 'M' e 'F' são a mesma coisa abreviada, e 'Não
--     Informado', 'Inválido', 'Ignorado' e 'I' viram NULL;
--   * "não sei" vira NULL também no estado físico ('Ignorado', 'Não Informado').
select
    id_lote,
    pesid,
    id,
    id_veiculo,
    tipo_envolvido,
    case estado_fisico
        when 'Morto'        then 'Óbito'
        when 'Ferido Grave' then 'Lesões Graves'
        when 'Ferido Leve'  then 'Lesões Leves'
        when 'Ignorado'      then null
        when 'Não Informado' then null
        else estado_fisico
    end as estado_fisico,
    idade,
    case sexo
        when 'M' then 'Masculino'
        when 'F' then 'Feminino'
        when 'Masculino' then 'Masculino'
        when 'Feminino'  then 'Feminino'
    end as sexo,
    nacionalidade,
    naturalidade
from {{ source('origem', 'pessoa_vigente') }}
