# Mapa dos pontos negros

Issue #57. Feedback da apresentação da E3: as visualizações do painel estavam fracas, e o ideal
seria um mapa. O painel ganhou uma aba nova, **Mapa dos pontos negros**, a primeira. As abas de
ranking continuam.

## O que o mapa mostra

| Camada | De onde vem | Como se lê |
|---|---|---|
| Círculos | `mapa_trecho` + `mart_risco_trecho_ano` + `mart_persistencia_trecho` | Um círculo por trecho de 10 km com acidente grave no ano. O tamanho é o número de graves no ano; a cor, em quantos anos o trecho ficou entre os 50 mais graves (amarelo = poucos, vermelho escuro = todos) |
| Mancha de densidade | `mapa_acidente_grave` | Onde os acidentes graves do ano se concentram. Ligada por padrão |
| Municípios | `mapa_municipio` + `mart_risco_municipio_ano` | Graves por 100 mil habitantes no ano. Cinza quando o município teve menos de 10 graves, a mesma regra do ranking da E3. Desligada por padrão |

Filtros: **ano** e **UF**. Passando o mouse num círculo ou num município, aparece o número.

Abaixo do mapa:

- **Ficha do trecho:** graves e mortos no ano, anos no top 50, o perfil dos acidentes graves
  (`mart_perfil_trecho`, #58) e o relevo (`dim_trecho_relevo`, #59).
- **O que os pontos negros têm de diferente:** as comparações `mart_perfil_comparacao` (#58) e
  `mart_relevo_comparacao` (#59).

Se uma dessas tabelas ainda não existir, a seção mostra um aviso, e não um erro.

## As tabelas do mapa (dbt, `dbt/models/marts/mapa/`)

| Tabela | Uma linha é | Linhas |
|---|---|---|
| `mapa_trecho` | um trecho com coordenada confiável: o ponto dele no mapa | 6.931 |
| `mapa_acidente_grave` | um acidente grave com coordenada confiável: só o ano, a UF e o ponto | 134.376 |
| `mapa_municipio` | um município: o contorno simplificado e os graves do último ano completo | 5.570 |

- Tudo em **WGS 84** (SRID 4326), o sistema dos mapas da web. O banco guarda em SIRGAS 2000
  (4674).
- O contorno dos municípios é **simplificado** (tolerância de 0,01 grau, cerca de 1 km): sem
  isso, os 5.570 contornos passam de 100 MB; assim, ficam em 3 MB.
- `mapa_acidente_grave` **não tem data, hora nem pessoa**, só o ano e o ponto, pelo cuidado com
  reidentificação do [`lgpd.md`](lgpd.md).
- O painel não calcula número nenhum: só junta essas tabelas com as da pergunta de gestão pela
  chave (`chave_trecho`, `cod_municipio`) e o ano.

**Testes:** chave única e ligação com a `dim_trecho` e com o IBGE; `mapa_acidentes_batem_com_o_fato`
(o mapa tem, ano a ano, exatamente os graves com coordenada confiável da `fct_ocorrencia`) e
`mapa_pontos_no_brasil` (nenhum ponto fora do retângulo do Brasil, que pegaria uma conversão de
coordenada errada). 20 itens passando.

## Limites

- **Só há coordenada desde 2017** (sistema BAT). Antes disso, o mapa mostra os círculos dos
  trechos, mas não a mancha de densidade.
- **De 2019 a 2024, metade das coordenadas é um ponto padrão** da PRF, e não o local do acidente
  (ADR 0002). Esses pontos ficam fora do mapa, e por isso a mancha desses anos é mais fraca.
- O lugar de cada trecho é o **centro dos acidentes com coordenada confiável** dele, e não um
  ponto da rodovia: um trecho em curva pode ficar um pouco fora do traçado.

## Como foi testado

Num banco carregado com os 20 anos, com as partes da #53 e da #59 construídas:

- `dbt build` dos três modelos do mapa: 20 itens passando;
- o painel rodado sem navegador, com a ferramenta de teste do Streamlit, conectado como
  `painel_leitor`: sem erro, com a ficha da BR-101/SC km 200–210 (125 graves e 10 mortos em
  2025, 20 anos no top 50), a camada de municípios ligada, o filtro de UF e um ano anterior a
  2017 (a mancha some, com o aviso).
