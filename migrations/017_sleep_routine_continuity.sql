-- v3.7.0: close the post-midnight sleep gap and cover light/weekend days.

UPDATE routine_patterns
SET canonical_key = 'class_day_sleep',
    day_scope = 'class_day',
    window_start = '00:00',
    window_end = '06:59',
    probability = 1.0,
    active = 1
WHERE canonical_key = 'weekday_sleep';

INSERT INTO routine_patterns (
    canonical_key, character_key, routine_type, day_scope,
    window_start, window_end, probability, canon_locked, active
)
SELECT
    'light_day_sleep', 'marina', 'sleep', 'light_day',
    '00:00', '08:29', 1.0, 1, 1
WHERE NOT EXISTS (
    SELECT 1 FROM routine_patterns WHERE canonical_key = 'light_day_sleep'
);

UPDATE world_bootstrap
SET value = '1e470f21dfc3ba7142c1ce766b8852fe5e674b2da61c60ddd1c29f3877a7d41b',
    updated_at = CURRENT_TIMESTAMP
WHERE key = 'world_bible_seed_digest';
