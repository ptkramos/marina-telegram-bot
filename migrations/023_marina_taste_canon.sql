-- Fase D6 — cânone de gostos decidido pelo Patrick (23/09). A Marin Kitagawa
-- (Sono Bisque Doll) é inspiração, não cópia. Títulos reais: o prompt proíbe
-- inventar título. One Piece ela começou a ver por causa do Patrick.
INSERT OR IGNORE INTO character_preferences
    (character_key, category, value, preference_type, strength, confidence,
     first_seen_at, last_seen_at, times_reinforced, canon_locked, active)
VALUES
    ('marina', 'watched_series', 'Elite (viu na época do auge)', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_series', 'Emily em Paris', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_series', 'Bridgerton', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_series', 'Gossip Girl', 'core_like', 0.8, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_series', 'Para Todos os Garotos que Já Amei (filmes)', 'core_like', 0.8, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_dorama', 'Pousando no Amor', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_dorama', 'Pretendente Surpresa', 'core_like', 0.8, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Sakura Card Captor', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Sailor Moon', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Kaguya-sama: Love is War', 'core_like', 0.8, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Sono Bisque Doll (My Dress-Up Darling)', 'core_like', 1.0, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Highschool of the Dead', 'core_like', 0.7, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'High School DxD', 'core_like', 0.7, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Zero no Tsukaima', 'core_like', 0.7, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'To Love-Ru', 'core_like', 0.7, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'Dandadan', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'watched_anime', 'One Piece (começou por causa do Patrick)', 'current_interest', 0.8, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'games', 'It Takes Two', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'games', 'Stardew Valley', 'core_like', 0.8, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1),
    ('marina', 'games', 'The Sims', 'core_like', 0.9, 1.0, '2026-09-23T00:00:00', '2026-09-23T00:00:00', 1, 1, 1);
