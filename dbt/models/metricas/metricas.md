{% docs metrica_graves %}
**Acidentes graves**: acidentes com ao menos um morto ou um ferido grave.

Fórmula: `count(acidente) where mortos > 0 or feridos_graves > 0`.

É a definição do projeto, e não a `classificacao_acidente` da PRF (que conta "Com Vítimas
Feridas" mesmo quando o ferido é leve; ver `docs/pergunta-e-recorte.md`). A regra está escrita
uma vez, na macro `metrica_grave` (`dbt/macros/metricas.sql`); a coluna `grave` do
`fct_ocorrencia` e as colunas `graves` dos marts saem dela.
{% enddocs %}

{% docs metrica_graves_por_100_mil %}
**Acidentes graves por 100 mil habitantes**: o número de acidentes graves do município no ano,
dividido pela população do município no mesmo ano, vezes 100 mil.

Fórmula: `round(graves * 100000 / populacao, 2)`.

A população é a estimativa do IBGE para o ano; em 2007 e 2023, que não têm estimativa, é a do
ano mais próximo (coluna `ano_populacao`). Num município pequeno, um único acidente grave faz a
taxa saltar: o painel só ranqueia quem tem ao menos 10 graves no ano. Regra na macro
`metrica_graves_por_100_mil` (`dbt/macros/metricas.sql`).
{% enddocs %}

{% docs metrica_anos_no_top_50 %}
**Anos no top 50**: em quantos anos o trecho ficou entre os 50 trechos com mais acidentes
graves do ano.

Fórmula: `count(ano) where posicao <= 50`, por trecho, sobre a `mart_risco_trecho_ano` (a
`posicao` é o `rank()` do trecho pelos graves no ano; empate fica com a mesma posição, então um
ano pode ter mais de 50 trechos no top).

Entram todos os anos de 2007 em diante, inclusive o ano corrente parcial: o ranking é feito
dentro do ano. É a resposta à segunda metade da pergunta de gestão: um trecho que fica no top
em muitos anos é um ponto negro de verdade, e não o azar de um ano. Regra na macro
`metrica_no_top_50` (`dbt/macros/metricas.sql`), gravada na coluna `no_top_50`.
{% enddocs %}

{% docs coluna_no_top_50 %}
O trecho ficou entre os 50 mais graves do ano (`posicao <= 50`). `false` quando `posicao` é
NULL (ano sem acidente grave). É a regra do top 50 que a métrica `anos_no_top_50` conta.
{% enddocs %}

{% docs coluna_graves_no_total %}
Acidentes graves somados **nos anos em que o trecho ficou no top 50** (não em todos os anos).
É o desempate da lista do painel: entre dois trechos com o mesmo `anos_no_top_50`, vem antes o
que teve mais graves nesses anos. 0 quando `anos_no_top_50 = 0`.
{% enddocs %}

{% docs coluna_ponto_negro %}
**Ponto negro**: o trecho ficou entre os 50 mais graves do ano em pelo menos 3 anos.

Fórmula: `anos_no_top_50 >= 3`.

Um ano no top pode ser acaso; três, dificilmente. Regra na macro `metrica_ponto_negro`
(`dbt/macros/metricas.sql`), gravada na coluna `ponto_negro` da `mart_persistencia_trecho`. Quem
compara pontos negros com os demais trechos lê essa coluna, e não repete a conta.
{% enddocs %}

{% docs coluna_perfil_pct %}
Percentual dos acidentes graves **com a informação preenchida**: o acidente em que a PRF não
informou o atributo fica fora da conta. NULL quando nenhum acidente grave do trecho tem a
informação. Com poucos graves o percentual oscila muito: leia junto com `graves`.
{% enddocs %}

{% docs coluna_perfil_declive %}
Percentual dos acidentes graves **do BAT (2017 em diante)** em trecho de declive. O BR-Brasil
(2007–2016) só registrava Reta, Curva e Cruzamento, então os anos dele ficam fora da conta. Só
conta `Declive`; `Aclive` é outro valor. NULL quando o trecho não tem acidente grave no BAT.
{% enddocs %}
