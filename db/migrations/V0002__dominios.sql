-- Domínios de causa e tipo de acidente.
--
-- São catálogos cumulativos, não versionados por lote: uma descrição que aparece
-- num lote continua existindo quando um lote mais novo a deixa de usar. A carga
-- insere descrições novas conforme as encontra.
--
-- As descrições são guardadas como vêm da PRF. O BAT tem variantes do mesmo
-- conceito (ex.: 'Ingestão de Álcool' e 'Ingestão de álcool pelo condutor'; 91
-- causas distintas em 2017–2025). Harmonizar essas variantes é transformação (E3),
-- não papel da origem.

CREATE TABLE causa_acidente (
    id_causa  smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    descricao text     NOT NULL UNIQUE CHECK (descricao <> '')
);

COMMENT ON TABLE causa_acidente IS
    'Domínio de causa_acidente (causa principal da ocorrência). Catálogo sem carimbo '
    'de tempo: não guarda hora do evento nem da ingestão (a ingestão de cada uso está '
    'no lote da ocorrência). Hora de processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN causa_acidente.descricao IS 'Texto exato do campo causa_acidente da PRF.';


CREATE TABLE tipo_acidente (
    id_tipo   smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    descricao text     NOT NULL UNIQUE CHECK (descricao <> '')
);

COMMENT ON TABLE tipo_acidente IS
    'Domínio de tipo_acidente (no arquivo de ocorrência do BAT, só o tipo de ordem 1). '
    'Catálogo sem carimbo de tempo: não guarda hora do evento nem da ingestão. Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN tipo_acidente.descricao IS 'Texto exato do campo tipo_acidente da PRF.';
