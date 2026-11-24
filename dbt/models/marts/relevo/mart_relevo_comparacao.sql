-- Em que relevo estão os pontos negros, comparado com o resto da malha (#59).
-- Granularidade: UM TIPO DE RELEVO (compartimento do IBGE).
--
--   ponto negro : trecho que ficou entre os 50 mais graves (posicao <= 50 na
--                 mart_risco_trecho_ano, br <> 0) em pelo menos N anos. N vem da variável
--                 ponto_negro_min_anos (padrão 3). Quando a mart_persistencia_trecho (#53)
--                 entrar, o critério passa a ser lido de lá, para ficar num lugar só.
--   pct_pontos_negros  : dos pontos negros com relevo, quantos % estão neste tipo de relevo;
--   pct_demais_trechos : o mesmo para os outros trechos com relevo;
--   razao              : pct_pontos_negros / pct_demais_trechos. Acima de 1, o tipo de relevo
--                        tem mais pontos negros do que o esperado pelo tamanho da malha nele.
--
-- Só entram os trechos com geom_centro (dim_trecho_relevo), ou seja, com coordenada do BAT.
-- É comparação, e não causa: um relevo pode concentrar pontos negros porque concentra
-- cidades grandes e tráfego, e não pelo terreno.
with anos_no_top as (
    select chave_trecho, count(*) filter (where posicao <= 50) as anos_no_top_50
    from {{ ref('mart_risco_trecho_ano') }}
    where br <> 0
    group by chave_trecho
),

trecho as (
    select
        r.tipo_relevo,
        coalesce(a.anos_no_top_50, 0) >= {{ var('ponto_negro_min_anos', 3) }} as ponto_negro
    from {{ ref('dim_trecho_relevo') }} r
    left join anos_no_top a using (chave_trecho)
),

por_relevo as (
    select
        tipo_relevo,
        count(*)::integer as trechos,
        (count(*) filter (where ponto_negro))::integer as pontos_negros,
        (count(*) filter (where not ponto_negro))::integer as demais_trechos
    from trecho
    group by tipo_relevo
),

com_pct as (
    select
        *,
        round(100.0 * pontos_negros / nullif(sum(pontos_negros) over (), 0), 1) as pct_pontos_negros,
        round(100.0 * demais_trechos / nullif(sum(demais_trechos) over (), 0), 1) as pct_demais_trechos
    from por_relevo
)

select
    tipo_relevo,
    trechos,
    pontos_negros,
    pct_pontos_negros,
    pct_demais_trechos,
    round(pct_pontos_negros / nullif(pct_demais_trechos, 0), 2) as razao
from com_pct
