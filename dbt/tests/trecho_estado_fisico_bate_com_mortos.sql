-- Limpeza do staging: depois de juntar os vocabulários ('Morto' do BR-Brasil = 'Óbito' do BAT,
-- 'Ferido Grave' = 'Lesões Graves'), as pessoas em óbito e com lesão grave de cada acidente
-- batem com as contagens mortos e feridos_graves da ocorrência. Medido em 2026-11-09: 8 e 19
-- acidentes divergem em 2,2 milhões, os que perderam pessoas para linha_rejeitada na carga
-- (docs/modelagem-origem.md). Se uma grafia nova de estado físico escapar da harmonização, as
-- divergências passam de milhares e o teste falha. Limite: 0,01% dos acidentes.
with pessoa as (
    select id_lote, id,
           count(*) filter (where estado_fisico = 'Óbito') as obitos,
           count(*) filter (where estado_fisico = 'Lesões Graves') as lesoes_graves
    from {{ ref('stg_pessoa') }}
    -- Só quem morreu ou teve lesão grave: o acidente sem nenhuma dessas pessoas fica com 0
    -- pelo coalesce abaixo, e o agrupamento é de ~570 mil pessoas, e não de 5 milhões.
    where estado_fisico in ('Óbito', 'Lesões Graves')
    group by 1, 2
),
divergencia as (
    select count(*) as acidentes,
           count(*) filter (where o.mortos <> coalesce(p.obitos, 0)) as mortos_divergem,
           count(*) filter (where o.feridos_graves <> coalesce(p.lesoes_graves, 0)) as graves_divergem
    from {{ ref('stg_ocorrencia') }} o
    left join pessoa p using (id_lote, id)
)
select * from divergencia
where mortos_divergem > 0.0001 * acidentes or graves_divergem > 0.0001 * acidentes
