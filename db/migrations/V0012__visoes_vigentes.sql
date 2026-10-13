-- Views de versão vigente para o dataset completo.
--
-- Em PostgreSQL, o `o.*` de uma view é expandido quando ela é criada: as colunas novas
-- de V0009 (ocorrencia.geom), V0010 (lote_carga.sistema, pessoa.nacionalidade e
-- naturalidade) só aparecem recriando as views. CREATE OR REPLACE acrescenta as colunas
-- no fim, sem mudar as existentes.

CREATE OR REPLACE VIEW lote_vigente AS
SELECT DISTINCT ON (ano) id_lote, ano, iniciado_em, finalizado_em, sistema
FROM lote_carga
WHERE status = 'concluido'
ORDER BY ano, id_lote DESC;

CREATE OR REPLACE VIEW ocorrencia_vigente AS
SELECT o.* FROM ocorrencia o JOIN lote_vigente v USING (id_lote);

CREATE OR REPLACE VIEW pessoa_vigente AS
SELECT p.* FROM pessoa p JOIN lote_vigente v USING (id_lote);

CREATE VIEW ocorrencia_causa_vigente AS
SELECT c.* FROM ocorrencia_causa c JOIN lote_vigente v USING (id_lote);

CREATE VIEW ocorrencia_tipo_vigente AS
SELECT t.* FROM ocorrencia_tipo t JOIN lote_vigente v USING (id_lote);

COMMENT ON VIEW lote_vigente IS
    'Lote vigente de cada ano: o maior id_lote com status concluido, com o sistema de origem. '
    'Carimbos: hora da ingestão (iniciado_em, finalizado_em). Hora de processamento não existe nesta etapa (E1).';
COMMENT ON VIEW ocorrencia_causa_vigente IS 'Causas das ocorrências da versão vigente de cada ano (BAT). Mesmos carimbos de ocorrencia_causa.';
COMMENT ON VIEW ocorrencia_tipo_vigente  IS 'Tipos das ocorrências da versão vigente de cada ano (BAT). Mesmos carimbos de ocorrencia_tipo.';
