-- Coerência da mart_perfil_trecho:
--   * percentual entre 0 e 100;
--   * sem acidente grave, nenhum percentual, causa ou tipo;
--   * pct_declive existe se, e só se, o trecho tem grave no BAT (o BR-Brasil não registra declive;
--     o BAT registra o traçado em todos);
--   * graves_bat entre 0 e graves;
--   * causa e tipo só com 10 ou mais graves no BAT, e sempre a partir de 25 (a folga é para os 13
--     graves do BAT sem tipo na origem, que podem deixar um trecho de 10 graves com 9 válidos).
select *
from {{ ref('mart_perfil_trecho') }}
where pct_curva         not between 0 and 100
   or pct_declive       not between 0 and 100
   or pct_pista_simples not between 0 and 100
   or pct_urbano        not between 0 and 100
   or pct_noite         not between 0 and 100
   or pct_chuva         not between 0 and 100
   or (graves = 0 and num_nonnulls(pct_curva, pct_declive, pct_pista_simples, pct_urbano, pct_noite,
                                   pct_chuva, causa_principal, causa_principal_desde_2021,
                                   tipo_principal) > 0)
   or graves_bat < 0 or graves_bat > graves
   or (pct_declive is not null) <> (graves_bat > 0)
   or (graves_bat < 10 and num_nonnulls(causa_principal, causa_principal_desde_2021, tipo_principal) > 0)
   or (graves_bat >= 25 and num_nulls(causa_principal, tipo_principal) > 0)
