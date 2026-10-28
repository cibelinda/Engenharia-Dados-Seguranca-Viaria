-- Base de municípios do IBGE (E3, issue #42).
--
-- Dados brutos, do jeito que vêm do IBGE: a lista de municípios, a população por ano e o
-- contorno de cada município no mapa. A ingestão (blackspot/ibge/ingestao.py) substitui o
-- conteúdo destas tabelas a cada execução; o histórico de nome e UF fica no snapshot do dbt
-- (dim_municipio).

CREATE SCHEMA ibge;

-- unaccent: tira os acentos para comparar o nome do município da PRF com o do IBGE.
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE ibge.carga (
    id_carga      integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iniciada_em   timestamptz NOT NULL DEFAULT now(),
    terminada_em  timestamptz,
    municipios    integer,
    populacao     integer,
    malha         integer
);
COMMENT ON TABLE ibge.carga IS 'Cada execução da ingestão do IBGE. Hora da ingestão.';

CREATE TABLE ibge.municipio (
    cod_municipio char(7)  PRIMARY KEY CHECK (cod_municipio ~ '^[0-9]{7}$'),
    nome          text     NOT NULL CHECK (nome <> ''),
    uf            char(2)  NOT NULL,
    id_carga      integer  NOT NULL REFERENCES ibge.carga (id_carga)
);
COMMENT ON TABLE ibge.municipio IS
    'Municípios do IBGE (API de localidades), como estão hoje. Uma linha por município.';

CREATE TABLE ibge.populacao (
    cod_municipio char(7)  NOT NULL,
    ano           smallint NOT NULL,
    populacao     integer  NOT NULL CHECK (populacao > 0),
    fonte         text     NOT NULL CHECK (fonte IN ('estimativa', 'censo')),
    id_carga      integer  NOT NULL REFERENCES ibge.carga (id_carga),
    PRIMARY KEY (cod_municipio, ano)
);
COMMENT ON TABLE ibge.populacao IS
    'População por município e ano: estimativas anuais (SIDRA 6579) e censos 2010 (1378) e '
    '2022 (4709). Não há valor para 2007 e 2023. Uma linha por município por ano.';

CREATE TABLE ibge.malha_municipal (
    cod_municipio char(7)                      PRIMARY KEY,
    geom          geometry(MultiPolygon, 4674) NOT NULL,
    id_carga      integer                      NOT NULL REFERENCES ibge.carga (id_carga)
);
-- Índice espacial: deixa rápido achar em qual município cai cada acidente.
CREATE INDEX malha_municipal_geom_idx ON ibge.malha_municipal USING gist (geom);
COMMENT ON TABLE ibge.malha_municipal IS
    'Contorno de cada município (API de malhas, qualidade intermediária), SIRGAS 2000.';
