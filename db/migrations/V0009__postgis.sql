-- Banco espacial: PostGIS (ADR 0002).
--
-- A PRF publica latitude e longitude de cada ocorrência a partir de 2017 (BAT). O
-- BR-Brasil (2007–2016) não tem coordenadas: só BR + km. Por isso a origem guarda os
-- dois referenciais. O trecho (br, uf, km) vale para os 20 anos, e o ponto (geom) vale
-- para o BAT e permite as consultas espaciais da pergunta de gestão: distância,
-- agrupamento de acidentes próximos (ST_ClusterDBSCAN), grade de células e cruzamento
-- com outras camadas (malha rodoviária do DNIT, limites do IBGE).
--
-- geom é coluna gerada a partir de latitude/longitude, e não um dado a mais: a carga
-- continua gravando só os números que a PRF publicou, e o ponto não diverge deles.
-- SRID 4674 = SIRGAS 2000, o referencial geodésico oficial do Brasil (IBGE). Para medir
-- em metros, projete com ST_Transform(geom, 5880) (SIRGAS 2000 / Brazil Polyconic) ou
-- use geom::geography.

CREATE EXTENSION IF NOT EXISTS postgis;

ALTER TABLE ocorrencia
    ADD COLUMN geom geometry(Point, 4674)
    GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude::float8, latitude::float8), 4674)) STORED;

-- Índices espaciais (R-tree sobre GiST). Parciais: o BR-Brasil inteiro e as coordenadas
-- anuladas pela carga não têm ponto.
--   geom            : contém/intersecta (polígonos de município, caixas, trechos da malha);
--   geom::geography : distância em metros (ST_DWithin(geom::geography, ponto, 2000)), que é
--                     a consulta típica de ponto negro ("acidentes graves a menos de X m").
CREATE INDEX ocorrencia_geom_idx ON ocorrencia USING gist (geom) WHERE geom IS NOT NULL;
CREATE INDEX ocorrencia_geog_idx ON ocorrencia USING gist ((geom::geography)) WHERE geom IS NOT NULL;

COMMENT ON COLUMN ocorrencia.geom IS
    'Ponto da ocorrência (SIRGAS 2000, EPSG:4674), gerado de longitude/latitude. NULL quando a PRF '
    'não publica coordenada (BR-Brasil, 2007–2016) ou quando a carga a anulou por estar fora do '
    'limite válido. Mesmo carimbo de tempo da ocorrência (hora do evento em ocorrido_em).';
