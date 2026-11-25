-- Em cada ano com volume (1.000 graves ou mais), todo atributo do perfil aparece em algum acidente
-- grave, e não em todos. Se a PRF trocar a palavra que o atributo procura, ele cai a zero naquele
-- ano e este teste falha. O declive só é cobrado no BAT (no BR-Brasil ele é NULL, e bool_or de
-- NULL é NULL).
select ano
from {{ ref('int_grave_atributo') }}
group by ano
having count(*) >= 1000
   and (not coalesce(bool_or(curva), false)         or bool_and(curva)
     or not coalesce(bool_or(pista_simples), false) or bool_and(pista_simples)
     or not coalesce(bool_or(urbano), false)        or bool_and(urbano)
     or not coalesce(bool_or(noite), false)         or bool_and(noite)
     or not coalesce(bool_or(chuva), false)         or bool_and(chuva)
     or (ano >= 2017 and (not coalesce(bool_or(declive), false) or bool_and(declive)))
     or (ano < 2017 and bool_or(declive) is not null))
