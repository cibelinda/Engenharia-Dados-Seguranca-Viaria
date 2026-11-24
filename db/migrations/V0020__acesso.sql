-- Controle de acesso com privilégio mínimo (E4, issue #52). Demonstração em docs/e4/acesso.md.
--
-- Até a E3, todos os serviços usavam o mesmo usuário, com acesso total. Aqui entram:
--   painel_leitor      o painel: só lê as tabelas de consumo (analitico_marts), e mais nada;
--   analista_regional  grupo de quem analisa uma UF: vê só os acidentes da própria UF (recorte
--                      de linha) e, das pessoas envolvidas, não vê idade, sexo, nacionalidade e
--                      naturalidade (recorte de coluna);
--   analista_df, analista_sc  dois usuários de exemplo do grupo, um por UF.
--
-- As senhas abaixo são só para desenvolvimento local, como a do usuário principal: o banco
-- escuta apenas em 127.0.0.1.
--
-- O usuário principal (o que roda as migrações, a carga e o dbt) é superusuário na imagem do
-- PostgreSQL e, por isso, não é afetado pelas políticas de linha abaixo.

-- Papéis -----------------------------------------------------------------------------------

CREATE ROLE painel_leitor LOGIN PASSWORD 'painel_leitor';
COMMENT ON ROLE painel_leitor IS 'Painel (E3/E4): só leitura das tabelas de consumo em analitico_marts.';

CREATE ROLE analista_regional NOLOGIN;
COMMENT ON ROLE analista_regional IS
    'Grupo de analistas de uma UF: só os acidentes da própria UF, sem os dados pessoais de pessoa.';

CREATE ROLE analista_df LOGIN PASSWORD 'analista' IN ROLE analista_regional;
CREATE ROLE analista_sc LOGIN PASSWORD 'analista' IN ROLE analista_regional;

-- Painel: só as tabelas de consumo ------------------------------------------------------------
--
-- O dbt apaga e recria as tabelas a cada execução, e um GRANT feito na tabela se perderia. Por
-- isso a permissão é dada por padrão no schema: toda tabela que o usuário principal criar em
-- analitico_marts já nasce legível pelo painel. O schema é criado aqui se o dbt ainda não rodou
-- (o dbt só cria o que não existe).

CREATE SCHEMA IF NOT EXISTS analitico_marts;
GRANT USAGE ON SCHEMA analitico_marts TO painel_leitor;
GRANT SELECT ON ALL TABLES IN SCHEMA analitico_marts TO painel_leitor;
ALTER DEFAULT PRIVILEGES IN SCHEMA analitico_marts GRANT SELECT ON TABLES TO painel_leitor;

-- Analista regional: recorte de linha e de coluna ----------------------------------------------

-- Qual UF cada analista pode ver. Os analistas não leem esta tabela: a política consulta a UF
-- pela função abaixo, que roda com a permissão de quem a criou.
CREATE SCHEMA acesso;
CREATE TABLE acesso.analista_uf (
    usuario name    PRIMARY KEY,
    uf      char(2) NOT NULL
);
COMMENT ON TABLE acesso.analista_uf IS 'UF que cada analista regional pode ver. Uma linha por usuário.';
INSERT INTO acesso.analista_uf (usuario, uf) VALUES ('analista_df', 'DF'), ('analista_sc', 'SC');

CREATE FUNCTION acesso.uf_do_usuario(usuario name) RETURNS char(2)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = acesso, pg_temp
    AS $$ SELECT uf FROM acesso.analista_uf WHERE analista_uf.usuario = uf_do_usuario.usuario $$;
REVOKE ALL ON FUNCTION acesso.uf_do_usuario(name) FROM PUBLIC;
GRANT USAGE ON SCHEMA acesso TO analista_regional;
GRANT EXECUTE ON FUNCTION acesso.uf_do_usuario(name) TO analista_regional;

-- Recorte de coluna: a pessoa sem idade, sexo, nacionalidade e naturalidade. Pedir uma dessas
-- colunas (ou SELECT *) dá "permission denied".
GRANT SELECT ON ocorrencia TO analista_regional;
GRANT SELECT (id_lote, pesid, id, id_veiculo, tipo_envolvido, estado_fisico)
    ON pessoa TO analista_regional;

-- Recorte de linha: o analista só vê os acidentes da própria UF, e as pessoas desses acidentes.
-- O (SELECT ...) faz a UF ser buscada uma vez por consulta, e não uma vez por linha.
ALTER TABLE ocorrencia ENABLE ROW LEVEL SECURITY;
CREATE POLICY analista_ve_a_propria_uf ON ocorrencia FOR SELECT TO analista_regional
    USING (uf = (SELECT acesso.uf_do_usuario(current_user)));

ALTER TABLE pessoa ENABLE ROW LEVEL SECURITY;
CREATE POLICY analista_ve_a_propria_uf ON pessoa FOR SELECT TO analista_regional
    USING (EXISTS (SELECT 1 FROM ocorrencia o
                   WHERE o.id_lote = pessoa.id_lote AND o.id = pessoa.id));
