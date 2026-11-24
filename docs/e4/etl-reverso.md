# ETL reverso: trechos críticos para a PRF de cada UF

Issue #54. A escolha do formato, com a medição, está no
[ADR 0006](../adr/0006-trechos-criticos-entregues-por-csv-agendado.md). Código em
[`orquestracao/etl_reverso.py`](../../orquestracao/etl_reverso.py), agendado no Dagster como o
asset `etl_reverso_trechos_criticos`. Contrato da E4 em [README.md](README.md).

## Quem consome e o que faz com o dado

**Quem:** a superintendência da PRF em cada UF, no planejamento operacional do mês.

**O que faz:** escolhe onde pôr viatura e operação de fiscalização (velocidade, alcoolemia,
ultrapassagem), e em que trechos pedir ao DNIT radar ou obra de segurança. Hoje ela vê os
acidentes do ano. O que a lista acrescenta é a **persistência**: o trecho que fica entre os 50
mais graves do país **ano após ano** é um ponto negro de verdade, e não o azar de um ano, e é
onde uma operação tem mais chance de evitar morte.

**Exemplo, MG:** a BR-381 km 480–490 ficou entre os 50 trechos mais graves do país em **todos os
19 anos completos** (2007 a 2025), e também no ano corrente, com 1.068 acidentes graves nesses anos. Em 2025, foi o 8º trecho mais
grave do país, com 67 acidentes graves e 9 mortos.

**Decisão que a plataforma permite e antes não se tomava:** escolher os trechos da operação pelo
histórico de 20 anos comparado com o país inteiro, e não só pelo que a UF viu no último ano.

## O que chega

Na pasta compartilhada (o volume `etl_reverso`, montado em `/app/saida/trechos_criticos` no
container da orquestração):

```
atual -> geracoes/2026-11-23T171854         a geração vigente (é o que a PRF abre)
geracoes/2026-11-23T171854/
    trechos_criticos_MG.csv                 um arquivo por UF (21 UFs têm trecho crítico)
    trechos_criticos_SC.csv
    ...
    manifesto.json                          data, critério, descrição das colunas,
                                            linhas e SHA-256 de cada arquivo
```

**Trecho crítico:** ficou entre os 50 mais graves do ano em pelo menos um ano completo
(`anos_completos_no_top_50 >= 1`). São 135 hoje, de 1 a 18 por UF. O ano corrente não basta: no
começo do ano, poucas semanas de dado já põem um trecho no top 50 (com ele, seriam 140). O
arquivo vem ordenado do mais persistente para o menos.

| Coluna | O que é | De onde vem |
|---|---|---|
| `trecho` | BR, UF e faixa de 10 km (ex.: BR-381/MG km 480–490) | `mart_persistencia_trecho.rotulo` |
| `br`, `km_inicio`, `km_fim` | Onde o trecho fica, como a PRF localiza na rodovia | `mart_persistencia_trecho` |
| `anos_completos_no_top_50` | Em quantos anos completos ficou entre os 50 mais graves do país | `mart_persistencia_trecho` (métrica da #53) |
| `anos_no_top_50` | O mesmo, contando também o ano corrente (parcial) | `mart_persistencia_trecho` (métrica da #53) |
| `primeiro_ano_no_top_50`, `ultimo_ano_no_top_50` | Desde quando e até quando | `mart_persistencia_trecho` |
| `graves_nos_anos_no_top_50` | Acidentes graves somados nesses anos | `mart_persistencia_trecho.graves_no_total` |
| `ano_referencia` | Último ano completo da PRF | `mart_risco_trecho_ano` (`ano_completo`) |
| `graves_ano_referencia`, `mortos_ano_referencia` | O trecho no último ano completo | `mart_risco_trecho_ano` |
| `posicao_ano_referencia` | Posição no ranking nacional desse ano (1 = o pior) | `mart_risco_trecho_ano.posicao` |

O ETL não calcula nenhuma métrica: escolhe colunas dos dois marts e separa por UF (contrato da
E4). Se a definição de "grave" ou do top 50 mudar, muda na camada de métricas da #53, e o arquivo
acompanha.

O CSV usa `;` e UTF-8 com BOM: abre no Excel em português com um clique, sem assistente de
importação.

## Quando chega

- O asset roda **todo dia**, como última etapa da esteira (`esteira`, 03:00), depois do
  `dbt build`.
- Só escreve uma **geração nova quando algum arquivo mudou** (compara o SHA-256 com o do
  manifesto vigente). A PRF republica uma vez por mês, então a lista muda cerca de uma vez por
  mês, e chega no máximo um dia depois da republicação.
- Ficam as **últimas 6 gerações** (cerca de meio ano), para comparar a lista do mês com a
  anterior. As mais antigas são apagadas pelo próprio ETL.

## E quando o destino está fora do ar

- A geração nova é escrita inteira numa pasta `.parcial`, renomeada no fim, e só depois o link
  `atual` passa a apontar para ela (troca atômica). **Quem abre `atual/` nunca vê metade de uma
  geração.**
- Se a pasta de destino não existe ou não aceita escrita, o ETL **falha na hora** (18 ms medidos)
  com "destino fora do ar". O Dagster tenta de novo em 30, 90 e 210 s. Se as quatro tentativas
  falharem, a execução fica vermelha na interface.
- Em qualquer falha, **a PRF continua com a geração anterior**, e o `gerado_em` do manifesto diz
  de quando ela é. Na medição, a geração anterior continuou legível, inteira, com o destino fora
  do ar.
- Se o banco estiver fora do ar, o ETL nem chega a escrever: falha na consulta, e vale o mesmo.

## Como rodar e conferir

Pelo Dagster (http://localhost:3000): materializar `etl_reverso_trechos_criticos`, ou esperar a
esteira das 03:00. Na linha de comando:

```bash
# roda o ETL reverso (o mesmo comando do asset)
docker compose run --rm orquestracao python -m orquestracao.etl_reverso

# copia a saída para fora do container e abre a lista de MG
docker compose cp orquestracao:/app/saida/trechos_criticos ./saida
cat saida/trechos_criticos/atual/manifesto.json
```

Medição do ADR 0006:

```bash
docker compose run --rm -v ./orquestracao/medicao:/app/orquestracao/medicao \
    orquestracao python -m orquestracao.medicao.medicao_adr0006
```

## Depende de

- **`mart_persistencia_trecho` (#53, Cibelly):** é dela que vêm `anos_no_top_50` e `anos_completos_no_top_50`. Enquanto o PR
  da #53 não estiver na `main`, o asset falha com "relation does not exist", e o Dagster mostra
  a etapa em vermelho; a medição foi feita com os modelos da #53 construídos localmente.
- **Exposure `etl_reverso_trechos_criticos` (#53):** o ETL aparece no fim da linhagem do
  `dbt docs`, lendo `mart_persistencia_trecho` e `mart_risco_trecho_ano`.
