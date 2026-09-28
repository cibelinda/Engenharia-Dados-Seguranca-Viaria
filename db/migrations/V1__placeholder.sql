-- PROVISÓRIA: existe só para testar a esteira do docker-compose (issue #5).
-- Será substituída pelo esquema real da issue #3. Ao trocar, apague este arquivo
-- e recrie o banco com `docker compose down -v`, porque o Flyway guarda o
-- checksum de cada migração já aplicada.

CREATE TABLE placeholder_contagem (
    arquivo      TEXT        PRIMARY KEY,
    membro_csv   TEXT        NOT NULL,
    registros    INTEGER     NOT NULL CHECK (registros >= 0),
    contado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
