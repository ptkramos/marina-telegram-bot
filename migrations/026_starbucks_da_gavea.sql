-- Cânone decidido pelo Patrick (26/09): "Starbucks do Shopping da Gávea" era descritivo
-- demais; o lugar se chama "Starbucks da Gávea" (no mundo, no chat e nos Bastidores).
UPDATE world_places SET name = 'Starbucks da Gávea' WHERE canonical_key = 'starbucks_shopping_gavea';
UPDATE eventos_pendentes
   SET description = replace(description, 'Starbucks do Shopping da Gávea', 'Starbucks da Gávea')
 WHERE description LIKE '%Starbucks do Shopping da Gávea%';
