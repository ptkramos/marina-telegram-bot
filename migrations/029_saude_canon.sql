-- Cânone decidido pelo Patrick (26/09): plano Bradesco Saúde Top Nacional (ela é dependente no
-- plano empresarial da empresa do pai). Urgente (virose): pronto-atendimento do Hospital Samaritano
-- Botafogo (Rua Bambina, 98). Dá pra esperar: consulta marcada na Novamed Botafogo (Rua São Clemente, 185).
INSERT OR IGNORE INTO world_places
    (canonical_key, name, region, place_type, truth_type, familiarity, distance_class,
     usage_rules_json, canon_locked, active, created_at, updated_at)
VALUES
    ('hospital_samaritano_botafogo', 'Hospital Samaritano Botafogo', 'Botafogo', 'hospital', 'real_world', 'known',
     'near_home', '{"endereco": "Rua Bambina, 98", "plano": "Bradesco Saúde Top Nacional", "uso": "pronto-atendimento"}',
     1, 1, '2026-09-26T00:00:00', '2026-09-26T00:00:00'),
    ('novamed_botafogo', 'Novamed Botafogo', 'Botafogo', 'clinic', 'real_world', 'known',
     'near_home', '{"endereco": "Rua São Clemente, 185", "plano": "Bradesco Saúde Top Nacional", "uso": "consulta marcada"}',
     1, 1, '2026-09-26T00:00:00', '2026-09-26T00:00:00');
