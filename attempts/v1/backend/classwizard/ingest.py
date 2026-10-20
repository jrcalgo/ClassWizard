import hashlib
import json
import uuid
from pathlib import Path
from sqlalchemy import select, update, text
from .config import DATA_DIR
from .db import (transaction, Dataset, Course, Program, Requirement, ProgramCourse, Occupation, Skill,
                 OccupationSkill, CourseSkill, SourceDocument, IngestionRun)

def load(path=None, fail_after=None):
    data = json.loads(Path(path or f'{DATA_DIR}/prepared/dataset.json').read_text())
    version = data['version']
    def ident(value):
        return version + ':' + value
    # Entire version activation and data load roll back together on failure.
    with transaction() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(14032026)"))
        if session.get(Dataset, version):
            return {'version': version, 'status': 'already_loaded'}
        missing = set(c for g in data['program']['groups'] for c in g['options']) - {c['code'] for c in data['courses']}
        if missing:
            raise ValueError('Missing program courses: ' + ', '.join(sorted(missing)))
        session.add(Dataset(id=version, active=False, manifest=data['manifest']))
        session.flush()
        session.add_all([Course(id=ident(c['code']), version=version, code=c['code'], title=c['title'], credits=c['credits'], payload=c) for c in data['courses']])
        session.add(Program(id=ident(data['program']['id']), version=version, payload=data['program']))
        session.add_all([Occupation(id=ident(c['soc']), version=version, soc=c['soc'], payload=c) for c in data['careers']])
        session.add_all([Skill(id=ident(s['element']), version=version, element=s['element'], payload=s) for s in data['skills']])
        session.add(SourceDocument(id=ident('manifest'), version=version, payload=data['manifest']))
        session.flush()
        if fail_after:
            raise RuntimeError('Injected failure to test rollback')
        pid = ident(data['program']['id'])
        session.add_all([Requirement(id=ident(g['id']), program_id=pid, payload=g) for g in data['program']['groups']])
        program_codes = set(c for g in data['program']['groups'] for c in g['options'])
        session.add_all([ProgramCourse(program_id=pid, course_id=ident(c)) for c in sorted(program_codes)])
        session.add_all([OccupationSkill(occupation_id=ident(l['soc']), skill_id=ident(l['element']), payload=l) for l in data['occupation_skills']])
        session.add_all([CourseSkill(course_id=ident(l['code']), skill_id=ident(l['element']), confidence=l['confidence'], payload=l) for l in data['course_skills']])
        session.flush()
        session.execute(update(Dataset).values(active=False))
        session.get(Dataset, version).active = True
        session.add(IngestionRun(id=str(uuid.uuid4()), payload={'version': version, 'status': 'activated', 'courses': len(data['courses'])}))
    return {'version': version, 'status': 'activated'}

if __name__ == '__main__':
    print(load())
