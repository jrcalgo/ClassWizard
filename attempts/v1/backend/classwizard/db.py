import time
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, JSON, UniqueConstraint, Index
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=5, pool_timeout=5, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
metrics = {'queries': 0, 'sql_seconds': 0.0}

@event.listens_for(engine, 'before_cursor_execute')
def before(conn, cursor, statement, params, context, many):
    context.started = time.perf_counter()

@event.listens_for(engine, 'after_cursor_execute')
def after(conn, cursor, statement, params, context, many):
    metrics['queries'] += 1
    metrics['sql_seconds'] += time.perf_counter() - context.started

class Base(DeclarativeBase):
    pass

class Dataset(Base):
    __tablename__ = 'datasets'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    manifest: Mapped[dict] = mapped_column(JSON)

class Course(Base):
    __tablename__ = 'courses'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(ForeignKey('datasets.id'), index=True)
    code: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    credits: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('version', 'code'),)

class Program(Base):
    __tablename__ = 'programs'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(ForeignKey('datasets.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)

class Requirement(Base):
    __tablename__ = 'requirements'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    program_id: Mapped[str] = mapped_column(ForeignKey('programs.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)

class ProgramCourse(Base):
    __tablename__ = 'program_courses'
    program_id: Mapped[str] = mapped_column(ForeignKey('programs.id'), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), primary_key=True)
    __table_args__ = (Index('ix_program_courses_course', 'course_id'),)

class Occupation(Base):
    __tablename__ = 'occupations'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(ForeignKey('datasets.id'), index=True)
    soc: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('version', 'soc'),)

class Skill(Base):
    __tablename__ = 'skills'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(ForeignKey('datasets.id'), index=True)
    element: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('version', 'element'),)

class OccupationSkill(Base):
    __tablename__ = 'occupation_skills'
    occupation_id: Mapped[str] = mapped_column(ForeignKey('occupations.id'), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey('skills.id'), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index('ix_occupation_skills_skill', 'skill_id'),)

class CourseSkill(Base):
    __tablename__ = 'course_skills'
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey('skills.id'), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index('ix_course_skills_skill', 'skill_id'),)

class SourceDocument(Base):
    __tablename__ = 'source_documents'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(ForeignKey('datasets.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)

class IngestionRun(Base):
    __tablename__ = 'ingestion_runs'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)

@contextmanager
def transaction():
    with Session.begin() as session:
        yield session

def public_snapshot():
    """Bounded bulk reads; one database snapshot per recommendation/plan."""
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        with conn.begin():
            version = conn.execute(text('SELECT id FROM datasets WHERE active = true')).scalar_one_or_none()
            if not version:
                return None
            def rows(table):
                return conn.execute(text(f'SELECT payload FROM {table} WHERE version = :v'), {'v': version}).scalars().all()
            courses = rows('courses')
            careers = rows('occupations')
            skills = rows('skills')
            program = rows('programs')[0]
            links = conn.execute(text('SELECT c.code, s.element, cs.confidence FROM course_skills cs JOIN courses c ON c.id = cs.course_id JOIN skills s ON s.id = cs.skill_id WHERE c.version = :v'), {'v': version}).all()
            career_links = conn.execute(text('SELECT o.soc, s.element, os.payload FROM occupation_skills os JOIN occupations o ON o.id = os.occupation_id JOIN skills s ON s.id = os.skill_id WHERE o.version = :v'), {'v': version}).all()
            for c in courses:
                c['skills'] = {el: conf for code, el, conf in links if code == c['code']}
            for o in careers:
                o['skills'] = {el: payload for soc, el, payload in career_links if soc == o['soc']}
            return {'version': version, 'courses': {c['code']: c for c in courses}, 'careers': careers, 'skills': {s['element']: s for s in skills}, 'program': program}
