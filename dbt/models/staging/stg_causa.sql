-- Domínio de causas de acidente (tabela causa_acidente, sem versão). Uma linha por causa como a
-- PRF escreveu: são 101, com variantes da mesma causa ('Ingestão de álcool', 'Ingestão de
-- Álcool', 'Ingestão de álcool pelo condutor'). A descrição fica como veio, para não perder o
-- vínculo com a fonte; quem junta as variantes é a dim_causa (marts/trecho).
select id_causa, trim(descricao) as descricao
from {{ source('origem', 'causa_acidente') }}
