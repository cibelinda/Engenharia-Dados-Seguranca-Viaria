-- Veículo envolvido, a partir das linhas de acidentesAAAA.zip com id_veiculo <> 0.
--
-- O arquivo "pessoa" mistura duas entidades: pesid = 0 é veículo sem pessoa
-- (144.628 linhas, sobretudo reboques e semirreboques) e id_veiculo = 0 é pessoa
-- sem veículo (60.890 pedestres, testemunhas e cavaleiros). Uma linha de veículo
-- entra aqui uma vez, ainda que se repita em várias linhas de pessoa: os atributos
-- de veículo são 100% consistentes entre as linhas do mesmo (id, id_veiculo).
--
-- PK composta (id_lote, id, id_veiculo), embora id_veiculo seja global no recorte
-- (nenhum id_veiculo <> 0 aparece em duas ocorrências): é o alvo da FK composta de
-- pessoa, que garante que a pessoa e o veículo dela são da mesma ocorrência. O
-- UNIQUE (id_lote, id_veiculo) registra a unicidade global verificada; se a PRF a
-- quebrar, a carga rejeita a linha em vez de aceitar um veículo ambíguo.

CREATE TABLE veiculo (
    id_lote        integer  NOT NULL,
    id             bigint   NOT NULL,
    id_veiculo     bigint   NOT NULL CHECK (id_veiculo > 0),
    tipo_veiculo   text     NOT NULL CHECK (tipo_veiculo <> ''),
    marca          text     NOT NULL CHECK (marca <> ''),
    ano_fabricacao smallint CHECK (ano_fabricacao >= 1900),

    PRIMARY KEY (id_lote, id, id_veiculo),
    CONSTRAINT veiculo_id_veiculo_global_uk UNIQUE (id_lote, id_veiculo),
    FOREIGN KEY (id_lote, id) REFERENCES ocorrencia (id_lote, id)
);

COMMENT ON TABLE veiculo IS
    'Veículo envolvido numa ocorrência, numa versão (lote). Não guarda hora do evento '
    '(é a da ocorrência). HORA DA INGESTÃO via id_lote -> lote_carga. Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN veiculo.id_lote IS
    'Lote que carregou esta versão da linha. A hora da ingestão está em lote_carga.iniciado_em/finalizado_em.';
COMMENT ON COLUMN veiculo.id_veiculo IS
    'Identificador do veículo na PRF. Sequência global no recorte; 0 na fonte significa "sem veículo" e não entra aqui.';
COMMENT ON COLUMN veiculo.marca IS 'Marca/modelo como vem da PRF. "Não Informado/Não Informado" em 46.933 linhas de origem.';
COMMENT ON COLUMN veiculo.ano_fabricacao IS
    'Campo ano_fabricacao_veiculo. NULL = desconhecido: a fonte usa 0 em 147.201 linhas (conversão na carga, issue #4).';
