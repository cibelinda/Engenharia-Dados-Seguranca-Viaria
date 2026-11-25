# Perfil dos trechos: o que os pontos negros têm de diferente

Issue #58. O ranking e o mapa dizem **onde** os acidentes graves acontecem. Esta parte usa o que a
PRF já registra em cada acidente (traçado, pista, uso do solo, luz, tempo, causa e tipo) para
mostrar **como** eles são, e em que os dos pontos negros são diferentes dos outros.

```bash
docker compose run --rm dbt build      # modelos e testes
```

## As tabelas

| Modelo | Uma linha é | Linhas |
|---|---|---|
| [`int_grave_atributo`](../../dbt/models/intermediate/trecho/int_grave_atributo.sql) (view) | um acidente grave com trecho, com cada atributo como sim, não ou "não informado" | 423.976 |
| [`mart_perfil_trecho`](../../dbt/models/marts/trecho/mart_perfil_trecho.sql) | um trecho (todos os da `dim_trecho`; 649 nunca tiveram acidente grave) | 7.544 |
| [`mart_perfil_comparacao`](../../dbt/models/marts/trecho/mart_perfil_comparacao.sql) | um atributo: % nos pontos negros × % nos demais trechos | 6 |

O painel lê as duas `mart_*` na aba do mapa. A regra de cada atributo está escrita só na
`int_grave_atributo`, e as duas tabelas saem dela.

Além das colunas do contrato, entraram `graves_bat` e `causa_principal_desde_2021` no perfil, e
`razao`, `graves_pontos_negros` e `graves_demais_trechos` na comparação.

## O que a comparação mostra

Medido em 25/11/2026, com os 20 anos carregados. **Ponto negro** = trecho com 3 ou mais anos entre
os 50 mais graves: 96 trechos, que são 1,3% dos trechos e têm 17,4% dos acidentes graves.

| Atributo | Pontos negros | Demais trechos | Razão |
|---|---|---|---|
| Área urbana | **87,4%** | 34,9% | 2,50 |
| Noite | 40,0% | 40,9% | 0,98 |
| Chuva | 9,3% | 13,0% | 0,72 |
| Declive (só 2017+) | 5,5% | 9,8% | 0,56 |
| Curva | 9,8% | 22,4% | 0,44 |
| Pista simples | **23,8%** | 70,4% | 0,34 |

- **O ponto negro típico é a travessia urbana em pista dupla ou múltipla**, em reta, e não a serra
  nem a pista simples. O exemplo escrito na issue ("62% em pista simples, contra 41%") supunha o
  contrário.
- **O tipo de acidente confirma.** A colisão traseira é o tipo principal de 48% dos pontos negros
  (12% dos demais); o atropelamento, de 19% (6%). Nos demais trechos, quem lidera é a colisão
  frontal: 42%, contra 2% nos pontos negros.
- **A noite não separa os dois grupos.**
- **A área urbana explica parte do resto.** Só entre os graves urbanos, a diferença diminui em curva
  (9,1% × 12,6%) e declive (5,3% × 6,4%), e some na chuva (9,0% × 9,4%). A da pista simples
  continua (22,5% × 59,3%).

**A conclusão não depende do corte.** O sentido das diferenças é o mesmo com 1 ou com 10 anos no
top 50 no lugar de 3, sem o ano parcial de 2026 e em cada sistema da PRF separado:

| Variação | Área urbana | Pista simples | Curva |
|---|---|---|---|
| **3 anos (a regra)** | 87,4 × 34,9 | 23,8 × 70,4 | 9,8 × 22,4 |
| 1 ano | 84,6 × 32,8 | 26,8 × 72,2 | 11,1 × 22,8 |
| 10 anos | 89,6 × 38,5 | 16,1 × 67,9 | 10,4 × 21,4 |
| 3 anos, sem 2026 | 87,7 × 35,1 | 24,0 × 70,6 | 9,8 × 22,5 |
| 3 anos, só BR-Brasil | 92,2 × 36,9 | 26,2 × 73,0 | 10,7 × 24,0 |
| 3 anos, só BAT | 80,5 × 32,5 | 20,4 × 67,1 | 8,5 × 20,3 |

## Decisões

- **Ponto negro num lugar só.** A regra é a macro `metrica_ponto_negro`
  ([`metricas.sql`](../../dbt/macros/metricas.sql)), gravada na coluna `ponto_negro` da
  `mart_persistencia_trecho`. Conta `anos_no_top_50`, como está no contrato. Com
  `anos_completos_no_top_50` seriam 95 trechos em vez de 96.
- **"Não informado" não é "não".** O acidente sem a informação fica fora do denominador daquele
  atributo. São 9.769 graves sem condição meteorológica e 11 sem fase do dia.
- **Declive só no BAT.** O BR-Brasil registrava um valor só por acidente (Reta, Curva ou
  Cruzamento). Contar os anos dele como "sem declive" daria 2,3% nos pontos negros, e não 5,5%.
- **A conta é por acidente, e não a média dos trechos.** Na média simples, um trecho com 2 graves
  pesa o mesmo que um com 2 mil (a pista simples dos demais trechos iria de 70,4% para 88,1%).
- **Causa e tipo só com 10 ou mais graves no BAT.** É o corte do ranking de municípios. Abaixo
  disso (metade dos trechos), "o mais frequente" costuma ser um ou dois acidentes, e a causa de um
  acidente só ("ingestão de álcool") é quase um dado do condutor, o cuidado do
  [`lgpd.md`](lgpd.md).
- **Duas colunas de causa.** "Falta de atenção à condução" é a `causa_principal` de 66 dos 96 pontos
  negros, mas a PRF **deixou de usá-la em 2020** e a trocou por causas mais específicas. A
  `causa_principal` segue o contrato (2017 em diante); a `causa_principal_desde_2021` só usa os anos
  do vocabulário atual, e nela lideram "Ausência de reação do condutor" (30), "Acessar a via sem
  observar a presença dos outros veículos" (24) e "Reação tardia ou ineficiente do condutor" (24).

## Limites

- **É comparação, e não causa.** Os pontos negros são escolhidos pelo **número** de acidentes
  graves, e não pelo risco por veículo. Travessia urbana tem mais tráfego, e o volume de tráfego
  não está nos dados da PRF. Nada aqui diz que a pista dupla é mais perigosa.
- **Trecho com poucos graves oscila.** 1.844 trechos têm de 1 a 9 acidentes graves: um percentual de
  100% pode ser um acidente. Por isso `graves` vem ao lado.
- **O declive cresce em 2023.** A fatia de graves com mais de um valor no traçado passa de 13%
  (2022) para 25% (2023), e o declive, de 8,5% para 11,8%. Parece mudança no preenchimento, e não na
  via (não verificado). A comparação entre os grupos continua válida, porque os dois têm quase a
  mesma fatia de graves do BAT (41% e 43%); a evolução ano a ano, não.
- **O tipo também mudou de vocabulário.** "Colisão lateral" virou "mesmo sentido" e "sentido oposto"
  entre 2020 e 2021. Os tipos ficam como a PRF escreveu.

## Testes

| Teste | O que confere |
|---|---|
| `trecho_perfil_bate_com_origem` | Percentuais, causas e tipo recontados por outro caminho, direto da `stg_ocorrencia`, trecho a trecho |
| `trecho_perfil_comparacao_bate` | A comparação recontada da `fct_ocorrencia`, com o critério de ponto negro escrito à mão |
| `trecho_perfil_graves_bate` | Os graves do perfil são a soma da `mart_risco_trecho_ano`; nenhum trecho sobra nem falta |
| `trecho_perfil_percentual_valido` | Percentuais de 0 a 100, declive só com BAT, causa e tipo só com 10 graves |
| `trecho_perfil_atributo_some_no_ano` | Nenhum atributo cai a zero num ano (a PRF trocou a palavra) |
| `trecho_perfil_vocabulario` (aviso) | Um valor novo da PRF, que contaria como "não" em silêncio |
| `metrica_ponto_negro_bate` | `ponto_negro` é a regra do contrato, trecho a trecho |
| contrato e genéricos | Nome e tipo de cada coluna, `chave_trecho` única e ligada à `dim_trecho`, os seis atributos |

O `dbt build` passa com 134 de 134 (eram 112 antes desta parte; os 2 NO-OP são as exposures). As
regras foram quebradas de propósito, uma a uma, e depois desfeitas:

| O que foi quebrado | Testes que falharam (linhas) |
|---|---|
| Declive conta o BR-Brasil como "não" | `atributo_some_no_ano` (10) |
| Noite com a grafia do BR-Brasil (`Plena Noite`) | `atributo_some_no_ano` (20) |
| Chuva sem a garoa | `bate_com_origem` (2.175), `comparacao_bate` (1) |
| "Não informado" conta como "não" | `bate_com_origem` (4.796), `percentual_valido` (409), `comparacao_bate` (6) |
| Ponto negro com 4 anos | `metrica_ponto_negro_bate` (11) |
| A causa menos frequente | `bate_com_origem` (10.371) |
| Mínimo de 5 graves | `bate_com_origem` (3.721), `percentual_valido` (1.169) |
| "Desde 2021" a partir de 2020 | `bate_com_origem` (432) |
| "Demais trechos" com todos os trechos | `comparacao_bate` (6) |
| Trecho sem grave fora do perfil | `graves_bate` (649) |
| Um valor (`Túnel`) fora da lista conhecida | `vocabulario` (aviso, 1) |
