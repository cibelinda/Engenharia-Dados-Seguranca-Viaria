-- Relevo do Brasil (E4, issue #59).
--
-- Dados brutos, do jeito que vêm do IBGE: o mapeamento de geomorfologia na escala
-- 1:250.000 (BDiA, versão 2026), um polígono por modelado de relevo, com o compartimento
-- (planalto, serra, planície...), a unidade geomorfológica (ex.: "Serra do Mar") e o domínio
-- morfoestrutural. A ingestão (blackspot/relevo/ingestao.py) substitui o conteúdo a cada
-- execução. O cruzamento com os trechos fica no dbt (dim_trecho_relevo).

CREATE SCHEMA relevo;

CREATE TABLE relevo.carga (
    id_carga      integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iniciada_em   timestamptz NOT NULL DEFAULT now(),
    terminada_em  timestamptz,
    arquivo       text        NOT NULL,
    sha256        char(64)    NOT NULL,
    poligonos     integer
);
COMMENT ON TABLE relevo.carga IS 'Cada execução da ingestão do relevo, com o arquivo e o SHA-256 lidos.';

CREATE TABLE relevo.modelado (
    id1           integer                      PRIMARY KEY,
    compartimento text,
    nm_dominio    text,
    nm_regiao     text,
    id_unidade    integer,
    nm_unidade    text,
    categoria     text,
    natureza      text,
    forma         text,
    dens_dren     text,
    aprof_inci    text,
    legenda       text,
    area_km2      numeric,
    geom          geometry(MultiPolygon, 4674) NOT NULL,
    id_carga      integer                      NOT NULL REFERENCES relevo.carga (id_carga)
);
-- Índice espacial: deixa rápido achar em qual polígono de relevo cai cada trecho.
CREATE INDEX modelado_geom_idx ON relevo.modelado USING gist (geom);
COMMENT ON TABLE relevo.modelado IS
    'Geomorfologia do IBGE, 1:250.000, versão 2026 (geom_area). Uma linha por polígono de modelado de relevo.';
COMMENT ON COLUMN relevo.modelado.compartimento IS
    'Campo compartime do IBGE: o compartimento de relevo (Planaltos, Serras, Planícies, Depressões, Tabuleiros...).';
COMMENT ON COLUMN relevo.modelado.dens_dren IS 'Densidade de drenagem do modelado de dissecação (quanto mais alta, mais recortado o terreno).';
COMMENT ON COLUMN relevo.modelado.aprof_inci IS 'Aprofundamento das incisões do modelado de dissecação (quanto mais fundo, mais acidentado).';
