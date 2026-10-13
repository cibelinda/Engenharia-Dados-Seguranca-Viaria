-- Todas as causas e todos os tipos de cada ocorrência, a partir de
-- acidentesAAAA_todas_causas_tipos.zip (só BAT, 2017+), ADR 0003.
--
-- O arquivo tem uma linha por pessoa x causa x tipo e repete o acidente e a pessoa em
-- cada uma. Medido em 2024 (603.839 linhas, 73.202 ocorrências): o conjunto de causas
-- e o de tipos são os mesmos para todas as pessoas da ocorrência, cada ocorrência tem
-- exatamente uma causa principal, e a causa principal e o tipo de ordem 1 são iguais
-- aos do datatranAAAA em 100% das ocorrências. Portanto o conteúdo novo do arquivo é de
-- nível de OCORRÊNCIA, e é só isso que entra: ocorrencia_causa e ocorrencia_tipo. As
-- pessoas e os veículos já vêm de acidentesAAAA.zip.
--
-- O BR-Brasil não publica esse arquivo: as ocorrências de 2007–2016 têm só a causa e o
-- tipo da tabela ocorrencia.

CREATE TABLE ocorrencia_causa (
    id_lote         integer  NOT NULL,
    id              bigint   NOT NULL,
    id_causa        smallint NOT NULL REFERENCES causa_acidente (id_causa),
    causa_principal boolean  NOT NULL,

    PRIMARY KEY (id_lote, id, id_causa),
    FOREIGN KEY (id_lote, id) REFERENCES ocorrencia (id_lote, id)
);

-- No máximo uma causa principal por ocorrência (medido: exatamente uma).
CREATE UNIQUE INDEX ocorrencia_causa_uma_principal ON ocorrencia_causa (id_lote, id) WHERE causa_principal;

COMMENT ON TABLE ocorrencia_causa IS
    'Cada causa apontada pela PRF para uma ocorrência do BAT, numa versão (lote). Não guarda hora '
    'do evento (é a da ocorrência). HORA DA INGESTÃO via id_lote -> lote_carga. Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN ocorrencia_causa.causa_principal IS
    'Campo causa_principal (Sim/Não). A principal é a mesma de ocorrencia.id_causa.';


CREATE TABLE ocorrencia_tipo (
    id_lote integer  NOT NULL,
    id      bigint   NOT NULL,
    ordem   smallint NOT NULL CHECK (ordem >= 1),
    id_tipo smallint NOT NULL REFERENCES tipo_acidente (id_tipo),

    PRIMARY KEY (id_lote, id, ordem),
    FOREIGN KEY (id_lote, id) REFERENCES ocorrencia (id_lote, id)
);

COMMENT ON TABLE ocorrencia_tipo IS
    'Sequência de tipos de acidente de uma ocorrência do BAT (ex.: 1 saída de pista, 2 capotamento), '
    'numa versão (lote). Não guarda hora do evento (é a da ocorrência). HORA DA INGESTÃO via '
    'id_lote -> lote_carga. Hora de processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN ocorrencia_tipo.ordem IS
    'Campo ordem_tipo_acidente. O tipo de ordem 1 é o mesmo de ocorrencia.id_tipo.';
