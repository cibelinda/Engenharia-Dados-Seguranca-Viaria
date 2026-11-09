-- Dimensão de trecho. Granularidade: UM TRECHO DE 10 KM de rodovia federal, BR + UF + faixa
-- de km (floor(km / 10) * 10, regra do contrato em docs/e3/README.md), que tenha ao menos um
-- acidente de 2007 em diante. A UF faz parte do trecho: a BR-116 km 0–10 no CE e na BA são
-- trechos diferentes, porque a PRF recomeça o km em cada UF.
--
-- Fora daqui (o fato fica com chave_trecho NULL): br = 0 (rodovia não identificada) e
-- acidentes sem br, uf ou km.
--
-- Atributos de qualidade, porque o km também tem sujeira:
--   km_isolado : o trecho tem 5 acidentes ou menos nos 20 anos e fica a mais de 100 km do
--                último trecho anterior com mais de 5 acidentes na mesma BR e UF. Ex.: a BR-040
--                em MG tem acidentes todo ano até o km 830, e depois um acidente aqui e ali nos
--                km 1.030, 2.140, 2.240... até o 9.960. É o km digitado errado, quase sempre.
--                A comparação é com o último trecho "cheio", e não com o vizinho, porque os kms
--                errados formam cadeias (2.140 e 2.240 estão a 100 km um do outro).
--                O trecho fica no ranking, mas quase nunca sobe nele.
--   geom_centro: o centro dos acidentes do trecho com coordenada confiável (BAT, sem o ponto
--                padrão). NULL no trecho que só tem acidente do BR-Brasil ou ponto padrão.
{{ config(indexes=[{'columns': ['chave_trecho'], 'unique': True}]) }}

with trecho as (
    select
        chave_trecho,
        min(br) as br,
        min(uf) as uf,
        min(floor(km / 10) * 10)::int as km_inicio,
        min(ano) as primeiro_ano,
        max(ano) as ultimo_ano,
        count(*) as acidentes,
        st_centroid(st_collect(geom) filter (where coordenada_confiavel)) as geom_centro
    from {{ ref('fct_ocorrencia') }}
    where chave_trecho is not null
    group by chave_trecho
),

com_anterior as (
    select
        *,
        max(case when acidentes > 5 then km_inicio end) over (
            partition by br, uf order by km_inicio
            rows between unbounded preceding and 1 preceding) as km_anterior_cheio
    from trecho
)

select
    chave_trecho,
    br,
    uf::text as uf,
    km_inicio,
    km_inicio + 10 as km_fim,
    'BR-' || lpad(br::text, 3, '0') || '/' || uf || ' km ' || km_inicio || '–' || (km_inicio + 10) as rotulo,
    primeiro_ano,
    ultimo_ano,
    (acidentes <= 5 and km_inicio - km_anterior_cheio > 100) is true as km_isolado,
    geom_centro::geometry(Point, 4674) as geom_centro
from com_anterior
