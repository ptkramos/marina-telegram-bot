"""Explicit, atomic initial seed. Run after World Bible, before canonical bootstrap."""

import hashlib
import json

from world_repository import CanonConflictError, _iso_now


# Project-authored subjects, not an official PUC-Rio curriculum. Monday=0.
COURSES = (
    ('projeto_corpo_moda', 'Projeto de Design: Corpo e Moda', 'PROJECT', 1, '08:00', '12:00'),
    ('cultura_visual', 'Cultura Visual e Moda', 'THEORY', 2, '08:00', '10:00'),
    ('materiais_texteis', 'Materiais e Experimentação Têxtil', 'LAB', 2, '10:00', '12:00'),
    ('atelie_modelagem', 'Ateliê de Modelagem', 'STUDIO', 3, '08:00', '12:00'),
    ('representacao_visual', 'Representação Visual de Projetos', 'LAB', 4, '10:00', '12:00'),
)
PROFILE = dict(institution='PUC-Rio', campus_area='Gávea', program_name='Design',
               focus_name='Corpo e Moda', entry_term='2025.1', current_term='2026.2')
METADATA = {'curriculum_source': 'project_authored_not_official',
            'calendar_dates_pending': True, 'timezone': 'America/Sao_Paulo',
            'prior_history': 'progressão normal, sem histórico detalhado'}


def seed_academic(db):
    digest = hashlib.sha256(json.dumps([PROFILE, COURSES, METADATA],
                           ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with db.transaction():
        with db.get_connection() as conn:
            previous = conn.execute("SELECT value FROM world_bootstrap WHERE key='academic_seed_digest'").fetchone()
            if previous:
                if previous['value'] != digest:
                    raise CanonConflictError('Seed acadêmico alterado; exige migração explícita')
                # Never reset legitimate academic progression on a repeated bootstrap.
                return False
            if conn.execute("SELECT 1 FROM academic_profile WHERE character_key='marina'").fetchone():
                raise CanonConflictError('Perfil acadêmico já existe sem marcador de seed')
            metadata = json.dumps(METADATA, ensure_ascii=False, sort_keys=True)
            conn.execute('''INSERT INTO academic_profile
                (character_key,institution,campus_area,program_name,focus_name,entry_term,current_term,metadata_json)
                VALUES ('marina',?,?,?,?,?,?,?)''', (*PROFILE.values(), metadata))
            term_id = conn.execute('''INSERT INTO academic_terms
                (character_key,term_key,status,generated_by,created_at,metadata_json)
                VALUES ('marina','2026.2','ACTIVE','CANONICAL_SEED',?,?)''',
                (_iso_now(), metadata)).lastrowid
            for key, name, kind, day, start, end in COURSES:
                course_id = conn.execute('''INSERT INTO academic_courses
                    (academic_term_id,course_key,display_name,course_type,area,metadata_json)
                    VALUES (?,?,?,?,?,?)''', (term_id,key,name,kind,'Corpo e Moda',metadata)).lastrowid
                conn.execute('''INSERT INTO academic_schedule_blocks
                    (academic_course_id,weekday,start_time,end_time,location_key)
                    VALUES (?,?,?,?,'puc_rio')''', (course_id,day,start,end))
            conn.execute('''INSERT INTO world_bootstrap (key,value,updated_at)
                VALUES ('academic_seed_digest',?,?)''', (digest,_iso_now()))
    return True
