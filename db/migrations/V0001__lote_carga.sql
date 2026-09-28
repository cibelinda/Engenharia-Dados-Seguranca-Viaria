-- Controle de ingestão. Toda linha de dado carregada pertence a um lote.
--
-- Decisão (docs/modelagem-origem.md; ADR 0001 da issue #6): a origem é insert-only
-- versionada por lote. O lote é o ANO, e não o arquivo, porque veiculo e pessoa
-- (acidentesAAAA.zip) referenciam ocorrencia (datatranAAAA.zip): se cada arquivo
-- fosse um lote, a FK veiculo -> ocorrencia cruzaria versões diferentes do mesmo
-- ano. Os dois arquivos do ano entram juntos, e o detalhe de cada um fica em
-- lote_arquivo.
--
-- A versão vigente de um ano é o maior id_lote com status 'concluido'
-- (views *_vigente, V0008). As linhas de dado nunca recebem UPDATE; só esta
-- tabela de controle muda de status durante a própria carga.

CREATE TABLE lote_carga (
    id_lote       integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ano           smallint    NOT NULL CHECK (ano BETWEEN 2017 AND 2025),
    status        text        NOT NULL DEFAULT 'em_carga'
                              CHECK (status IN ('em_carga', 'concluido', 'falhou')),
    iniciado_em   timestamptz NOT NULL DEFAULT now(),
    finalizado_em timestamptz,

    CONSTRAINT lote_carga_fim_apos_inicio CHECK (finalizado_em >= iniciado_em),
    -- Lote em carga não tem fim; lote concluído ou que falhou tem.
    CONSTRAINT lote_carga_fim_conforme_status
        CHECK ((status = 'em_carga') = (finalizado_em IS NULL)),
    -- Alvo da FK (id_lote, ano) de ocorrencia: garante que o acidente é do ano do lote.
    CONSTRAINT lote_carga_id_ano_uk UNIQUE (id_lote, ano)
);

-- No máximo uma carga em andamento por ano: duas cargas simultâneas do mesmo ano
-- tornariam ambígua a versão vigente.
CREATE UNIQUE INDEX lote_carga_um_em_carga_por_ano
    ON lote_carga (ano) WHERE status = 'em_carga';

COMMENT ON TABLE lote_carga IS
    'Uma execução de carga de um ano do recorte (datatranAAAA + acidentesAAAA). '
    'Guarda a HORA DA INGESTÃO. Hora de processamento não existe nesta etapa (E1): '
    'não há transformação depois da carga.';
COMMENT ON COLUMN lote_carga.ano IS
    'Ano dos arquivos carregados. Um lote novo só é criado quando o SHA-256 de algum '
    'arquivo do ano muda (republicação pela PRF).';
COMMENT ON COLUMN lote_carga.status IS
    'em_carga -> concluido | falhou. Só lotes concluídos entram nas views *_vigente.';
COMMENT ON COLUMN lote_carga.iniciado_em IS
    'Hora da ingestão (início da carga), relógio do banco, com fuso.';
COMMENT ON COLUMN lote_carga.finalizado_em IS
    'Hora da ingestão (fim da carga, com sucesso ou falha). NULL enquanto em_carga.';


CREATE TABLE lote_arquivo (
    id_lote             integer     NOT NULL REFERENCES lote_carga (id_lote),
    dataset             text        NOT NULL CHECK (dataset IN ('ocorrencia', 'pessoa')),
    chave_manifesto     text        NOT NULL,
    arquivo             text        NOT NULL,
    sha256              char(64)    NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    tamanho_bytes       bigint      NOT NULL CHECK (tamanho_bytes > 0),
    drive_last_modified timestamptz,
    linhas_lidas        integer     CHECK (linhas_lidas >= 0),
    linhas_rejeitadas   integer     CHECK (linhas_rejeitadas >= 0),

    PRIMARY KEY (id_lote, dataset),
    CONSTRAINT lote_arquivo_rejeitadas_ate_lidas CHECK (linhas_rejeitadas <= linhas_lidas)
);

COMMENT ON TABLE lote_arquivo IS
    'Arquivo de origem de cada lote (um por dataset). Guarda a HORA DE PUBLICAÇÃO NA '
    'FONTE (drive_last_modified); a hora da ingestão está em lote_carga. Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN lote_arquivo.chave_manifesto IS 'Chave da entrada em sources.yaml (ex.: bat_2024_pessoa).';
COMMENT ON COLUMN lote_arquivo.arquivo IS 'Nome do ZIP da PRF (ex.: acidentes2024.zip).';
COMMENT ON COLUMN lote_arquivo.sha256 IS
    'SHA-256 do ZIP carregado. É a única identificação de versão: nenhum arquivo da PRF '
    'tem coluna de versão, e a PRF regrava arquivos no mesmo ID e nome.';
COMMENT ON COLUMN lote_arquivo.drive_last_modified IS
    'Hora de publicação na fonte: Last-Modified do Google Drive, em UTC. NULL quando '
    'desconhecida (arquivo vindo do cache local sem referência no manifesto).';
COMMENT ON COLUMN lote_arquivo.linhas_lidas IS 'Registros lidos do CSV, sem o cabeçalho. NULL enquanto o lote está em carga.';
COMMENT ON COLUMN lote_arquivo.linhas_rejeitadas IS 'Registros enviados a linha_rejeitada. NULL enquanto o lote está em carga.';
