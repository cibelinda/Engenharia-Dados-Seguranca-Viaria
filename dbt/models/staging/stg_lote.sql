-- Lote vigente de cada ano (view lote_vigente). Uma linha por ano.
-- Não há o que limpar: é a tabela de controle da carga. As colunas ficam explícitas para que
-- uma coluna nova na origem não apareça aqui sem passar por este arquivo.
select id_lote, ano, sistema, iniciado_em, finalizado_em
from {{ source('origem', 'lote_vigente') }}
