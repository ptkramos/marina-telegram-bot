-- Fase C.4 — cânone decidido pelo Patrick (22/09): o Theo tem carro e pode dar
-- carona pra Marina (ida/volta da PUC e das saídas). Bancos já semeados.
UPDATE world_characters
   SET initial_state_json = json_set(COALESCE(initial_state_json, '{}'), '$.has_car', json('true'))
 WHERE canonical_key = 'theo_martins';
