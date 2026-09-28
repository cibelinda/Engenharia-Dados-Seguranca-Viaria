# Uso de IA

> **Versão provisória.** Reúne as declarações de uso de IA que estavam no `commits.md`
> (removido no PR #15), para que o registro não se perca. O formato será ajustado ao
> modelo da disciplina na issue #9.

| Quem | Onde | Uso declarado |
|---|---|---|
| Cibelly | Aquisição dos dados: `sources.yaml` | Manifesto com os 50 arquivos da PRF, os IDs do Google Drive conferidos um a um e o SHA-256 de referência de cada arquivo, feito via IA. |
| Ana Luiza Komatsu | Issue #2 (PR #10): recorte dos dados | O recorte (BAT 2017–2025, conjuntos de ocorrência e pessoa) foi escolhido com o uso de IA, a partir dos números do reconhecimento em `docs/fontes/`. |
| Ana Luiza Komatsu | Issue #5 (PR #11): esteira do Docker Compose | Feita com o uso de IA: configuração do Docker, scripts e README, incluindo os ajustes pedidos na revisão do PR. |
| Cibelly | Issue #3 (PR #13): esquema físico | Feita com o uso de IA: perfilamento, SQL e ADR. |
| Maria Clara | Issue #6 (PR #12): caracterização da carga e rascunho do ADR 0001 | Feita com o uso de IA: script de perfil e rascunho dos textos. |
| Ana Luiza Komatsu | Revisão do PR #13 | Feita com o uso de IA: teste das migrações num banco vazio, script que conferiu as restrições do esquema contra os 18 arquivos do recorte e texto da revisão. |
| Maria Clara | Issue #8: testes de esquema, restrições e versão vigente | Feita com o uso de IA: testes, serviço `tests` no compose e README. Conferi que os testes falham quando uma restrição é removida do banco. |

O texto original das declarações continua no histórico do git (`git show 58468f7:commits.md`
e nas branches dos PRs #12 e #13).
