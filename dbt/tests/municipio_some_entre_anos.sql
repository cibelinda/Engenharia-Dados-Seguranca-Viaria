-- Distribuição (salto de série): o número de municípios com acidente não pode cair ou subir
-- mais de 15% de um ano para o outro. Uma queda assim indica municípios que "sumiram" na
-- ligação, e não uma mudança real nas estradas. O ano corrente (parcial) fica fora.
with por_ano as (
    select ano, count(distinct cod_municipio) as municipios
    from {{ ref('mart_risco_municipio_ano') }}
    where ano < (select max(ano) from {{ ref('mart_risco_municipio_ano') }})
    group by ano
)
select ano, municipios, anterior
from (select ano, municipios, lag(municipios) over (order by ano) as anterior from por_ano) t
where anterior is not null
  and abs(municipios - anterior) * 1.0 / anterior > 0.15
