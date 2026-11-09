-- Tipos de cada ocorrência, na versão vigente (view ocorrencia_tipo_vigente). Só BAT (2017+).
-- Uma linha por ocorrência por ordem. Não há o que limpar: a descrição está em stg_tipo.
select id_lote, id, ordem, id_tipo
from {{ source('origem', 'ocorrencia_tipo_vigente') }}
