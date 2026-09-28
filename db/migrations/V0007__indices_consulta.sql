-- Índices para as consultas da pergunta de gestão (docs/pergunta-e-recorte.md):
-- trechos de 10 km (br + uf + faixa de km) com acidentes com morto ou ferido grave,
-- por ano, só na versão vigente de cada ano.
--
-- Os índices de FK já existem: as PKs de ocorrencia e veiculo começam por
-- (id_lote, id), e pessoa tem pessoa_ocorrencia_veiculo_idx (V0005).

-- Ranking de trechos graves por ano:
--   SELECT br, uf, floor(km / 10), ano, count(*) FROM ocorrencia_vigente
--   WHERE mortos > 0 OR feridos_graves > 0 GROUP BY 1, 2, 3, 4
-- Parcial: guarda só as ocorrências graves. Começa por id_lote porque "vigente" é um
-- filtro por lote, e depois vem na ordem do agrupamento. O INCLUDE (ano) permite
-- responder só com o índice. Com o volume inteiro, o planejador ainda pode preferir
-- varrer a tabela; o plano real será medido com dado carregado (issue #4, semana 10).
CREATE INDEX ocorrencia_grave_trecho_idx
    ON ocorrencia (id_lote, br, uf, km) INCLUDE (ano)
    WHERE mortos > 0 OR feridos_graves > 0;

-- Detalhe de um trecho, com qualquer gravidade:
--   SELECT ... FROM ocorrencia_vigente WHERE br = 116 AND uf = 'PR' AND km >= 10 AND km < 20
-- Igualdade em br e uf e intervalo em km, nessa ordem.
CREATE INDEX ocorrencia_trecho_idx ON ocorrencia (br, uf, km);
