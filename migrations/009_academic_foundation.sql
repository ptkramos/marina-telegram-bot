-- Storage only; weekday follows Python: Monday=0, Sunday=6.
CREATE TABLE academic_profile (
    character_key TEXT PRIMARY KEY REFERENCES world_characters(canonical_key),
    institution TEXT NOT NULL,
    campus_area TEXT,
    program_name TEXT NOT NULL,
    focus_name TEXT,
    entry_term TEXT NOT NULL,
    current_term TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    graduation_status TEXT NOT NULL DEFAULT 'in_progress',
    metadata_json TEXT
);
CREATE TABLE academic_terms (
    id INTEGER PRIMARY KEY,
    character_key TEXT NOT NULL REFERENCES academic_profile(character_key),
    term_key TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL CHECK(status IN ('PLANNED','ACTIVE','COMPLETED','VACATION','CANCELLED')),
    generated_by TEXT NOT NULL CHECK(generated_by IN ('CANONICAL_SEED','ACADEMIC_ENGINE','USER_DEFINED')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT,
    UNIQUE(character_key, term_key),
    CHECK(start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
);
CREATE TABLE academic_courses (
    id INTEGER PRIMARY KEY,
    academic_term_id INTEGER NOT NULL REFERENCES academic_terms(id),
    course_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    course_type TEXT NOT NULL CHECK(course_type IN ('THEORY','STUDIO','PROJECT','LAB','ELECTIVE','SEMINAR')),
    area TEXT,
    workload_weight REAL NOT NULL DEFAULT 1.0 CHECK(workload_weight > 0),
    status TEXT NOT NULL DEFAULT 'ENROLLED' CHECK(status IN ('ENROLLED','COMPLETED','DROPPED','FAILED')),
    prerequisite_keys_json TEXT,
    metadata_json TEXT,
    UNIQUE(academic_term_id, course_key)
);
CREATE TABLE academic_schedule_blocks (
    id INTEGER PRIMARY KEY,
    academic_course_id INTEGER NOT NULL REFERENCES academic_courses(id),
    weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL CHECK(start_time GLOB '[0-2][0-9]:[0-5][0-9]' AND start_time < '24:00'),
    end_time TEXT NOT NULL CHECK(end_time GLOB '[0-2][0-9]:[0-5][0-9]' AND end_time < '24:00'),
    location_key TEXT NOT NULL REFERENCES world_places(canonical_key),
    block_type TEXT NOT NULL DEFAULT 'CLASS',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    metadata_json TEXT,
    CHECK(start_time < end_time),
    UNIQUE(academic_course_id, weekday, start_time)
);
