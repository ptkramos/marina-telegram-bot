"""Canonical PUC-Rio Design 2026.2 grade and guarded upgrade from the draft seed."""

import hashlib
import json

from world_repository import CanonConflictError, _iso_now


# Offerings and rooms: user-provided MicroHorário snapshot of 2026-09-18.
# Curriculum: https://www.puc-rio.br/ensinopesq/ccg/design.html
# Dates: https://www.puc-rio.br/sobrepuc/depto/dar/calendario/
# Weekdays follow Python (Monday=0). Teachers are intentionally not persona data.
COURSES = (
    ('DSG1400', 'Projeto: Projetar em Sociedade', 'PROJECT', 6, '1AB', 'required_period_component', 'DSG1814', ((0, '09:00', '13:00', 'ARTE1'), (2, '11:00', '13:00', 'ARTE1'))),
    ('DSG1804', 'Conteúdos Estruturantes: Projetar para a Sociedade', 'PROJECT', 2, '1AB', 'required_period_component', 'DSG1804', ((2, '09:00', '11:00', 'ARTE2'),)),
    ('DSG1862', 'Práticas Experimentais II', 'LAB', 2, '1AA', 'required_period_component', 'DSG1862', ((1, '07:00', '09:00', 'LAB'),)),
    ('DSG1854', 'Linguagem e Estruturas', 'STUDIO', 4, '1AD', 'required_period_component', 'DSG1854', ((1, '09:00', '11:00', 'L422'), (3, '09:00', '11:00', 'L422'))),
    ('DSG1852', 'Fundamentos em Ergodesign', 'THEORY', 2, '1AB', 'required_period_component', 'DSG1852', ((1, '11:00', '13:00', 'L260'),)),
    ('CRE1227', 'O Cristianismo', 'ELECTIVE', 4, '7TG', 'required_group_component', 'CRE0712', ((1, '13:00', '15:00', 'L332'), (3, '13:00', '15:00', 'L332'))),
    ('DSG1866', 'Práticas Experimentais VI', 'LAB', 2, '1AB', 'required_group_component', 'DSG0860', ((3, '07:00', '09:00', 'LAB'),)),
    ('DSG1853', 'Desenho Técnico', 'STUDIO', 2, '1AC', 'required_period_component', 'DSG1853', ((3, '11:00', '13:00', 'ARTE1'),)),
    ('DSG1985', 'Acessórios de Moda e Extensões do Corpo', 'ELECTIVE', 2, '1AA', 'extra_emphasis_elective', 'DSG0011', ((2, '07:00', '09:00', 'LAB'),)),
)
PROFILE = dict(institution='PUC-Rio', campus_area='Gávea', program_name='Design',
               focus_name='Corpo e Moda', entry_term='2025.1', current_term='2026.2')
METADATA = {
    'curriculum_key': 'design_2023_0', 'curriculum_source': 'puc_rio_official',
    'canonical_schedule_source': 'microhorario_2026_2_snapshot',
    'schedule_snapshot_date': '2026-09-18', 'timezone': 'America/Sao_Paulo',
    'schedule_snapshot_path': 'data/external/puc_rio/2026_2/raw/HORARIO_DAS_DISCIPLINAS_18092026.csv',
    'schedule_snapshot_sha256': '87838c84b0a676dfae025e2f9db2ee25b2dc9bb27dc3920d1051030ce5bf584d',
    'approximate_period': 4, 'plausible_extra_elective': True,
    'prior_history': 'progressão normal, sem histórico detalhado',
}
TERM_START, TERM_END = '2026-08-11', '2026-12-14'
OLD_COURSES = (
    ('projeto_corpo_moda', 'Projeto de Design: Corpo e Moda', 'PROJECT', 1, '08:00', '12:00'),
    ('cultura_visual', 'Cultura Visual e Moda', 'THEORY', 2, '08:00', '10:00'),
    ('materiais_texteis', 'Materiais e Experimentação Têxtil', 'LAB', 2, '10:00', '12:00'),
    ('atelie_modelagem', 'Ateliê de Modelagem', 'STUDIO', 3, '08:00', '12:00'),
    ('representacao_visual', 'Representação Visual de Projetos', 'LAB', 4, '10:00', '12:00'),
)
OLD_METADATA = {'curriculum_source': 'project_authored_not_official',
                'calendar_dates_pending': True, 'timezone': 'America/Sao_Paulo',
                'prior_history': 'progressão normal, sem histórico detalhado'}


def _digest(courses=None, metadata=None):
    courses = COURSES if courses is None else courses
    metadata = METADATA if metadata is None else metadata
    return hashlib.sha256(json.dumps([PROFILE, courses, metadata],
                        ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _insert_courses(conn, term_id):
    for key, name, kind, credits, section, requirement, group, blocks in COURSES:
        info = {'credits': credits, 'section': section, 'requirement_kind': requirement,
                'curriculum_group': group, 'source': 'microhorario_2026_2_snapshot',
                'curriculum_key': 'design_2023_0'}
        if key == 'DSG1985':
            info.update(emphasis='Corpo e Moda', prerequisite_in_snapshot=False)
        if key == 'CRE1227':
            info['enrollment_does_not_imply_religious_belief'] = True
        if key == 'DSG1804':
            info['instructional_type'] = 'PROJECT_SUPPORT'
        if key in ('DSG1400', 'CRE1227'):
            info['extension_hours'] = 60 if key == 'DSG1400' else 40
        course_id = conn.execute('''INSERT INTO academic_courses
            (academic_term_id,course_key,display_name,course_type,area,metadata_json)
            VALUES (?,?,?,?,?,?)''', (term_id, key, name, kind,
            'Corpo e Moda' if key == 'DSG1985' else 'Design',
            json.dumps(info, ensure_ascii=False, sort_keys=True))).lastrowid
        for day, start, end, room in blocks:
            conn.execute('''INSERT INTO academic_schedule_blocks
                (academic_course_id,weekday,start_time,end_time,location_key,metadata_json)
                VALUES (?,?,?,?,'puc_rio',?)''',
                (course_id, day, start, end, json.dumps({'room': room}, sort_keys=True)))


def seed_academic(db):
    digest = _digest()
    with db.transaction():
        with db.get_connection() as conn:
            previous = conn.execute("SELECT value FROM world_bootstrap WHERE key='academic_seed_digest'").fetchone()
            if previous:
                if previous['value'] != digest:
                    raise CanonConflictError('Seed acadêmico alterado; execute a migração explícita da grade V2')
                return False  # Never reset legitimate progression.
            if conn.execute("SELECT 1 FROM academic_profile WHERE character_key='marina'").fetchone():
                raise CanonConflictError('Perfil acadêmico já existe sem marcador de seed')
            metadata = json.dumps(METADATA, ensure_ascii=False, sort_keys=True)
            conn.execute('''INSERT INTO academic_profile
                (character_key,institution,campus_area,program_name,focus_name,entry_term,current_term,metadata_json)
                VALUES ('marina',?,?,?,?,?,?,?)''', (*PROFILE.values(), metadata))
            term_id = conn.execute('''INSERT INTO academic_terms
                (character_key,term_key,start_date,end_date,status,generated_by,created_at,metadata_json)
                VALUES ('marina','2026.2',?,?,'ACTIVE','CANONICAL_SEED',?,?)''',
                (TERM_START, TERM_END, _iso_now(), metadata)).lastrowid
            _insert_courses(conn, term_id)
            conn.execute('''INSERT INTO world_bootstrap (key,value,updated_at)
                VALUES ('academic_seed_digest',?,?)''', (digest, _iso_now()))
    return True


def upgrade_academic_grade_v2(db):
    """Upgrade only an untouched draft grade; never discard academic progress/events."""
    with db.transaction():
        with db.get_connection() as conn:
            marker = conn.execute("SELECT value FROM world_bootstrap WHERE key='academic_seed_digest'").fetchone()
            if marker and marker['value'] == _digest():
                return False
            if not marker or marker['value'] != _digest(OLD_COURSES, OLD_METADATA):
                raise CanonConflictError('Grade anterior desconhecida; migração automática recusada')
            profile = conn.execute("SELECT * FROM academic_profile WHERE character_key='marina'").fetchone()
            term = conn.execute("SELECT * FROM academic_terms WHERE character_key='marina' AND term_key='2026.2'").fetchone()
            if (not profile or not term or profile['current_term'] != '2026.2'
                    or term['status'] != 'ACTIVE' or term['generated_by'] != 'CANONICAL_SEED'
                    or term['start_date'] not in (None, '2026-08-01')
                    or term['end_date'] not in (None, '2026-12-18')):
                raise CanonConflictError('Estado acadêmico avançou ou divergiu; revisão manual necessária')
            courses = conn.execute('''SELECT id,course_key,status FROM academic_courses
                WHERE academic_term_id=?''', (term['id'],)).fetchall()
            if (len(courses) != len(OLD_COURSES)
                    or {row['course_key'] for row in courses} != {row[0] for row in OLD_COURSES}
                    or any(row['status'] != 'ENROLLED' for row in courses)):
                raise CanonConflictError('Cursos antigos alterados; revisão manual necessária')
            blocks = conn.execute('''SELECT b.* FROM academic_schedule_blocks b
                JOIN academic_courses c ON c.id=b.academic_course_id WHERE c.academic_term_id=?''',
                (term['id'],)).fetchall()
            expected_blocks = {(old[0], old[3], old[4], old[5]) for old in OLD_COURSES}
            actual_blocks = conn.execute('''SELECT c.course_key,b.weekday,b.start_time,b.end_time,
                b.active,b.location_key FROM academic_schedule_blocks b
                JOIN academic_courses c ON c.id=b.academic_course_id WHERE c.academic_term_id=?''',
                (term['id'],)).fetchall()
            if (len(blocks) != len(OLD_COURSES)
                    or {(b['course_key'], b['weekday'], b['start_time'], b['end_time'])
                        for b in actual_blocks} != expected_blocks
                    or any(b['active'] != 1 or b['location_key'] != 'puc_rio'
                           for b in actual_blocks)):
                raise CanonConflictError('Grade antiga alterada; revisão manual necessária')
            old_ids = {row['id'] for row in courses}
            old_block_ids = {row['id'] for row in blocks}
            for row in conn.execute("SELECT metadata_json FROM eventos_pendentes WHERE metadata_json IS NOT NULL"):
                meta = json.loads(row['metadata_json'] or '{}')
                if meta.get('academic_course_id') in old_ids or meta.get('academic_block_id') in old_block_ids:
                    raise CanonConflictError('Evento datado referencia a grade antiga; revisão manual necessária')
            conn.execute('''DELETE FROM academic_schedule_blocks WHERE academic_course_id IN
                (SELECT id FROM academic_courses WHERE academic_term_id=?)''', (term['id'],))
            conn.execute('DELETE FROM academic_courses WHERE academic_term_id=?', (term['id'],))
            metadata = json.dumps(METADATA, ensure_ascii=False, sort_keys=True)
            conn.execute("UPDATE academic_profile SET metadata_json=? WHERE character_key='marina'", (metadata,))
            conn.execute('''UPDATE academic_terms SET start_date=?,end_date=?,metadata_json=? WHERE id=?''',
                         (TERM_START, TERM_END, metadata, term['id']))
            _insert_courses(conn, term['id'])
            conn.execute("UPDATE world_bootstrap SET value=?,updated_at=? WHERE key='academic_seed_digest'",
                         (_digest(), _iso_now()))
    return True
