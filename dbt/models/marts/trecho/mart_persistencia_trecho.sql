-- Segunda metade da pergunta de gestão: os trechos que concentram acidentes graves SE MANTÊM de
-- um ano para o outro? Até a E3, o painel calculava isto sozinho; agora o número vem do dbt
-- (issue #53, contrato em docs/e4/README.md).
-- Granularidade: UM TRECHO, todos os trechos da dim_trecho (o que nunca ficou no top 50 tem
-- anos_no_top_50 = 0).
--
--   anos_no_top_50  : em quantos anos o trecho ficou entre os 50 mais graves do ano. Conta a
--                     coluna no_top_50 da mart_risco_trecho_ano, que é onde mora a regra
--                     (macros/metricas.sql). Entram todos os anos, inclusive o ano corrente,
--                     parcial, como no painel da E3: o ranking é dentro do ano, então o ano
--                     parcial também tem os seus 50 piores.
--   graves_no_total : os acidentes graves somados NOS ANOS EM QUE O TRECHO FICOU NO TOP 50 (o
--                     mesmo número que o painel mostrava). 0 quando anos_no_top_50 = 0.
--
-- O teste metrica_anos_no_top_50_bate_com_painel confere que os números são os mesmos da
-- consulta que o painel da E3 fazia.
{{ config(indexes=[{'columns': ['chave_trecho'], 'unique': True}]) }}

with no_top as (
    select
        chave_trecho,
        count(*) filter (where no_top_50)        as anos_no_top_50,
        sum(graves) filter (where no_top_50)     as graves_no_total,
        min(ano) filter (where no_top_50)        as primeiro_ano_no_top_50,
        max(ano) filter (where no_top_50)        as ultimo_ano_no_top_50
    from {{ ref('mart_risco_trecho_ano') }}
    group by chave_trecho
)

select
    t.chave_trecho::text                          as chave_trecho,
    t.br::smallint                                as br,
    t.uf::text                                    as uf,
    t.km_inicio::integer                          as km_inicio,
    t.km_fim::integer                             as km_fim,
    t.rotulo::text                                as rotulo,
    coalesce(n.anos_no_top_50, 0)::integer        as anos_no_top_50,
    coalesce(n.graves_no_total, 0)::integer       as graves_no_total,
    n.primeiro_ano_no_top_50::smallint            as primeiro_ano_no_top_50,
    n.ultimo_ano_no_top_50::smallint              as ultimo_ano_no_top_50
from {{ ref('dim_trecho') }} t
left join no_top n using (chave_trecho)
