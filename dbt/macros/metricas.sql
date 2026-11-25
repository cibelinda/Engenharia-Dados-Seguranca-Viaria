{#-
  Camada de métricas (issue #53): a regra de cada métrica do projeto escrita UMA vez.

  Os modelos chamam estas macros em vez de repetir a regra no SQL, e a camada semântica
  (models/metricas/_metricas.yml) só agrega as colunas que elas produzem. Mudar uma regra é
  mudar uma linha aqui: o `dbt build` reconstrói tudo o que depende dela, e os testes
  dbt/tests/metrica_* conferem que o número do mart é o número da definição.
  Descrição e fórmula de cada métrica: docs/e4/metricas.md e models/metricas/metricas.md.
-#}

{#- Acidente grave: com ao menos um morto ou um ferido grave. É a definição do projeto, e não a
    classificacao_acidente da PRF (docs/pergunta-e-recorte.md). Devolve boolean. -#}
{% macro metrica_grave(mortos='mortos', feridos_graves='feridos_graves') -%}
    ({{ mortos }} > 0 or {{ feridos_graves }} > 0)
{%- endmacro %}


{#- Acidentes graves por 100 mil habitantes, com duas casas. NULL quando não há população. -#}
{% macro metrica_graves_por_100_mil(graves='graves', populacao='populacao') -%}
    round({{ graves }} * 100000.0 / nullif({{ populacao }}, 0), 2)
{%- endmacro %}


{#- Tamanho do "top": quantos trechos contam como "os mais graves" de um ano. -#}
{% macro metrica_top_n() -%}
    50
{%- endmacro %}


{#- O trecho ficou entre os 50 mais graves do ano: posição (rank pelos graves no ano, na
    mart_risco_trecho_ano) até 50. Posição NULL (ano sem grave) não entra. Devolve boolean. -#}
{% macro metrica_no_top_50(posicao='posicao') -%}
    coalesce({{ posicao }} <= {{ metrica_top_n() }}, false)
{%- endmacro %}


{#- Ponto negro: em quantos anos, no mínimo, o trecho precisa ter ficado no top 50 (issue #58). -#}
{% macro metrica_ponto_negro_min_anos() -%}
    3
{%- endmacro %}


{#- O trecho é um ponto negro: ficou entre os 50 mais graves em pelo menos 3 anos. Devolve boolean. -#}
{% macro metrica_ponto_negro(anos_no_top_50='anos_no_top_50') -%}
    coalesce({{ anos_no_top_50 }} >= {{ metrica_ponto_negro_min_anos() }}, false)
{%- endmacro %}


{#- Percentual de acidentes em que o atributo (boolean) é verdadeiro, com uma casa. O acidente sem
    a informação (NULL) fica fora do denominador. NULL quando nenhum acidente tem a informação. -#}
{% macro metrica_pct(atributo) -%}
    round(100.0 * avg(({{ atributo }})::int), 1)::numeric(4, 1)
{%- endmacro %}


{#- Mínimo de acidentes graves para dizer a causa ou o tipo mais frequente de um trecho. Abaixo
    disso, "o mais frequente" é um ou dois acidentes. É o mesmo corte do ranking de municípios. -#}
{% macro metrica_perfil_min_graves() -%}
    10
{%- endmacro %}
