-- Número 027: o 26 já foi usado direto no banco da produção (faxineira_e_porteiro, 24/09, antes do canon_extras).
-- Cânone decidido pelo Patrick (26/09): "Starbucks do Shopping da Gávea" era descritivo
-- demais; o lugar se chama "Starbucks da Gávea" (no mundo, no chat e nos Bastidores).
UPDATE world_places SET name = 'Starbucks da Gávea' WHERE canonical_key = 'starbucks_shopping_gavea';
UPDATE eventos_pendentes
   SET description = replace(description, 'Starbucks do Shopping da Gávea', 'Starbucks da Gávea')
 WHERE description LIKE '%Starbucks do Shopping da Gávea%';
