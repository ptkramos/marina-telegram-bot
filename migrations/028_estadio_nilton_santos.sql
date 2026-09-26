-- Cânone decidido pelo Patrick (26/09): às vezes ela vê o Botafogo no estádio (jogo em casa).
-- O Nilton Santos é real (Engenho de Dentro); ela vai com os amigos, de carona ou de uber.
INSERT OR IGNORE INTO world_places
    (canonical_key, name, region, place_type, truth_type, familiarity, distance_class,
     usage_rules_json, canon_locked, active, created_at, updated_at)
VALUES
    ('estadio_nilton_santos', 'Estádio Nilton Santos', 'Engenho de Dentro', 'stadium', 'real_world', 'known',
     'far', '{"botafogo_home": true}', 1, 1, '2026-09-26T00:00:00', '2026-09-26T00:00:00');
