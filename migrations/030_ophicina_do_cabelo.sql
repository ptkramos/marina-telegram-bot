-- Cânone decidido pelo Patrick (26/09): o salão dela é a Ophicina do Cabelo de Botafogo
-- (Rua Voluntários da Pátria, 185). Unha em gel a cada ~3 semanas, antes de evento/job e às
-- vezes por mimo, pago do saldo dela (unhas.py). Depois serve também pro cabelo.
INSERT OR IGNORE INTO world_places
    (canonical_key, name, region, place_type, truth_type, familiarity, distance_class,
     usage_rules_json, canon_locked, active, created_at, updated_at)
VALUES
    ('ophicina_do_cabelo_botafogo', 'Ophicina do Cabelo', 'Botafogo', 'salao', 'real_world', 'known',
     'near_home', '{"endereco": "Rua Voluntários da Pátria, 185", "uso": "unhas em gel (mão e pé), cabelo",
       "opening_hours": {"mon": "09:00-20:00", "tue": "09:00-20:00", "wed": "09:00-20:00",
       "thu": "09:00-20:00", "fri": "09:00-20:00", "sat": "09:00-20:00", "sun": "closed"}}',
     1, 1, '2026-09-26T00:00:00', '2026-09-26T00:00:00');
