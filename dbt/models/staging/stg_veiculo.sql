-- Veículos, na versão vigente de cada ano (view veiculo_vigente). Uma linha por veículo.
--
-- Limpeza (issue #43), com os nomes de coluna da origem:
--   * tipo_veiculo escrito de um jeito só ('Motocicletas' e 'Motocicleta', 'Caminhão-trator' e
--     'Caminhão-Trator', 'Micro-ônibus' e 'Microônibus'...); 'Não identificado' vira NULL;
--   * ano_fabricacao 1900 e 1901 vira NULL: são 208 veículos, e são o valor de preenchimento
--     (o menor que o esquema aceita), e não carros de 125 anos.
select
    id_lote,
    id,
    id_veiculo,
    case trim(tipo_veiculo)
        when 'Motocicletas'      then 'Motocicleta'
        when 'Caminhão-trator'   then 'Caminhão-Trator'
        when 'Micro-ônibus'      then 'Microônibus'
        when 'Semi-Reboque'      then 'Semireboque'
        when 'Carro-de-mao'      then 'Carro de mão'
        when 'Trator de esteiras' then 'Trator de esteira'
        when 'Motor-Casa'        then 'Motor-casa'
        when 'Trem-bonde'        then 'Bonde / Trem'
        when 'Não identificado'  then null
        else nullif(trim(tipo_veiculo), '')
    end as tipo_veiculo,
    marca,
    case when ano_fabricacao > 1901 then ano_fabricacao end as ano_fabricacao
from {{ source('origem', 'veiculo_vigente') }}
