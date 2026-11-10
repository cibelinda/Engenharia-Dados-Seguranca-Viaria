-- Consulta do painel (painel/app.py, aba "Trechos mais graves"): os 20 trechos com mais
-- acidentes graves num ano. Roda a cada troca de ano no painel.
EXPLAIN (ANALYZE, BUFFERS)
SELECT br, uf, km_inicio, graves
FROM analitico_marts.mart_risco_trecho_ano
WHERE ano = 2025 AND br <> 0
ORDER BY graves DESC
LIMIT 20;
