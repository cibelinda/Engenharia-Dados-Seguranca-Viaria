-- Domínio de tipos de acidente (tabela tipo_acidente, sem versão). Uma linha por tipo como a
-- PRF escreveu (31, com variantes só de maiúscula, como 'Colisão Transversal' e 'Colisão
-- transversal'). A descrição fica como veio, para não perder o vínculo com a fonte.
select id_tipo, trim(descricao) as descricao
from {{ source('origem', 'tipo_acidente') }}
