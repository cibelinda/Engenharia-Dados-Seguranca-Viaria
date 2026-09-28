-- Ocorrência (acidente), a partir de datatranAAAA.zip.
--
-- Nulabilidade conferida nos 632.713 registros do recorte (BAT 2017–2025):
-- só tipo_acidente (41 vazios), classificacao_acidente (10 'NA') e
-- regional/delegacia/uop ('NA' ou 'N/A') têm ausência. O resto é NOT NULL.
--
-- Fora do esquema por serem deriváveis: dia_semana (de ocorrido_em) e ano (coluna
-- gerada). As contagens (mortos, feridos_graves...) ficam, apesar de mortos e
-- feridos_graves baterem 100% com a soma de pessoa: são o que a pergunta de gestão
-- filtra, e recalculá-las exigiria agregar 1,5 milhão de linhas de pessoa a cada
-- consulta. `pessoas` não é derivável: em 93.524 ocorrências é maior que o número
-- de linhas em pessoa.

CREATE TABLE ocorrencia (
    id_lote                integer       NOT NULL,
    id                     bigint        NOT NULL CHECK (id > 0),
    ocorrido_em            timestamp     NOT NULL,
    ano                    smallint      NOT NULL
                           GENERATED ALWAYS AS (extract(year FROM ocorrido_em)::smallint) STORED,

    uf                     char(2)       NOT NULL CHECK (uf IN (
                               'AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT','PA',
                               'PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO')),
    br                     smallint      NOT NULL CHECK (br BETWEEN 0 AND 999),
    km                     numeric(6,1)  NOT NULL CHECK (km >= 0),
    municipio              text          NOT NULL CHECK (municipio <> ''),
    latitude               numeric(12,10) NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude              numeric(13,10) NOT NULL CHECK (longitude BETWEEN -180 AND 180),

    id_causa               smallint      NOT NULL REFERENCES causa_acidente (id_causa),
    id_tipo                smallint               REFERENCES tipo_acidente (id_tipo),
    classificacao_acidente text          CHECK (classificacao_acidente IN (
                               'Sem Vítimas', 'Com Vítimas Feridas', 'Com Vítimas Fatais')),

    fase_dia               text          NOT NULL,
    sentido_via            text          NOT NULL,
    condicao_meteorologica text          NOT NULL,
    tipo_pista             text          NOT NULL,
    tracado_via            text[]        NOT NULL CHECK (cardinality(tracado_via) >= 1),
    uso_solo_urbano        boolean       NOT NULL,

    pessoas                smallint      NOT NULL CHECK (pessoas        >= 0),
    mortos                 smallint      NOT NULL CHECK (mortos         >= 0),
    feridos_leves          smallint      NOT NULL CHECK (feridos_leves  >= 0),
    feridos_graves         smallint      NOT NULL CHECK (feridos_graves >= 0),
    feridos                smallint      NOT NULL CHECK (feridos        >= 0),
    ilesos                 smallint      NOT NULL CHECK (ilesos         >= 0),
    ignorados              smallint      NOT NULL CHECK (ignorados      >= 0),
    veiculos               smallint      NOT NULL CHECK (veiculos       >= 0),

    regional               text,
    delegacia              text,
    uop                    text,

    PRIMARY KEY (id_lote, id),
    -- O acidente tem de ser do ano do lote que o carregou.
    CONSTRAINT ocorrencia_lote_ano_fk FOREIGN KEY (id_lote, ano)
        REFERENCES lote_carga (id_lote, ano),
    CONSTRAINT ocorrencia_ano_do_recorte CHECK (ano BETWEEN 2017 AND 2025),
    -- Vale em 100% do recorte.
    CONSTRAINT ocorrencia_feridos_soma CHECK (feridos = feridos_leves + feridos_graves)
);

COMMENT ON TABLE ocorrencia IS
    'Um acidente registrado pela PRF (BAT), numa versão (lote). Insert-only: uma revisão '
    'da PRF gera linhas novas em outro lote. Carimbos: HORA DO EVENTO em ocorrido_em; '
    'HORA DA INGESTÃO via id_lote -> lote_carga. Hora de processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN ocorrencia.id_lote IS
    'Lote que carregou esta versão da linha. A hora da ingestão está em lote_carga.iniciado_em/finalizado_em.';
COMMENT ON COLUMN ocorrencia.id IS
    'Identificador do acidente na PRF. Único dentro do BAT; colide com IDs do BR-Brasil (fora do recorte).';
COMMENT ON COLUMN ocorrencia.ocorrido_em IS
    'Hora do evento: data_inversa + horario da PRF combinados. Hora local do acidente, SEM '
    'fuso conhecido (o Brasil tem quatro fusos e a PRF não informa qual), por isso timestamp '
    'sem time zone. Não comparar diretamente com carimbos de ingestão (timestamptz).';
COMMENT ON COLUMN ocorrencia.ano IS 'Ano do evento, derivado de ocorrido_em.';
COMMENT ON COLUMN ocorrencia.br IS
    'Número da BR. 0 em 1.407 ocorrências do recorte (rodovia não identificada); mantido como vem da PRF.';
COMMENT ON COLUMN ocorrencia.km IS 'Quilômetro da BR, uma casa decimal. Com br e uf, define o trecho da pergunta de gestão.';
COMMENT ON COLUMN ocorrencia.latitude IS 'Coordenada informada pela PRF. 53 pontos fora do Brasil e 14 zerados no recorte; sem correção na origem.';
COMMENT ON COLUMN ocorrencia.id_tipo IS 'Tipo de acidente de ordem 1. NULL quando a PRF não informa (41 ocorrências).';
COMMENT ON COLUMN ocorrencia.classificacao_acidente IS 'NULL quando a PRF informa NA (10 ocorrências).';
COMMENT ON COLUMN ocorrencia.condicao_meteorologica IS 'Campo condicao_metereologica da PRF (grafia corrigida no nome da coluna).';
COMMENT ON COLUMN ocorrencia.tracado_via IS 'A PRF combina vários traçados com ";" (ex.: Reta;Declive); guardado como lista, na ordem original.';
COMMENT ON COLUMN ocorrencia.uso_solo_urbano IS 'Campo uso_solo da PRF: Sim = urbano, Não = rural.';
COMMENT ON COLUMN ocorrencia.mortos IS 'Contagem informada pela PRF. Confere com a soma de pessoa em 100% do recorte.';
COMMENT ON COLUMN ocorrencia.feridos_graves IS 'Contagem informada pela PRF. Confere com a soma de pessoa em 100% do recorte.';
COMMENT ON COLUMN ocorrencia.pessoas IS 'Contagem informada pela PRF. Pode ser maior que o número de linhas em pessoa.';
COMMENT ON COLUMN ocorrencia.regional IS 'Superintendência da PRF (não é a UF). NULL quando NA ou N/A.';
