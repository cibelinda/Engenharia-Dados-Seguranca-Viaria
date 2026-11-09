-- Causas de cada ocorrência, na versão vigente (view ocorrencia_causa_vigente). Só BAT (2017+).
-- Uma linha por ocorrência por causa. Não há o que limpar: a descrição está em stg_causa.
select id_lote, id, id_causa, causa_principal
from {{ source('origem', 'ocorrencia_causa_vigente') }}
