-- Os atributos de cada acidente grave (issue #58), a base da mart_perfil_trecho e da
-- mart_perfil_comparacao: a regra de cada atributo fica escrita só aqui.
-- Granularidade: UM ACIDENTE GRAVE COM TRECHO (grave e chave_trecho não nula na fct_ocorrencia).
--
-- Cada atributo é verdadeiro, falso ou NULL. NULL é "a PRF não informou": o acidente fica fora do
-- percentual daquele atributo, em vez de contar como "não".
--
--   curva         : 'Curva' na lista tracado_via. Um acidente em curva e em declive conta nos dois.
--   declive       : 'Declive' na lista. SÓ NO BAT: o BR-Brasil registrava um valor só, entre Reta,
--                   Curva e Cruzamento, então nele o declive é desconhecido, e não falso.
--   pista_simples : tipo_pista 'Simples' (as outras são Dupla e Múltipla).
--   urbano        : uso do solo urbano.
--   noite         : fase_dia 'Plena noite'. Amanhecer e Anoitecer não contam.
--   chuva         : 'Chuva' ou 'Garoa/Chuvisco' (o BR-Brasil só tem 'Chuva').
--
-- Um valor novo da PRF cairia em falso sem ninguém ver: o teste trecho_perfil_vocabulario avisa.
select
    f.id_lote,
    f.id,
    f.chave_trecho,
    f.ano,
    f.sistema,
    f.mortos,
    'Curva' = any(f.tracado_via)                                        as curva,
    case when f.sistema = 'bat' then 'Declive' = any(f.tracado_via) end as declive,
    f.tipo_pista = 'Simples'                                            as pista_simples,
    f.uso_solo_urbano                                                   as urbano,
    f.fase_dia = 'Plena noite'                                          as noite,
    f.condicao_meteorologica in ('Chuva', 'Garoa/Chuvisco')             as chuva,
    c.causa,
    t.descricao                                                         as tipo
from {{ ref('fct_ocorrencia') }} f
left join {{ ref('dim_causa') }} c using (id_causa)
left join {{ ref('stg_tipo') }} t using (id_tipo)
where f.grave and f.chave_trecho is not null
