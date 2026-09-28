-- Registros que a carga (issue #4) não conseguiu colocar no esquema.
--
-- Casos já conhecidos no recorte: IDs em notação científica (5 ocorrências, 23
-- linhas de pessoa), a linha com pesid = 0 e id_veiculo = 0 (nem pessoa nem
-- veículo) e qualquer valor que viole as restrições das tabelas de dado.

CREATE TABLE linha_rejeitada (
    id_rejeicao  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_lote      integer NOT NULL,
    dataset      text    NOT NULL,
    numero_linha integer NOT NULL CHECK (numero_linha >= 1),
    linha_bruta  text    NOT NULL,
    motivo       text    NOT NULL CHECK (motivo <> ''),

    FOREIGN KEY (id_lote, dataset) REFERENCES lote_arquivo (id_lote, dataset),
    -- Um registro é rejeitado uma vez por lote; vários problemas vão juntos no motivo.
    CONSTRAINT linha_rejeitada_registro_uk UNIQUE (id_lote, dataset, numero_linha)
);

COMMENT ON TABLE linha_rejeitada IS
    'Registro de origem rejeitado pela carga, com o texto bruto. HORA DA INGESTÃO via '
    'id_lote -> lote_carga; o arquivo e sua hora de publicação via (id_lote, dataset) -> '
    'lote_arquivo. Não guarda hora do evento (o registro não foi interpretado). Hora de '
    'processamento não existe nesta etapa (E1).';
COMMENT ON COLUMN linha_rejeitada.id_lote IS
    'Lote em que a rejeição ocorreu. A hora da ingestão está em lote_carga.iniciado_em/finalizado_em.';
COMMENT ON COLUMN linha_rejeitada.numero_linha IS 'Número do registro no CSV, contando a partir de 1 após o cabeçalho.';
COMMENT ON COLUMN linha_rejeitada.linha_bruta IS 'Registro exatamente como estava no CSV (decodificado de cp1252).';
COMMENT ON COLUMN linha_rejeitada.motivo IS 'Por que o registro foi rejeitado (ex.: id não inteiro: 4e+05).';
