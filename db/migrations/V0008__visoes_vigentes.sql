-- Versão vigente: para cada ano, o maior lote concluído. As consultas da pergunta de
-- gestão usam estas views; as tabelas guardam todas as versões.

CREATE VIEW lote_vigente AS
SELECT DISTINCT ON (ano) id_lote, ano, iniciado_em, finalizado_em
FROM lote_carga
WHERE status = 'concluido'
ORDER BY ano, id_lote DESC;

COMMENT ON VIEW lote_vigente IS
    'Lote vigente de cada ano: o maior id_lote com status concluido. Carimbos: hora da '
    'ingestão (iniciado_em, finalizado_em). Hora de processamento não existe nesta etapa (E1).';

CREATE VIEW ocorrencia_vigente AS
SELECT o.* FROM ocorrencia o JOIN lote_vigente v USING (id_lote);

CREATE VIEW veiculo_vigente AS
SELECT ve.* FROM veiculo ve JOIN lote_vigente v USING (id_lote);

CREATE VIEW pessoa_vigente AS
SELECT p.* FROM pessoa p JOIN lote_vigente v USING (id_lote);

COMMENT ON VIEW ocorrencia_vigente IS 'Ocorrências da versão vigente de cada ano. Mesmos carimbos de ocorrencia.';
COMMENT ON VIEW veiculo_vigente    IS 'Veículos da versão vigente de cada ano. Mesmos carimbos de veiculo.';
COMMENT ON VIEW pessoa_vigente     IS 'Pessoas da versão vigente de cada ano. Mesmos carimbos de pessoa.';
