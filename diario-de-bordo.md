# Diário de bordo

Uma entrada por semana, no formato **o que foi medido / o que surpreendeu / o que foi
decidido**. O que foi feito em cada commit, por quem e quando, fica no histórico do git.
O antigo `commits.md` (removido no PR #15) continua em `git show 58468f7:commits.md`.
Os usos de IA ficam registrados no [`AI-USAGE.md`](AI-USAGE.md).

## Semana 1 — E1 (27 e 28/09/2026)

Reconhecimento da fonte, pergunta e recorte, esquema, carga e ADR 0001.

### O que foi medido

- **Fonte** ([`docs/fontes/`](docs/fontes/README.md)): 50 arquivos da PRF (2007–2026), cerca
  de 370 MB em ZIP e 4 GB descompactados, vindos de dois sistemas de registro: BR-Brasil
  (2007–2016) e BAT (2017+). Entre eles, 490.283 IDs de acidente colidem.
- **Recorte** ([`docs/pergunta-e-recorte.md`](docs/pergunta-e-recorte.md)): BAT 2017–2025,
  com 632.713 ocorrências e 1.654.197 registros de pessoa.
- **Perfil** ([`docs/caracterizacao-da-carga.md`](docs/caracterizacao-da-carga.md)):
  `(id, pesid, id_veiculo)` é único em todo o recorte. As 144.628 linhas com `pesid = 0`
  são veículos sem pessoa.
- **Carga:** 2.286.910 registros lidos, 29 rejeitados. O banco ocupa 731 MB.
- **Medição do ADR 0001:** o modelo adotado (normalizado e insert-only) ocupa 731 MB, contra
  784 MB da opção nula. A Q2 leva 708 ms, contra 618 ms. Uma republicação de 2024
  acrescenta 85 MB.

### O que surpreendeu

- **A PRF regrava arquivos no mesmo ID e com o mesmo nome, inclusive anos fechados.** 2024
  foi regravado em 23/09/2026, 4 dias antes do reconhecimento. Os arquivos não têm coluna de
  versão.
- A página da PRF tem links ocultos que apontam para arquivos de outros anos. Por isso os
  IDs do manifesto foram validados à mão.
- O dicionário oficial não bate com os arquivos (formato de `data_inversa`, separador
  decimal de `km`).
- Há IDs corrompidos em notação científica (`4e+05`), e o valor original não é recuperável.
- `(id, pesid)` não é único no BAT. Todas as repetições vêm de `pesid = 0`.
- A queda de 22,6% nas ocorrências em 2018 quase não aparece nos acidentes graves (−6%).
- O modelo normalizado ocupa **menos** espaço que a opção nula, mesmo com índices e
  versionamento.

### O que foi decidido

- **Pergunta de gestão (#1):** quais trechos de 10 km concentraram mais acidentes com mortos
  ou feridos graves entre 2017 e 2025, e se esses trechos se mantêm de um ano para o outro.
- **Recorte (#2):** BAT 2017–2025, conjuntos `ocorrencia` e `pessoa`. 2026 fica fora por ser
  parcial e regravado todo mês.
- **Modelagem (#3, #6):** insert-only, versionado por lote, sendo o lote o ano
  ([ADR 0001](docs/adr/0001-modelo-normalizado-insert-only-versionado-por-lote.md)).
  Ocorrências com `br = 0` ficam no banco, mas saem do ranking.
- **Divergência de hash** é tratada como aviso, e não como erro, porque a PRF republica sem
  aviso.
- **Evidência de revisão (#7):** a evidência indireta fica registrada na E1. A comparação
  direta das versões fica para depois da próxima atualização mensal da PRF e vira insumo
  da E2.
- **Processo (#9):**
  - o `commits.md` foi substituído pelo histórico do git, por este diário e pelo `AI-USAGE.md`;
  - toda mudança entra por PR, com uma branch por issue e `Closes #N` na descrição;
  - cada PR é revisado por outra pessoa da Squad antes do merge;
  - quem usar IA num PR atualiza o `AI-USAGE.md` no mesmo PR.

## Correções da E1 (12/10/2026)

Duas correções da professora na avaliação da E1: o banco não era apropriado para dados com
latitude e longitude, e o BR-Brasil não podia ser descartado só por estar em outro formato.

### O que foi medido

- **Coordenadas** ([ADR 0002](docs/adr/0002-banco-espacial-postgis.md)): 100% das 681.425
  ocorrências do BAT (2017–2026) têm latitude e longitude; nenhum arquivo do BR-Brasil
  (2007–2016) tem as colunas.
- **Dataset completo** ([ADR 0003](docs/adr/0003-dataset-completo-br-brasil-e-bat.md)): os 50
  arquivos, 2.243.625 ocorrências e 5.156.169 registros de pessoa lidos; 2.243.584 ocorrências,
  4.008.904 veículos, 4.998.779 pessoas, 934.079 causas e 1.051.668 tipos carregados; 1.275 linhas
  rejeitadas, todas com motivo conhecido. Carga do zero em 467 s; banco com 2,7 GB.
- **PostGIS:** acidentes graves num raio de 2 km em 46 ms, contra 608 ms com haversine sem
  índice, com a mesma resposta. A coluna `geom` e os dois índices GiST ocupam ~102 MB.
- **Coordenada × BR + km:** em 87% dos trechos de 10 km do BAT, a distância mediana dos
  acidentes ao centro do trecho fica até 5 km.

### O que surpreendeu

- **Metade das coordenadas de 2019 a 2024 não é o local do acidente.** São pontos padrão
  repetidos: um ponto em São José/SC reúne 438 acidentes do km 205 ao 210,7. Em 2017, 2018 e
  2025 a fração cai para 6–16%, e em 2026 para 0,1%. Só apareceu com o agrupamento espacial.
- No BR-Brasil, `mortos` e `feridos_graves` batem com as pessoas quase sempre (só 8 e 19
  ocorrências não batem, por pessoas rejeitadas). O perfil inicial indicava 4% de divergência,
  mas era um erro dele: não tirava os espaços de `'Morto       '`.
- O BR-Brasil marca ausência com o texto `(null)`, tem `km` negativo (19), ano de fabricação
  9999 e IDs de ocorrência repetidos no mesmo arquivo (35).
- O `km` de 2016 já usa vírgula decimal, e não ponto, como dizia o reconhecimento.

### O que foi decidido

- **Banco espacial:** PostgreSQL 18.6 com PostGIS 3.6. `ocorrencia.geom` é uma coluna gerada
  das coordenadas (SIRGAS 2000), com índices GiST. O modelo da E1 continua o mesmo.
- **Dataset completo:** BR-Brasil e BAT no mesmo esquema, com o formato tratado na carga e o
  vocabulário de cada sistema guardado como veio. A pergunta de gestão passa a cobrir 2007–2025.
- **Migrações novas** (`V0009`–`V0012`), sem editar as da E1: um banco da E1 sobe para o esquema
  novo só aplicando as quatro.
- **Coordenadas repetidas** ficam como a PRF publicou; marcar e tratar é trabalho da E3.
