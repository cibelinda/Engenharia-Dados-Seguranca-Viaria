-- Os atributos do perfil comparam texto ('Curva', 'Plena noite'...). Um valor novo da PRF, ou uma
-- grafia nova, contaria como "não" em silêncio. Este teste avisa, sem parar a esteira, para
-- alguém decidir na int_grave_atributo (ou juntar a grafia no staging).
{{ config(severity='warn') }}
with valor as (
    select distinct sistema, 'tracado_via' as coluna, t.valor
    from {{ ref('fct_ocorrencia') }} f, unnest(f.tracado_via) as t (valor)
    union
    select distinct sistema, 'tipo_pista', tipo_pista from {{ ref('fct_ocorrencia') }}
    union
    select distinct sistema, 'fase_dia', fase_dia from {{ ref('fct_ocorrencia') }}
    union
    select distinct sistema, 'condicao_meteorologica', condicao_meteorologica from {{ ref('fct_ocorrencia') }}
)
select *
from valor
where valor is not null
  and not case coluna
        when 'tracado_via' then
            valor in ('Reta', 'Curva', 'Cruzamento')
            or (sistema = 'bat' and valor in (
                'Declive', 'Aclive', 'Interseção de Vias', 'Rotatória', 'Retorno Regulamentado',
                'Em Obras', 'Viaduto', 'Ponte', 'Desvio Temporário', 'Túnel'))
        when 'tipo_pista' then valor in ('Simples', 'Dupla', 'Múltipla')
        when 'fase_dia' then valor in ('Pleno dia', 'Plena noite', 'Amanhecer', 'Anoitecer')
        when 'condicao_meteorologica' then
            valor in ('Céu Claro', 'Nublado', 'Chuva', 'Sol', 'Garoa/Chuvisco', 'Nevoeiro/Neblina',
                      'Vento', 'Granizo', 'Neve')
      end
