-- Pessoa envolvida, a partir das linhas de acidentesAAAA.zip com pesid <> 0.
--
-- pesid é único no recorte inteiro, então a PK é (id_lote, pesid). Os atributos do
-- acidente repetidos no arquivo (data, br, km, causa...) ficam só em ocorrencia:
-- conferem com ela em 100% das linhas. As binárias ilesos/feridos_leves/
-- feridos_graves/mortos também ficam fora: são o estado_fisico codificado (100%
-- das linhas).
--
-- Duas FKs, e nenhuma é redundante:
--   (id_lote, id)             -> ocorrencia  sempre vale, inclusive para pedestre,
--                                            testemunha e cavaleiro, que não têm veículo;
--   (id_lote, id, id_veiculo) -> veiculo     vale quando há veículo. Com id_veiculo NULL,
--                                            a FK (MATCH SIMPLE) não é verificada.

CREATE TABLE pessoa (
    id_lote        integer  NOT NULL,
    pesid          bigint   NOT NULL CHECK (pesid > 0),
    id             bigint   NOT NULL,
    id_veiculo     bigint,
    tipo_envolvido text     NOT NULL CHECK (tipo_envolvido IN (
                       'Condutor', 'Passageiro', 'Pedestre', 'Testemunha', 'Cavaleiro')),
    estado_fisico  text     NOT NULL CHECK (estado_fisico IN (
                       'Ileso', 'Lesões Leves', 'Lesões Graves', 'Óbito', 'Não Informado')),
    idade          smallint CHECK (idade >= 0),
    sexo           text     NOT NULL CHECK (sexo <> ''),

    PRIMARY KEY (id_lote, pesid),
    FOREIGN KEY (id_lote, id) REFERENCES ocorrencia (id_lote, id),
    FOREIGN KEY (id_lote, id, id_veiculo) REFERENCES veiculo (id_lote, id, id_veiculo),
    -- No recorte, id_veiculo = 0 ocorre exatamente para esses três tipos de envolvido.
    CONSTRAINT pessoa_sem_veiculo_conforme_envolvido
        CHECK ((id_veiculo IS NULL) = (tipo_envolvido IN ('Pedestre', 'Testemunha', 'Cavaleiro')))
);

-- Serve às duas FKs (prefixo id_lote, id) e ao join pessoa -> veiculo.
CREATE INDEX pessoa_ocorrencia_veiculo_idx ON pessoa (id_lote, id, id_veiculo);

COMMENT ON TABLE pessoa IS
    'Pessoa envolvida numa ocorrência, numa versão (lote). Não guarda hora do evento '
    '(é a da ocorrência). HORA DA INGESTÃO via id_lote -> lote_carga. Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN pessoa.id_lote IS
    'Lote que carregou esta versão da linha. A hora da ingestão está em lote_carga.iniciado_em/finalizado_em.';
COMMENT ON COLUMN pessoa.pesid IS 'Identificador da pessoa na PRF. Sequência global no recorte; 0 na fonte é veículo sem pessoa e não entra aqui.';
COMMENT ON COLUMN pessoa.id_veiculo IS 'Veículo da pessoa. NULL para pedestre, testemunha e cavaleiro (0 na fonte).';
COMMENT ON COLUMN pessoa.estado_fisico IS
    'Estado físico. Substitui as binárias ilesos/feridos_leves/feridos_graves/mortos da fonte, que o codificam.';
COMMENT ON COLUMN pessoa.idade IS
    'Idade informada. NULL = desconhecida. A fonte tem 0 em 147.311 pessoas e valores acima de 110 '
    '(ex.: 906, 2016) em 2.449; o tratamento desses valores é da carga (issue #4).';
