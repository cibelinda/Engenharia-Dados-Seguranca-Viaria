-- Resposta da pergunta de gestão: quais trechos de 10 km concentram mais acidentes com morto ou
-- ferido grave, e se eles se mantêm de um ano para o outro.
-- Granularidade: UM TRECHO POR ANO, para cada trecho que teve ao menos um acidente no ano.
--
--   graves  : acidentes com mortos > 0 ou feridos_graves > 0 (a definição do projeto, e não a
--             classificacao_acidente da PRF; ver docs/pergunta-e-recorte.md)
--   posicao : posição do trecho no ano, do que tem mais graves para o que tem menos (rank:
--             empate fica com a mesma posição). NULL quando o trecho não teve acidente grave.
--   percentil_graves : a posição como fração (0 = o pior do ano, 1 = o melhor), para comparar
--             anos com volumes diferentes: o BR-Brasil registrava o dobro de acidentes do BAT.
--   ano_completo : false no ano corrente (parcial). O ranking do ano parcial não se compara
--             com o dos outros.
--
-- br = 0 e acidentes sem trecho ficam fora (não há trecho para ranquear); o teste
-- trecho_volume_graves_bate_com_origem confere que eles são os únicos que faltam.
-- O painel (docs/e3/painel.md) lê br, uf, km_inicio, ano e graves: o contrato do modelo
-- (_trecho__marts.yml) faz o build falhar se uma coluna mudar de nome ou de tipo.
--
-- Índices (docs/e3/explain/):
--   (ano, graves) : a consulta do painel, "os 20 trechos com mais graves no ano", lê só as 20
--                   primeiras entradas do índice, de trás para a frente, em vez de varrer e
--                   ordenar a tabela inteira;
--   (chave_trecho, ano) único : a granularidade garantida também pelo banco.
{{ config(indexes=[
    {'columns': ['ano', 'graves']},
    {'columns': ['chave_trecho', 'ano'], 'unique': True},
]) }}

with por_trecho_ano as (
    select
        f.chave_trecho,
        f.ano,
        count(*) as acidentes,
        count(*) filter (where f.grave) as graves,
        sum(f.mortos) as mortos,
        sum(f.feridos_graves) as feridos_graves
    from {{ ref('fct_ocorrencia') }} f
    where f.chave_trecho is not null
    group by f.chave_trecho, f.ano
)

select
    p.chave_trecho::text                     as chave_trecho,
    t.br::smallint                           as br,
    t.uf::text                               as uf,
    t.km_inicio::integer                     as km_inicio,
    t.km_fim::integer                        as km_fim,
    t.rotulo::text                           as rotulo,
    p.ano::smallint                          as ano,
    a.ano_completo::boolean                  as ano_completo,
    p.acidentes::integer                     as acidentes,
    p.graves::integer                        as graves,
    p.mortos::integer                        as mortos,
    p.feridos_graves::integer                as feridos_graves,
    case when p.graves > 0 then
        rank() over (partition by p.ano, (p.graves > 0) order by p.graves desc)
    end::integer                             as posicao,
    case when p.graves > 0 then
        round((percent_rank() over (partition by p.ano, (p.graves > 0) order by p.graves desc))::numeric, 4)
    end::numeric(5, 4)                       as percentil_graves
from por_trecho_ano p
join {{ ref('dim_trecho') }} t using (chave_trecho)
join (select ano, bool_and(ano_completo) as ano_completo
      from {{ ref('dim_tempo') }} group by ano) a using (ano)
