"""One-time setup of a dedicated synthetic Render database; run before starting the API."""
import os
from datetime import date, timedelta

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import hash_password
from database import engine
from models import (Base, CandidateEvaluation, Country, EducationLevel, Language, LanguageLevel,
                    LanguageScale, OrgUnit, User, Vacancy)
from candidate_schemas import CandidateEvaluationIn, CandidateMethodologyIn
from demo_candidates import seed_demo_candidates
from demo_vacancies import EXAMPLES
from migrations import run_migrations
from routers.appointments import create_appointment
from routers.personnel import PersonnelRecordIn, create_record
from seed_data import seed_methodology, seed_org, seed_reference
from services import candidate_methodology as methodology
from services import candidate_sources


DATABASE_NAME = "digital_profile_demo"
MARKER = "digital-profile-render-synthetic-v1"
ACTOR = "render-demo-bootstrap"
MARKER_TABLE = "public.render_demo_bootstrap"


def _check_database(connection):
    if (os.getenv("APP_ENV") != "production" or not os.getenv("DATABASE_URL")
            or engine.dialect.name != "postgresql" or engine.url.database != DATABASE_NAME
            or connection.scalar(text("SELECT current_database()")) != DATABASE_NAME):
        raise RuntimeError("Нужны APP_ENV=production и выделенная база PostgreSQL digital_profile_demo.")
    if connection.scalar(text("SELECT current_schema()")) != "public":
        raise RuntimeError("Демонстрационная база должна использовать схему public.")


def _is_ready(connection):
    if connection.scalar(text("SELECT to_regclass(:table)"), {"table": MARKER_TABLE}) is None:
        return False
    markers = connection.scalars(text(f"SELECT fixture FROM {MARKER_TABLE}")).all()
    if markers != [MARKER]:
        raise RuntimeError("Неизвестная метка установки. Автоматические изменения запрещены.")
    return True


def require_ready_demo():
    """Read-only guard for the ASGI wrapper, including direct uvicorn startup."""
    with engine.connect() as connection:
        _check_database(connection)
        if not _is_ready(connection):
            raise RuntimeError("Сначала завершите подготовку синтетической базы.")


def _accounts():
    accounts = []
    for role in ("admin", "viewer"):
        prefix = "DEMO_" + role.upper()
        login = os.getenv(prefix + "_USERNAME", "").strip()
        password = os.getenv(prefix + "_PASSWORD", "")
        if role == "viewer" and not login and not password:
            continue
        if not login or len(login) > 60 or any(ch.isspace() or not ch.isprintable() for ch in login):
            raise ValueError(f"Задайте корректный логин в {prefix}_USERNAME.")
        if not (12 <= len(password.strip()) and len(password) <= 1024) or password.casefold() == login.casefold():
            raise ValueError(f"Задайте отдельный пароль длиной от 12 символов в {prefix}_PASSWORD.")
        if any(other.username.casefold() == login.casefold() for other in accounts):
            raise ValueError("Логины администратора и наблюдателя должны различаться.")
        accounts.append(User(username=login, password_hash=hash_password(password), role=role,
                             display_name=login, is_active=True))
    return accounts


def _create_dossier_method(db, people):
    original = methodology.get_method(db)
    draft = methodology.clone_method(db, original.id, ACTOR)
    template = methodology.method_dict(draft)
    education = {v.code: v.rank for v in db.query(EducationLevel)}
    english = db.query(Language).filter_by(code="EN").one()
    scale = db.query(LanguageScale).filter_by(code="CEFR").one()
    levels = {v.code: v.rank for v in db.query(LanguageLevel).filter_by(scale_id=scale.id)}

    def source(fact, thresholds, **arguments):
        return {"kind": "dossier_fact", "fact": fact, **arguments, "rules": [
            {"value": value, "points": points, "operator": "gte"} for value, points in thresholds]}

    sources = {
        3: ("Уровень образования", "Білім деңгейі", 15, source("education_level", [
            (education["BACHELOR"], 10), (education["MASTER"], 15)])),
        4: ("Подтверждённый английский язык", "Расталған ағылшын тілі", 20, source("language_level", [
            (levels["B1"], 5), (levels["B2"], 10), (levels["C1"], 15), (levels["C2"], 20)],
            argument=english.id, scale_id=scale.id)),
        5: ("Стаж в организации", "Ұйымдағы еңбек өтілі", 15, source("company_experience_years", [
            (3, 5), (5, 10), (10, 15)])),
    }
    criteria = []
    for row in template["criteria"]:
        criterion = {k: row[k] for k in ("id", "position", "section_key", "display_order", "name_ru",
                                         "name_kk", "max_points", "enabled", "source")}
        if row["position"] in sources:
            ru, kk, maximum, recipe = sources[row["position"]]
            criterion.update(name_ru=ru, name_kk=kk, max_points=maximum, source=recipe)
        criteria.append(criterion)
    methodology.update_method(db, draft.id, CandidateMethodologyIn(expected_revision=draft.revision,
        name_ru="Оценка по данным личного дела", name_kk="Жеке іс деректері бойынша бағалау",
        sections=template["sections"], criteria=criteria), ACTOR)
    methodology.activate_method(db, draft.id, draft.revision, ACTOR)
    for person in people:
        previous = db.query(CandidateEvaluation).filter_by(employee_id=person.id, methodology_id=original.id).one()
        scores = {score.criterion.position: score.points for score in previous.scores}
        applicable = methodology.applicable(draft.criteria, previous.technical_profile, True)
        payload = CandidateEvaluationIn(methodology_id=draft.id, expected_revision=0,
            technical_profile=previous.technical_profile, scores=[{"position": c.position, "points": scores[c.position]}
            for c in applicable if not c.source], note="Учебная оценка по синтетическим данным.")
        preview = candidate_sources.preview(db, person.id, payload)
        if not preview["summary"]["complete"]:
            raise RuntimeError("Пример оценки не заполнен; подготовка отменена.")
        payload.confirm_sources = True
        payload.source_fingerprint = preview["source_fingerprint"]
        methodology.save_evaluation(db, person.id, payload, ACTOR)
    return draft


def _seed_career_examples(db, people):
    profiles = {p.personnel_number: p for p in people}
    today = date.today()
    request = Request({"type": "http", "headers": [], "query_string": b""})
    request.state.user = {"role": "admin", "sub": ACTOR}
    for record in (
        PersonnelRecordIn(kind="contract", title="Срочный контракт", event_date=today - timedelta(days=90),
                          end_date=today + timedelta(days=180)),
        PersonnelRecordIn(kind="rank", title="Специалист I класса", event_date=today - timedelta(days=120),
                          planned_date=today + timedelta(days=90)),
        PersonnelRecordIn(kind="recognition", title="Благодарность за обучение коллег", event_date=today - timedelta(days=45)),
    ):
        create_record(profiles["DEMO-001"].id, record, request, db)
    create_appointment(profiles["DEMO-002"].id, {
        "appointment_type": "disposal", "effective_date": today - timedelta(days=6),
        "reason": "Учебный пример вывода в распоряжение",
    }, request, db)


def _seed(db, accounts):
    seed_reference(db)
    seed_org(db)
    seed_methodology(db)
    people = seed_demo_candidates(db)
    _seed_career_examples(db, people)
    method = _create_dossier_method(db, people)
    for example in EXAMPLES:
        country_code = example["country"]
        country = db.query(Country).filter_by(code=country_code).one()
        unit = db.query(OrgUnit).filter_by(code="FOREIGN_" + country_code).one()
        fields = {k: v for k, v in example.items() if k != "country"}
        db.add(Vacancy(**fields, country_id=country.id, org_unit_id=unit.id,
                       candidate_methodology_id=method.id, requirements_version=1, status="active"))
    db.add_all(accounts)
    db.flush()


def bootstrap_demo():
    with engine.begin() as connection:
        _check_database(connection)
        connection.execute(text("SELECT pg_advisory_xact_lock(61652024)"))
        if _is_ready(connection):
            return False
        # Refuse other people's objects in any user schema, even if there are no employees.
        # Extension-owned objects installed by the PostgreSQL provider are allowed.
        occupied = connection.scalar(text("""
            SELECT EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname <> 'information_schema' AND left(n.nspname, 3) <> 'pg_'
                AND c.relkind IN ('r','p','v','m','f','S')
                AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.classid='pg_class'::regclass
                    AND d.objid=c.oid AND d.deptype='e'))
        """))
        if occupied:
            raise RuntimeError("В базе уже есть объекты без метки Render-демо. Для первого запуска нужна пустая БД.")
        accounts = _accounts()
        # The stock seed helpers commit individual stages. Their commits release savepoints,
        # while all tables, data and the completion marker belong to this single outer transaction.
        Base.metadata.create_all(connection)
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            _seed(db, accounts)
            run_migrations(db)
            db.commit()
        connection.execute(text(f"CREATE TABLE {MARKER_TABLE} (fixture text PRIMARY KEY)"))
        connection.execute(text(f"INSERT INTO {MARKER_TABLE} (fixture) VALUES (:marker)"), {"marker": MARKER})
    return True


if __name__ == "__main__":
    created = bootstrap_demo()
    print("Созданы 15 синтетических профилей и 3 вакансии." if created else "Демонстрационная база уже подготовлена.")
