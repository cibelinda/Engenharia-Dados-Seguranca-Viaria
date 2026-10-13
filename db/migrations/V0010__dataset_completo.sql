-- Dataset completo da PRF: BR-Brasil (2007–2016) e BAT (2017 em diante), ADR 0003.
--
-- O esquema da E1 foi fechado no recorte BAT 2017–2025. Esta migração abre o esquema
-- para os 20 anos publicados, sem mudar as chaves:
--
-- * Os 490.283 IDs que colidem entre BR-Brasil e BAT não colidem aqui. O lote é o ano,
--   cada ano pertence a um único sistema, e toda PK de dado começa por id_lote. O
--   sistema de origem fica registrado no lote (lote_carga.sistema).
-- * As diferenças de formato (separador, datas, decimal, '(null)') são resolvidas na
--   carga (blackspot/load.py). Aqui entram só as diferenças de CONTEÚDO, medidas nos
--   arquivos em 2026-10-12 (docs/modelagem-origem.md, "Dataset completo"):
--     - BR-Brasil traz '(null)' em uf/br/km (12 ocorrências), causa (2), fase do dia
--       (69), condição meteorológica (58), tipo de pista, traçado e uso do solo (10):
--       as ocorrências entram, com NULL, porque trazem contagens de mortos e feridos;
--     - km negativo em 19 ocorrências do BR-Brasil (ex.: -687,4): a carga grava NULL;
--     - classificacao_acidente tem o valor 'Ignorado' (11.660 ocorrências);
--     - pessoa usa outro vocabulário (estado_fisico 'Morto', 'Ferido Grave'...;
--       tipo_envolvido 'Vítima', 'Autor'...) e traz nacionalidade e naturalidade;
--     - a regra "sem veículo <=> pedestre, testemunha ou cavaleiro" não vale no
--       BR-Brasil (53 passageiros e 38 condutores sem veículo; 17 pedestres com veículo).
--       Ela continua verificada na carga para o BAT.
--
-- Os vocabulários NÃO são harmonizados na origem ('Morto' x 'Óbito', 'Ceu Claro' x
-- 'Céu Claro'): a origem guarda o que a PRF publicou, e a harmonização é transformação (E3).

-- --- lote --------------------------------------------------------------------------

ALTER TABLE lote_carga DROP CONSTRAINT lote_carga_ano_check;
ALTER TABLE lote_carga ADD CONSTRAINT lote_carga_ano_check CHECK (ano >= 2007);

-- O sistema é função do ano (dicionário da PRF): BR-Brasil até 2016, BAT a partir de 2017.
ALTER TABLE lote_carga ADD COLUMN sistema text NOT NULL
    GENERATED ALWAYS AS (CASE WHEN ano <= 2016 THEN 'br_brasil' ELSE 'bat' END) STORED;

COMMENT ON COLUMN lote_carga.ano IS
    'Ano dos arquivos carregados (2007 em diante; o ano corrente é parcial e regravado todo mês). '
    'Um lote novo só é criado quando o SHA-256 de algum arquivo do ano muda (republicação pela PRF).';
COMMENT ON COLUMN lote_carga.sistema IS
    'Sistema de registro da PRF que produziu o ano: br_brasil (2007–2016) ou bat (2017+). '
    'Os IDs de ocorrência, pessoa e veículo só são únicos dentro de um sistema.';
COMMENT ON TABLE lote_carga IS
    'Uma execução de carga de um ano da PRF (datatranAAAA + acidentesAAAA e, no BAT, '
    'acidentesAAAA_todas_causas_tipos). Guarda a HORA DA INGESTÃO. Hora de processamento não '
    'existe nesta etapa (E1): não há transformação depois da carga.';

ALTER TABLE lote_arquivo DROP CONSTRAINT lote_arquivo_dataset_check;
ALTER TABLE lote_arquivo ADD CONSTRAINT lote_arquivo_dataset_check
    CHECK (dataset IN ('ocorrencia', 'pessoa', 'pessoa_todas_causas'));

-- --- ocorrência ----------------------------------------------------------------------

ALTER TABLE ocorrencia DROP CONSTRAINT ocorrencia_ano_do_recorte;
ALTER TABLE ocorrencia ADD CONSTRAINT ocorrencia_ano_da_fonte CHECK (ano >= 2007);

ALTER TABLE ocorrencia
    ALTER COLUMN uf                     DROP NOT NULL,
    ALTER COLUMN br                     DROP NOT NULL,
    ALTER COLUMN km                     DROP NOT NULL,
    ALTER COLUMN id_causa               DROP NOT NULL,
    ALTER COLUMN fase_dia               DROP NOT NULL,
    ALTER COLUMN sentido_via            DROP NOT NULL,
    ALTER COLUMN condicao_meteorologica DROP NOT NULL,
    ALTER COLUMN tipo_pista             DROP NOT NULL,
    ALTER COLUMN tracado_via            DROP NOT NULL,
    ALTER COLUMN uso_solo_urbano        DROP NOT NULL;

ALTER TABLE ocorrencia DROP CONSTRAINT ocorrencia_classificacao_acidente_check;
ALTER TABLE ocorrencia ADD CONSTRAINT ocorrencia_classificacao_acidente_check
    CHECK (classificacao_acidente IN (
        'Sem Vítimas', 'Com Vítimas Feridas', 'Com Vítimas Fatais', 'Ignorado'));

COMMENT ON TABLE ocorrencia IS
    'Um acidente registrado pela PRF (BR-Brasil ou BAT, conforme o lote), numa versão (lote). '
    'Insert-only: uma revisão da PRF gera linhas novas em outro lote. Carimbos: HORA DO EVENTO em '
    'ocorrido_em; HORA DA INGESTÃO via id_lote -> lote_carga. Hora de processamento não existe '
    'nesta etapa (E1).';
COMMENT ON COLUMN ocorrencia.id IS
    'Identificador do acidente na PRF. Único dentro de cada sistema (lote_carga.sistema); 490.283 '
    'IDs se repetem entre BR-Brasil e BAT, o que não colide aqui porque a PK começa por id_lote.';
COMMENT ON COLUMN ocorrencia.uf IS 'UF da ocorrência. NULL quando a PRF publica (null) (12 ocorrências do BR-Brasil).';
COMMENT ON COLUMN ocorrencia.br IS
    'Número da BR. 0 = rodovia não identificada (mantido como vem da PRF); NULL quando a PRF publica (null).';
COMMENT ON COLUMN ocorrencia.km IS
    'Quilômetro da BR, uma casa decimal. Com br e uf, define o trecho da pergunta de gestão. NULL '
    'quando a PRF publica (null) ou um km negativo (BR-Brasil).';
COMMENT ON COLUMN ocorrencia.latitude IS
    'Coordenada informada pela PRF; só existe no BAT (2017+). NULL no BR-Brasil e quando o par está '
    'fora do limite válido (33 ocorrências de 2017). Dentro do limite, sem correção na origem.';
COMMENT ON COLUMN ocorrencia.id_causa IS 'Causa principal. NULL quando a PRF publica (null) (2 ocorrências do BR-Brasil).';
COMMENT ON COLUMN ocorrencia.classificacao_acidente IS
    'Como a PRF publica. ''Ignorado'' só no BR-Brasil. NULL quando a PRF informa NA ou (null).';
COMMENT ON COLUMN ocorrencia.uso_solo_urbano IS
    'Campo uso_solo da PRF: Sim/Urbano = urbano, Não/Rural = rural (o BR-Brasil usa Urbano/Rural).';
COMMENT ON COLUMN ocorrencia.mortos IS
    'Contagem informada pela PRF. Confere com as pessoas em Óbito (BAT) ou Morto (BR-Brasil) em 100% do '
    'BAT e em todas as ocorrências do BR-Brasil menos 8, que perderam pessoas para linha_rejeitada.';
COMMENT ON COLUMN ocorrencia.feridos_graves IS
    'Contagem informada pela PRF. Confere com as pessoas em Lesões Graves (BAT) ou Ferido Grave (BR-Brasil) '
    'em 100% do BAT e em todas as ocorrências do BR-Brasil menos 19 (pessoas rejeitadas).';
COMMENT ON COLUMN ocorrencia.regional IS 'Superintendência da PRF (não é a UF). Só no BAT; NULL quando NA ou N/A.';

-- --- veículo -------------------------------------------------------------------------

ALTER TABLE veiculo
    ALTER COLUMN tipo_veiculo DROP NOT NULL,
    ALTER COLUMN marca        DROP NOT NULL;

COMMENT ON COLUMN veiculo.tipo_veiculo IS 'Tipo do veículo como vem da PRF. NULL quando a PRF publica (null) ou vazio (BR-Brasil).';
COMMENT ON COLUMN veiculo.marca IS
    'Marca/modelo como vem da PRF, sem os espaços de preenchimento do BR-Brasil. NULL quando (null) ou vazio.';

-- --- pessoa --------------------------------------------------------------------------

ALTER TABLE pessoa DROP CONSTRAINT pessoa_sem_veiculo_conforme_envolvido;

ALTER TABLE pessoa DROP CONSTRAINT pessoa_tipo_envolvido_check;
ALTER TABLE pessoa ADD CONSTRAINT pessoa_tipo_envolvido_check CHECK (tipo_envolvido IN (
    'Condutor', 'Passageiro', 'Pedestre', 'Testemunha', 'Cavaleiro',                        -- BAT e BR-Brasil
    'Vítima', 'Autor', 'Ciclista', 'Proprietário de Carga', 'Proprietário da CNH'));        -- só BR-Brasil

ALTER TABLE pessoa ALTER COLUMN estado_fisico DROP NOT NULL;
ALTER TABLE pessoa DROP CONSTRAINT pessoa_estado_fisico_check;
ALTER TABLE pessoa ADD CONSTRAINT pessoa_estado_fisico_check CHECK (estado_fisico IN (
    'Ileso', 'Lesões Leves', 'Lesões Graves', 'Óbito', 'Não Informado',                    -- BAT
    'Ferido Leve', 'Ferido Grave', 'Morto', 'Ignorado'));                                   -- BR-Brasil

ALTER TABLE pessoa ALTER COLUMN sexo DROP NOT NULL;

ALTER TABLE pessoa
    ADD COLUMN nacionalidade text CHECK (nacionalidade <> ''),
    ADD COLUMN naturalidade  text CHECK (naturalidade <> '');

COMMENT ON TABLE pessoa IS
    'Pessoa envolvida numa ocorrência, numa versão (lote). Não guarda hora do evento '
    '(é a da ocorrência). HORA DA INGESTÃO via id_lote -> lote_carga. Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN pessoa.id_veiculo IS
    'Veículo da pessoa. NULL quando a pessoa não está num veículo: 0 na fonte (BAT) ou (null)/NA (BR-Brasil).';
COMMENT ON COLUMN pessoa.tipo_envolvido IS
    'Como a PRF publica. No BAT, sem veículo <=> Pedestre, Testemunha ou Cavaleiro (verificado na carga); '
    'no BR-Brasil essa regra não vale.';
COMMENT ON COLUMN pessoa.estado_fisico IS
    'Estado físico no vocabulário do sistema de origem: BAT (Óbito, Lesões Graves...) ou BR-Brasil '
    '(Morto, Ferido Grave...). Sem harmonização na origem. NULL quando a PRF publica (null).';
COMMENT ON COLUMN pessoa.sexo IS 'Como a PRF publica (Masculino, M, Inválido...). NULL quando vazio, NA ou (null).';
COMMENT ON COLUMN pessoa.nacionalidade IS 'Só no BR-Brasil (o BAT não publica). NULL quando ausente.';
COMMENT ON COLUMN pessoa.naturalidade IS 'Só no BR-Brasil (o BAT não publica). NULL quando ausente.';
