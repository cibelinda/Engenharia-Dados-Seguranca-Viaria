# Caracterização da carga

Passo 1 do Método de Decisão (issue #6). Recorte do PR #10: sistema BAT, 2017–2025,
conjuntos `ocorrencia` (`datatranAAAA`) e `pessoa` (`acidentesAAAA`).

Os números vêm de duas fontes:

- o reconhecimento de 2026-09-27 ([`docs/fontes/`](fontes/README.md));
- o perfil dos ZIPs baixados, gerado por [`bench/perfil_recorte.py`](../bench/perfil_recorte.py).
  O resultado completo está em [`bench/resultados/perfil_recorte.json`](../bench/resultados/perfil_recorte.json),
  que também registra o SHA-256 de cada ZIP lido (`arquivos_sha256`). Os 18 hashes são iguais
  às referências do [`sources.yaml`](../sources.yaml) de 2026-09-27.

Para reproduzir:

```bash
python -m blackspot.download --system bat --dataset ocorrencia --dataset pessoa \
    --year 2017 --year 2018 --year 2019 --year 2020 --year 2021 \
    --year 2022 --year 2023 --year 2024 --year 2025
python bench/perfil_recorte.py      # ~1 min, só biblioteca padrão
```

Os números do banco (volume por tabela, tamanho em disco, rejeitados) vêm da carga real
(#4, PR #18), rodada do zero em 2026-09-28, e da medição do ADR
([`bench/resultados/medicao_adr.json`](../bench/resultados/medicao_adr.json)).

## Origem

Dados abertos de acidentes da Polícia Rodoviária Federal. Os arquivos ficam no Google Drive,
e a PRF os publica como ZIP com um CSV cada (`;`, cp1252). A publicação é mensal (unidade DIOP).
Não há API: a captura é por download de arquivo inteiro.

## Período

De 01/01/2017 a 31/12/2025: 9 anos completos. 2026 fica fora por ser parcial e porque a PRF
o regrava todo mês.

## Volume

| Conjunto | Arquivos | Registros | Descompactado |
|---|---|---|---|
| `ocorrencia` | 9 | 632.713 | ~181 MB |
| `pessoa` | 9 | 1.654.197 | ~615 MB |

Os 18 ZIPs somam ~103 MB. O número de registros CSV é igual ao de linhas físicas em
todos os arquivos, ou seja, não há quebra de linha dentro de campo.

No banco, depois da carga (versão vigente, um lote por ano):

| Tabela | Linhas | Tamanho em disco, com índices |
|---|---|---|
| `ocorrencia` | 632.708 | 215 MB |
| `veiculo` | 1.191.461 | 231 MB |
| `pessoa` | 1.509.549 | 285 MB |
| `linha_rejeitada` | 29 | < 1 MB |
| **Total do banco (todas as tabelas)** | | **731 MB** |

Os 9 veículos a menos que no arquivo aparecem só em linhas rejeitadas (IDs em notação científica).

## Cardinalidade

| Medida | Valor |
|---|---|
| Ocorrências distintas (`id`) | 632.713 (nenhum `id` repetido) |
| Pessoas distintas (`pesid` ≠ 0) | 1.509.569 (nenhum `pesid` repetido em todo o recorte) |
| Veículos distintos (`id_veiculo` ≠ 0) | 1.191.470 |
| Linhas de `pessoa` com `pesid = 0` | 144.628: veículo sem pessoa associada; todas com `tipo_envolvido = NA` e `estado_fisico = NA` (`pesid_zero_por_tipo_envolvido_estado_fisico`) |
| Registros de `pessoa` por ocorrência | média 2,61; mediana 2; p95 6; máx. 143 |
| Veículos por ocorrência | média 1,96; mediana 2; p95 4; máx. 131 |
| `causa_acidente` distintas | 91 |
| `tipo_acidente` distintos | 22 |
| `classificacao_acidente` distintas | 4 (incluindo `NA`, em 10 ocorrências) |
| BRs distintas | 134 |
| UFs | 27 |
| Municípios distintos (UF + nome) | 2.210 |
| Trechos distintos (BR + UF + faixa de 10 km) | 6.883 |

### Chaves de `pessoa`

`(id, pesid)` não é único: tem 51.104 linhas excedentes. **Todas vêm de `pesid = 0`**, isto é,
de veículos listados sem pessoa (reboques, semirreboques, veículos estacionados).
`(id, pesid, id_veiculo)` é único em todos os anos, sem nenhuma linha excedente.

Na prática, o arquivo `pessoa` mistura dois tipos de linha: pessoa em veículo, e veículo sem
pessoa. Isso responde à pergunta aberta 1 do reconhecimento e é insumo para a chave da #3.

## Taxa de escrita

- **Volume anual:** 63,6 mil a 89,6 mil ocorrências por ano; em 2025, 72.529, cerca de 6 mil
  por mês e 200 por dia.
- **Padrão de escrita:** um lote mensal. A PRF substitui o arquivo inteiro do ano, com o mesmo
  ID e o mesmo nome no Drive. Não existe escrita linha a linha.
- **Regravação de anos fechados:** acontece. Datas observadas no `Last-Modified` do Drive:

  | Anos | Última gravação |
  |---|---|
  | 2017–2021 | 27/09/2024 |
  | 2022–2023 | 16/08/2024 |
  | 2024 | 23/09/2026 (ano fechado, regravado 4 dias antes do levantamento) |
  | 2025 | 18/03/2026 |

  No esquema da #3 ([`modelagem-origem.md`](modelagem-origem.md)), o lote é o ano inteiro e só
  é criado quando o SHA-256 de algum arquivo do ano muda. Uma regravação de 2024 acrescenta,
  então, 73.202 ocorrências e as 196.448 linhas do arquivo de pessoa, divididas entre
  `veiculo` e `pessoa`. Quantas dessas linhas mudaram de fato é a evidência da #7.

## Crescimento e sazonalidade

| Ano | Ocorrências | Variação | Com morto ou ferido grave |
|---|---|---|---|
| 2017 | 89.567 | — | 18.663 |
| 2018 | 69.333 | −22,6% | 17.535 |
| 2019 | 67.558 | −2,6% | 18.309 |
| 2020 | 63.585 | −5,9% | 17.452 |
| 2021 | 64.567 | +1,5% | 18.118 |
| 2022 | 64.606 | +0,1% | 18.409 |
| 2023 | 67.766 | +4,9% | 19.212 |
| 2024 | 73.202 | +8,0% | 20.644 |
| 2025 | 72.529 | −0,9% | 20.493 |

- A queda de 2018 ocorre no total, mas quase não aparece nos acidentes graves (−6%). A
  hipótese é mudança de critério de registro no início do BAT, mas **não foi verificada**.
- Os acidentes graves (`mortos > 0` ou `feridos_graves > 0`) somam 168.835 (26,7% das
  ocorrências) e são mais estáveis que o total: de 17,5 mil a 20,6 mil por ano.
- **Sazonalidade:** dezembro é o mês de pico (59.151 ocorrências somando 2017–2025, 12% acima
  da média mensal de 52.726). Fevereiro é o menor (48.874), em parte por ter menos dias.
- O menor mês da série é abril de 2020 (3.885), no início da pandemia. O maior é dezembro de 2017 (8.624).

## Taxa e padrão de leitura

A leitura serve à pergunta de gestão. Ela agrega por trecho e por ano e varre todo o
recorte. Não há acesso por chave nem consulta em tempo real. A leitura acontece em rodadas de
análise, sempre muito depois da escrita, que é mensal.

Consultas que respondem à pergunta, escritas sobre o esquema da #3. `ocorrencia_vigente`
(migração `V0008`) traz a versão do lote vigente de cada ano, e `ano` é derivado de `ocorrido_em`.
As ocorrências com `br = 0` ficam no banco, mas saem do ranking (`WHERE br <> 0`): sem a BR,
não dá para montar o trecho ([`pergunta-e-recorte.md`](pergunta-e-recorte.md), "Decidido depois").
A Q3 já filtra uma BR específica, então não precisa do filtro.

```sql
-- Q1: acidentes com morto ou ferido grave por trecho de 10 km e ano
SELECT br, uf, floor(km / 10) * 10 AS km_inicio,
       ano,
       count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
FROM ocorrencia_vigente
WHERE br <> 0
GROUP BY br, uf, km_inicio, ano;

-- Q2: persistência, ou seja, em quantos anos o trecho ficou entre os 50 mais graves
WITH por_trecho AS (
    SELECT br, uf, floor(km / 10) * 10 AS km_inicio,
           ano,
           count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves
    FROM ocorrencia_vigente
    WHERE br <> 0
    GROUP BY br, uf, km_inicio, ano
), ranqueado AS (
    SELECT *, rank() OVER (PARTITION BY ano ORDER BY graves DESC) AS posicao
    FROM por_trecho
)
SELECT br, uf, km_inicio, count(*) AS anos_entre_os_50, sum(graves) AS graves_total
FROM ranqueado
WHERE posicao <= 50
GROUP BY br, uf, km_inicio
ORDER BY anos_entre_os_50 DESC, graves_total DESC;

-- Q3: série anual de um trecho
SELECT ano,
       count(*) FILTER (WHERE mortos > 0 OR feridos_graves > 0) AS graves,
       count(*) AS total
FROM ocorrencia_vigente
WHERE br = 116 AND uf = 'SP' AND km >= 200 AND km < 210
GROUP BY ano ORDER BY ano;
```

As três leem só `ocorrencia`; `pessoa` entra no perfilamento e na E3. Com 6.883 trechos e
~18,8 mil acidentes graves por ano, a média é de ~2,7 acidentes graves por trecho por ano.
Esse número serve para calibrar o tamanho do trecho (parâmetro do PR #10).

O top 50 da Q2 é um valor provisório. O critério de persistência ainda precisa ser definido,
e também o desempate: `rank()` dá a mesma posição a trechos empatados, então o "top 50" pode
ter mais de 50 trechos num ano.

## Latência tolerada

Meses. A pergunta é anual, a PRF publica uma vez por mês com semanas de defasagem, e um ano
só é comparável depois de fechado. Um atraso de um mês entre a publicação e a carga não muda
nenhuma resposta.

## Características encontradas no perfil

- `data_inversa` está em `aaaa-mm-dd` em 100% das ocorrências do recorte.
- `br` e `km` são numéricos em 100% das ocorrências. `km` usa vírgula decimal (`123,4`).
- `br = 0` (rodovia não identificada) em 1.407 ocorrências (`br_zero` no JSON). Essas ocorrências
  ficam no banco, com o valor como vem da PRF, mas saem do ranking de trechos: "BR-0, km 0–10"
  não é um trecho de verdade.
- `latitude` e `longitude` são numéricas em 100% das ocorrências. A qualidade
  (ponto dentro da UF, coerência com o km) não foi medida aqui. O perfilamento da #3 achou
  33 pares fora do limite válido em 2017 e alguns pontos fora do Brasil
  ([`modelagem-origem.md`](modelagem-origem.md)).
- **IDs em notação científica:** 5 ocorrências (`1e+05` em 2018, `2e+05` em 2019, `3e+05` em
  2020, `4e+05` em 2021 e `6e+05` em 2024), com 23 registros de pessoa ligados a elas pelo mesmo
  texto (`registros_com_id_nao_numerico` no JSON). O `id` original não é recuperável.
- Toda ocorrência tem ao menos um registro de pessoa, e todo `id` de `pessoa` existe em `ocorrencia`.

## Inconsistências e tratamento na carga

Regras de conversão da carga: README, seção "Carga". Em cada arquivo, lidas = aceitas +
rejeitadas: 2.286.910 registros lidos, 29 rejeitados.

| Arquivo | Rejeitados | Motivo |
|---|---|---|
| `datatran` 2018, 2019, 2020, 2021 e 2024 | 5 (1 por ano) | `id` em notação científica |
| `acidentes` 2018 (1), 2019 (1), 2020 (3), 2021 (15) e 2024 (3) | 23 | `id` em notação científica |
| `acidentes` 2020 | 1 | `pesid = 0` e `id_veiculo = 0`: nem pessoa nem veículo |

Não viram rejeição, mas mudam o valor: 33 pares de coordenadas fora do limite em 2017 viram
`NULL`, e idade 0 ou acima de 110 e `ano_fabricacao` 0 viram `NULL` (desconhecido).

## Declaração de histórico

**A origem sobrescreve.** A PRF publica cada ano como um arquivo que é substituído
inteiro, no mesmo ID e com o mesmo nome, sem versão nem registro de alteração. Quem guarda
só a versão mais recente perde o estado anterior a cada regravação.

**O projeto guarda como insert-only, versionado por lote.** A decisão foi tomada na #3 e está
implementada no esquema: `lote_carga`, PKs que começam por `id_lote` e views `*_vigente`
([`modelagem-origem.md`](modelagem-origem.md) e
[ADR 0001](adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md)). Cada carga de um
ano é um lote. Uma republicação da PRF gera um lote novo, e o anterior não é alterado nem apagado.

| | Insert-only por lote (adotado) | CRUD (descartado) |
|---|---|---|
| Permite perguntar | quantas ocorrências de 2024 a PRF alterou, incluiu ou removeu depois de fechar o ano; se um trecho entrou ou saiu do ranking de graves por causa de uma revisão; qual era a resposta da pergunta de gestão numa data passada | só o estado da última versão publicada |
| Impede | nada que a origem permita | qualquer pergunta sobre o que a PRF mudou; a versão anterior se perde no primeiro UPDATE |

Nos dois casos, as versões anteriores a 2026-09-27 (linha de base dos SHA-256 do
reconhecimento) já não existem na origem e estão perdidas para qualquer modelo.

Evidência: **[#7]**, com a comparação da versão de 2024 com a linha de base.
