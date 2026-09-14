"""Seed reference data, methodology v1.0 and the specification's Austria case.

Run:  python seed_data.py
"""

from datetime import date
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from models import (
    Base, Country, Nationality, Language, LanguageScale, LanguageLevel,
    EducationLevel, EducationField, JobFamily, OrgUnitType, PositionGrade,
    TrainingType, AssessmentScale, CompetencyCategory, Competency,
    RequirementType, OrgUnit, Position,
    Employee, EmployeeEducation, EmployeeLanguage, EmployeeTraining,
    WorkExperience, AssessmentSession, CompetencyScore,
    ScoringModel, ScoringFunction, CompensationTable, ReadinessBand,
    PositionProfile, Vacancy, Requirement,
)
from services.metrics import persist_employee_metrics
from seed_catalogs import COUNTRIES, REQUIREMENT_TYPES


def upsert(db: Session, model, code: str, **fields):
    row = db.query(model).filter(model.code == code).first()
    if row:
        return row
    row = model(code=code, **fields)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------

def seed_reference(db: Session):
    # -- countries ---------------------------------------------------------
    for code, ru, kk, en in COUNTRIES:
        upsert(db, Country, code, name_ru=ru, name_kk=kk, name_en=en)

    for code, ru, kk, en in [
        ("KAZ", "Казах", "Қазақ", "Kazakh"),
        ("RUS", "Русский", "Орыс", "Russian"),
        ("OTH", "Другая", "Басқа", "Other"),
    ]:
        upsert(db, Nationality, code, name_ru=ru, name_kk=kk, name_en=en)

    # -- languages ---------------------------------------------------------
    for code, ru, kk, en in [
        ("EN", "Английский", "Ағылшын", "English"),
        ("DE", "Немецкий", "Неміс", "German"),
        ("KK", "Казахский", "Қазақ тілі", "Kazakh"),
        ("RU", "Русский", "Орыс тілі", "Russian"),
        ("FR", "Французский", "Француз", "French"),
    ]:
        upsert(db, Language, code, name_ru=ru, name_kk=kk, name_en=en)

    cefr = upsert(db, LanguageScale, "CEFR",
                  name_ru="CEFR", name_kk="CEFR", name_en="CEFR")
    # Exactly six levels. "B3" is absent, so it can never be stored.
    for rank, lvl in enumerate(["A1", "A2", "B1", "B2", "C1", "C2"], start=1):
        if not db.query(LanguageLevel).filter(
            LanguageLevel.scale_id == cefr.id, LanguageLevel.code == lvl
        ).first():
            db.add(LanguageLevel(scale_id=cefr.id, code=lvl, rank=rank,
                                 name_ru=lvl, name_kk=lvl, name_en=lvl))
    db.flush()

    # -- education ---------------------------------------------------------
    for rank, (code, ru, kk, en) in enumerate([
        ("SECONDARY", "Среднее", "Орта", "Secondary"),
        ("VOCATIONAL", "Среднее профессиональное", "Орта кәсіптік", "Vocational"),
        ("BACHELOR", "Высшее (бакалавр)", "Жоғары (бакалавр)", "Higher (Bachelor)"),
        ("MASTER", "Магистратура", "Магистратура", "Master"),
        ("PHD", "Докторантура", "Докторантура", "Doctorate"),
    ], start=1):
        upsert(db, EducationLevel, code, name_ru=ru, name_kk=kk, name_en=en, rank=rank)

    # -- job families ------------------------------------------------------
    families = {}
    for code, ru, kk, en in [
        ("MARKETING", "Маркетинг", "Маркетинг", "Marketing"),
        ("ANALYTICS", "Аналитика", "Аналитика", "Analytics"),
        ("FINANCE", "Финансы", "Қаржы", "Finance"),
        ("IT", "ИТ", "АТ", "IT"),
        ("HR", "Управление персоналом", "Персоналды басқару", "HR"),
        ("LEGAL", "Юридическое", "Заң", "Legal"),
        ("PROCUREMENT", "Закупки", "Сатып алу", "Procurement"),
        ("OPERATIONS", "Операционная деятельность", "Операциялық қызмет", "Operations"),
    ]:
        families[code] = upsert(db, JobFamily, code, name_ru=ru, name_kk=kk, name_en=en)

    # Marketing Analytics is a child of Analytics, so it credits both.
    upsert(db, JobFamily, "MARKETING_ANALYTICS",
           name_ru="Маркетинговая аналитика", name_kk="Маркетингтік аналитика",
           name_en="Marketing Analytics", parent_id=families["ANALYTICS"].id)

    for code, ru, kk, en, family in [
        ("MARKETING", "Маркетинг", "Маркетинг", "Marketing", "MARKETING"),
        ("ANALYTICS", "Аналитика данных", "Деректер аналитикасы", "Data Analytics", "ANALYTICS"),
        ("FINANCE", "Финансы", "Қаржы", "Finance", "FINANCE"),
        ("CS", "Информатика", "Информатика", "Computer Science", "IT"),
    ]:
        upsert(db, EducationField, code, name_ru=ru, name_kk=kk, name_en=en,
               job_family_id=families[family].id)

    # -- organisation ------------------------------------------------------
    for code, ru, kk, en in [
        ("HQ", "Головной офис", "Бас кеңсе", "Headquarters"),
        ("REGIONAL", "Региональное подразделение", "Аймақтық бөлімше", "Regional"),
        ("FOREIGN", "Зарубежный филиал", "Шетелдік филиал", "Foreign Branch"),
        ("SUBSIDIARY", "Дочерняя организация", "Еншілес ұйым", "Subsidiary"),
        ("OTHER", "Иное", "Өзге", "Other"),
    ]:
        upsert(db, OrgUnitType, code, name_ru=ru, name_kk=kk, name_en=en)

    for rank, (code, ru, kk, en) in enumerate([
        ("SPECIALIST", "Специалист", "Маман", "Specialist"),
        ("SENIOR", "Ведущий специалист", "Жетекші маман", "Senior Specialist"),
        ("MANAGER", "Руководитель", "Басшы", "Manager"),
        ("DIRECTOR", "Директор", "Директор", "Director"),
    ], start=1):
        upsert(db, PositionGrade, code, name_ru=ru, name_kk=kk, name_en=en, rank=rank)

    for code, ru, kk, en in [
        ("COURSE", "Курс повышения квалификации", "Біліктілікті арттыру курсы", "Course"),
        ("CERT", "Сертификация", "Сертификаттау", "Certification"),
        ("INTERNAL", "Внутреннее обучение", "Ішкі оқыту", "Internal training"),
    ]:
        upsert(db, TrainingType, code, name_ru=ru, name_kk=kk, name_en=en)

    # -- assessment scales & competencies ---------------------------------
    upsert(db, AssessmentScale, "1-5", name_ru="Шкала 1–5", name_kk="1–5 шкаласы",
           name_en="Scale 1-5", min_value=1, max_value=5, step=0.1)
    upsert(db, AssessmentScale, "0-10", name_ru="Шкала 0–10", name_kk="0–10 шкаласы",
           name_en="Scale 0-10", min_value=0, max_value=10, step=0.1)

    prof = upsert(db, CompetencyCategory, "PROFESSIONAL",
                  name_ru="Профессиональные качества",
                  name_kk="Кәсіби қасиеттер",
                  name_en="Professional qualities", is_confidential=False)
    psych = upsert(db, CompetencyCategory, "PSYCHOLOGICAL",
                   name_ru="Психологические характеристики",
                   name_kk="Психологиялық сипаттамалар",
                   name_en="Psychological characteristics", is_confidential=True)

    for order, (code, ru, kk, en) in enumerate([
        ("LEADERSHIP", "Лидерство", "Көшбасшылық", "Leadership"),
        ("DECISION_MAKING", "Принятие решений", "Шешім қабылдау", "Decision making"),
        ("PROBLEM_SOLVING", "Решение проблем", "Мәселелерді шешу", "Problem solving"),
        ("PLANNING", "Планирование", "Жоспарлау", "Planning"),
        ("TEAMWORK", "Работа в команде", "Командада жұмыс", "Teamwork"),
        ("INNOVATION", "Внедрение инноваций", "Инновацияларды енгізу", "Innovation"),
    ], start=1):
        upsert(db, Competency, code, name_ru=ru, name_kk=kk, name_en=en,
               category_id=prof.id, sort_order=order, is_active=True)

    for order, (code, ru, kk, en) in enumerate([
        ("COMMUNICATION", "Коммуникативность", "Коммуникативтілік", "Communication"),
        ("STRESS_RESISTANCE", "Стрессоустойчивость", "Стресске төзімділік", "Stress resistance"),
        ("RECEPTIVITY", "Восприимчивость", "Қабылдағыштық", "Receptivity"),
        ("TIME_MANAGEMENT", "Управление временем", "Уақытты басқару", "Time management"),
        ("LEARNING", "Способность к усвоению новых знаний", "Жаңа білім игеру қабілеті",
         "Learning ability"),
    ], start=1):
        upsert(db, Competency, code, name_ru=ru, name_kk=kk, name_en=en,
               category_id=psych.id, sort_order=order, is_active=True)

    # -- requirement types -------------------------------------------------
    # `condition_schema` is a FORM SPECIFICATION, not a raw JSON shape. The UI
    # renders real inputs from it, so an HR user never types JSON by hand.
    for code, ru, kk, en, handler, schema in REQUIREMENT_TYPES:
        row = db.query(RequirementType).filter(RequirementType.code == code).first()
        if row:
            # Keep schemas current when this seed is re-run after an upgrade.
            row.name_ru, row.name_kk, row.name_en = ru, kk, en
            row.handler, row.condition_schema = handler, schema
        else:
            db.add(RequirementType(code=code, name_ru=ru, name_kk=kk, name_en=en,
                                   handler=handler, condition_schema=schema))

    db.commit()


# ---------------------------------------------------------------------------

def seed_org(db: Session):
    kz = db.query(Country).filter(Country.code == "KZ").first()
    at = db.query(Country).filter(Country.code == "AT").first()
    types = {t.code: t for t in db.query(OrgUnitType).all()}
    families = {f.code: f for f in db.query(JobFamily).all()}
    grades = {g.code: g for g in db.query(PositionGrade).all()}

    hq = upsert(db, OrgUnit, "HQ", name_ru="Головной офис", name_kk="Бас кеңсе",
                name_en="Headquarters", country_id=kz.id, region="Астана",
                unit_type_id=types["HQ"].id)
    upsert(db, OrgUnit, "ALMATY", name_ru="Алматинский региональный филиал",
           name_kk="Алматы аймақтық филиалы", name_en="Almaty Regional Branch",
           country_id=kz.id, region="Алматы", parent_id=hq.id,
           unit_type_id=types["REGIONAL"].id)
    upsert(db, OrgUnit, "VIENNA", name_ru="Филиал в Австрии",
           name_kk="Австриядағы филиал", name_en="Austria Branch",
           country_id=at.id, region="Вена", parent_id=hq.id,
           unit_type_id=types["FOREIGN"].id)

    for code, ru, kk, en, family, grade in [
        ("MKT_SPEC", "Маркетолог", "Маркетолог", "Marketing Specialist",
         "MARKETING", "SPECIALIST"),
        ("MKT_SENIOR", "Ведущий маркетолог", "Жетекші маркетолог",
         "Senior Marketing Specialist", "MARKETING", "SENIOR"),
        ("MKT_MANAGER", "Менеджер по маркетингу", "Маркетинг менеджері",
         "Marketing Manager", "MARKETING", "MANAGER"),
        ("ANALYST", "Аналитик", "Аналитик", "Analyst", "ANALYTICS", "SPECIALIST"),
        ("OPS_SPEC", "Специалист по операциям", "Операциялар маманы",
         "Operations Specialist", "OPERATIONS", "SPECIALIST"),
    ]:
        upsert(db, Position, code, name_ru=ru, name_kk=kk, name_en=en,
               job_family_id=families[family].id, grade_id=grades[grade].id)

    db.commit()


# ---------------------------------------------------------------------------

def seed_methodology(db: Session):
    model = db.query(ScoringModel).filter(ScoringModel.version == "1.0").first()
    if not model:
        model = ScoringModel(
            version="1.0",
            name="Базовая методология подбора",
            description="Ступенчатые функции соответствия и компенсации "
                        "согласно постановке задачи.",
            status="draft",
        )
        db.add(model)
        db.flush()

    def add_fn(code, ru, kk, en, kind, breakpoints):
        if db.query(ScoringFunction).filter(
            ScoringFunction.model_id == model.id, ScoringFunction.code == code
        ).first():
            return
        db.add(ScoringFunction(model_id=model.id, code=code, name_ru=ru,
                               name_kk=kk, name_en=en, kind=kind,
                               breakpoints=breakpoints))

    # The specification's step function: 3+ y -> 1.0, 2-3 -> 0.75,
    # 1-2 -> 0.40, under 1 -> 0. Expressed as ratios of the requirement.
    add_fn("EXPERIENCE_STEP", "Ступенчатая: стаж", "Сатылы: өтіл",
           "Stepped: experience", "step_ratio", [
               {"min_ratio": 1.0, "m": 1.0},
               {"min_ratio": 0.67, "m": 0.75},
               {"min_ratio": 0.33, "m": 0.40},
               {"min_ratio": 0.0, "m": 0.0},
           ])
    add_fn("PRESENCE", "Наличие признака", "Белгінің болуы", "Presence",
           "boolean", [])
    add_fn("LANGUAGE_LEVEL", "Уровень языка", "Тіл деңгейі", "Language level",
           "level_scale", [{"min_gap": 1, "m": 0.5}, {"min_gap": 2, "m": 0.0}])
    add_fn("COMPETENCY_LINEAR", "Компетенция (линейная)", "Құзыреттілік (сызықтық)",
           "Competency (linear)", "step_ratio", [
               {"min_ratio": 1.0, "m": 1.0},
               {"min_ratio": 0.85, "m": 0.6},
               {"min_ratio": 0.0, "m": 0.0},
           ])

    if not db.query(CompensationTable).filter(
        CompensationTable.model_id == model.id,
        CompensationTable.code == "ANALYTICS_COMPENSATION"
    ).first():
        db.add(CompensationTable(
            model_id=model.id, code="ANALYTICS_COMPENSATION",
            name_ru="Компенсация опыта аналитики",
            name_kk="Аналитика тәжірибесінің өтемақысы",
            name_en="Analytics experience compensation",
            entries=[
                {"code": "direct_experience", "m": 1.00,
                 "label_ru": "Прямой опыт аналитиком"},
                {"code": "relevant_education", "m": 0.75,
                 "label_ru": "Профильное образование"},
                {"code": "education_and_training", "m": 0.80,
                 "label_ru": "Профильное образование и курс"},
                {"code": "training_only", "m": 0.30,
                 "label_ru": "Только курсы повышения квалификации"},
                {"code": "none", "m": 0.0, "label_ru": "Компенсация отсутствует"},
            ],
        ))

    for code, ru, kk, en, min_score, color in [
        ("READY_NOW", "Готов сейчас", "Қазір дайын", "Ready now", 90, "#1a7f37"),
        ("READY_6M", "Готов ≤ 6 мес.", "≤ 6 айда дайын", "Ready ≤ 6 months", 80, "#2da44e"),
        ("READY_12M", "Готов 6–12 мес.", "6–12 айда дайын", "Ready 6-12 months", 70, "#bf8700"),
        ("DEVELOPMENT", "Развитие 12–24 мес.", "Дамыту 12–24 ай",
         "Development 12-24 months", 60, "#d1242f"),
        ("LONG_TERM", "Долгосрочный потенциал", "Ұзақ мерзімді әлеует",
         "Long-term potential", 0, "#6e7781"),
    ]:
        if not db.query(ReadinessBand).filter(
            ReadinessBand.model_id == model.id, ReadinessBand.code == code
        ).first():
            db.add(ReadinessBand(model_id=model.id, code=code, name_ru=ru,
                                 name_kk=kk, name_en=en, min_score=min_score,
                                 color=color))

    db.commit()

    model.status = "approved"
    model.approved_by = "hr_methodologist"
    # Exactly one model may be the default: clear the flag everywhere else
    # first, or a re-run leaves two rows marked and the matching engine picks
    # between them arbitrarily.
    db.query(ScoringModel).filter(ScoringModel.id != model.id).update(
        {ScoringModel.is_default: False})
    model.is_default = True
    db.commit()
    return model


# ---------------------------------------------------------------------------

CANDIDATES = [
    # letter, last, first, hire, career rows, languages, leadership
    ("А", "Абенова", "Айгүль", date(2018, 9, 1), [
        ("ALMATY", "ANALYST", "ANALYTICS", "REGIONAL", "KZ", date(2018, 9, 1), date(2021, 8, 31)),
        ("HQ", "MKT_SENIOR", "MARKETING", "HQ", "KZ", date(2021, 9, 1), date(2024, 8, 31)),
        ("VIENNA", "MKT_SENIOR", "MARKETING", "FOREIGN", "AT", date(2024, 9, 1), None),
    ], [("EN", "C1"), ("DE", "B2")], 4.5, None),

    ("Б", "Бекжанов", "Бекзат", date(2019, 9, 1), [
        ("ALMATY", "ANALYST", "ANALYTICS", "REGIONAL", "KZ", date(2019, 9, 1), date(2022, 8, 31)),
        ("HQ", "MKT_SENIOR", "MARKETING", "HQ", "KZ", date(2022, 9, 1), None),
    ], [("EN", "C1")], 4.2, None),

    ("В", "Вагнер", "Вера", date(2020, 9, 1), [
        ("ALMATY", "OPS_SPEC", "OPERATIONS", "REGIONAL", "KZ", date(2020, 9, 1), date(2023, 8, 31)),
        ("HQ", "MKT_SPEC", "MARKETING", "HQ", "KZ", date(2023, 9, 1), None),
    ], [("DE", "C1")], 3.8, "ANALYTICS_COURSE"),

    ("Г", "Ғабитова", "Гүлназ", date(2017, 9, 1), [
        ("ALMATY", "ANALYST", "ANALYTICS", "REGIONAL", "KZ", date(2017, 9, 1), date(2022, 8, 31)),
        ("VIENNA", "MKT_SENIOR", "MARKETING", "FOREIGN", "AT", date(2022, 9, 1), None),
    ], [("EN", "B2")], 4.0, None),

    ("Д", "Дәулетов", "Дамир", date(2020, 9, 1), [
        ("HQ", "ANALYST", "ANALYTICS", "HQ", "KZ", date(2020, 9, 1), date(2021, 8, 31)),
        ("HQ", "MKT_SENIOR", "MARKETING", "HQ", "KZ", date(2021, 9, 1), date(2024, 8, 31)),
        ("VIENNA", "MKT_SENIOR", "MARKETING", "FOREIGN", "AT", date(2024, 9, 1), None),
    ], [("EN", "C1")], 3.9, None),
]


def seed_employees(db: Session):
    countries = {c.code: c for c in db.query(Country).all()}
    units = {u.code: u for u in db.query(OrgUnit).all()}
    positions = {p.code: p for p in db.query(Position).all()}
    families = {f.code: f for f in db.query(JobFamily).all()}
    unit_types = {t.code: t for t in db.query(OrgUnitType).all()}
    languages = {l.code: l for l in db.query(Language).all()}
    cefr = db.query(LanguageScale).filter(LanguageScale.code == "CEFR").first()
    levels = {l.code: l for l in db.query(LanguageLevel).filter(
        LanguageLevel.scale_id == cefr.id).all()}
    edu_levels = {e.code: e for e in db.query(EducationLevel).all()}
    edu_fields = {e.code: e for e in db.query(EducationField).all()}
    scale_1_5 = db.query(AssessmentScale).filter(AssessmentScale.code == "1-5").first()
    kz_nat = db.query(Nationality).filter(Nationality.code == "KAZ").first()
    training_type = db.query(TrainingType).filter(TrainingType.code == "COURSE").first()

    professional = [c for c in db.query(Competency).join(CompetencyCategory).filter(
        CompetencyCategory.code == "PROFESSIONAL").all()]

    for idx, (letter, last, first, hire, career, langs, leadership, extra) \
            in enumerate(CANDIDATES, start=1):

        if db.query(Employee).filter(Employee.personnel_number == f"TN-{idx:04d}").first():
            continue

        employee = Employee(
            personnel_number=f"TN-{idx:04d}",
            anonymous_code=letter,
            last_name=last,
            first_name=first,
            birth_date=date(1988 + idx, 3, 12),
            birth_place="Алматы" if idx % 2 else "Астана",
            birth_country_id=countries["KZ"].id,
            nationality_id=kz_nat.id if kz_nat else None,
            email=f"candidate{idx}@company.kz",
            phone=f"+7 701 000 00{idx:02d}",
            hire_date=hire,
            current_org_unit_id=units[career[-1][0]].id,
            current_position_id=positions[career[-1][1]].id,
            employment_status="active",
            profile_status="verified",
        )
        db.add(employee)
        db.flush()

        # education
        db.add(EmployeeEducation(
            employee_id=employee.id,
            level_id=edu_levels["BACHELOR"].id,
            institution="Казахский национальный университет",
            country_id=countries["KZ"].id,
            field_id=edu_fields["MARKETING"].id,
            start_year=hire.year - 5, end_year=hire.year - 1,
            qualification="Бакалавр",
        ))

        # career history -- the source of every tenure figure
        for unit_code, pos_code, family_code, unit_type, country, start, end in career:
            db.add(WorkExperience(
                employee_id=employee.id,
                is_internal=True,
                org_unit_id=units[unit_code].id,
                position_id=positions[pos_code].id,
                job_family_id=families[family_code].id,
                org_unit_type_id=unit_types[unit_type].id,
                country_id=countries[country].id,
                date_from=start, date_to=end,
            ))

        # languages
        for lang_code, level_code in langs:
            db.add(EmployeeLanguage(
                employee_id=employee.id,
                language_id=languages[lang_code].id,
                scale_id=cefr.id,
                level_id=levels[level_code].id,
                is_confirmed=True,
                document="IELTS" if lang_code == "EN" else "Goethe-Zertifikat",
                confirmed_at=date(2025, 5, 14),
                valid_until=date(2028, 5, 14),
            ))

        # Candidate В has no analytics job history, only a recent course --
        # this is the compensation case from the specification.
        if extra == "ANALYTICS_COURSE":
            db.add(EmployeeTraining(
                employee_id=employee.id,
                name="Business Analytics",
                training_type_id=training_type.id if training_type else None,
                job_family_id=families["ANALYTICS"].id,
                provider="Corporate University",
                date_from=date(2026, 2, 1), date_to=date(2026, 5, 30),
                result="Завершено",
            ))

        # professional assessment
        session = AssessmentSession(
            employee_id=employee.id,
            session_type="professional",
            scale_id=scale_1_5.id,
            session_date=date(2026, 6, 15),
            assessor="Руководитель подразделения",
            conclusion_text="Показывает устойчивые результаты, инициативен.",
        )
        db.add(session)
        db.flush()
        for competency in professional:
            score = leadership if competency.code == "LEADERSHIP" else round(
                min(5.0, leadership - 0.2 + (competency.sort_order % 3) * 0.15), 2)
            db.add(CompetencyScore(session_id=session.id,
                                   competency_id=competency.id, score=score))

        db.commit()
        persist_employee_metrics(db, employee)


# ---------------------------------------------------------------------------

def seed_vacancy(db: Session, model: ScoringModel):
    if db.query(Vacancy).filter(Vacancy.title.like("%Австри%")).first():
        return

    at = db.query(Country).filter(Country.code == "AT").first()
    vienna = db.query(OrgUnit).filter(OrgUnit.code == "VIENNA").first()
    marketing = db.query(JobFamily).filter(JobFamily.code == "MARKETING").first()
    manager_grade = db.query(PositionGrade).filter(
        PositionGrade.code == "MANAGER").first()

    profile = upsert(db, PositionProfile, "MKT_MANAGER_INTL",
                     name_ru="Менеджер по маркетингу (международный)",
                     name_kk="Маркетинг менеджері (халықаралық)",
                     name_en="Marketing Manager (International)",
                     job_family_id=marketing.id,
                     grade_id=manager_grade.id if manager_grade else None)
    db.commit()

    vacancy = Vacancy(
        profile_id=profile.id,
        title="Менеджер по маркетингу — Австрия",
        country_id=at.id,
        org_unit_id=vienna.id if vienna else None,
        description="Открыта вакансия в филиале компании в Австрии.",
        status="draft",
    )
    db.add(vacancy)
    db.flush()

    types = {t.code: t for t in db.query(RequirementType).all()}
    fns = {f.code: f for f in db.query(ScoringFunction).filter(
        ScoringFunction.model_id == model.id).all()}
    comp = db.query(CompensationTable).filter(
        CompensationTable.model_id == model.id,
        CompensationTable.code == "ANALYTICS_COMPENSATION").first()

    rows = [
        ("COMPANY_TENURE", "Стаж в компании ≥ 5 лет", "Компаниядағы өтіл ≥ 5 жыл",
         "Company tenure ≥ 5 years", {"min_years": 5}, 15, "must",
         "EXPERIENCE_STEP", None),

        ("FUNCTION_EXPERIENCE", "Опыт в маркетинге ≥ 3 лет",
         "Маркетингтегі тәжірибе ≥ 3 жыл", "Marketing experience ≥ 3 years",
         {"job_family_code": "MARKETING", "min_years": 3}, 20, "must",
         "EXPERIENCE_STEP", None),

        ("LANGUAGE", "Английский или немецкий ≥ B2",
         "Ағылшын немесе неміс ≥ B2", "English or German ≥ B2",
         {"any_of": [{"language_code": "EN", "min_level": "B2", "confirmed": True},
                     {"language_code": "DE", "min_level": "B2", "confirmed": True}]},
         20, "critical", "LANGUAGE_LEVEL", None),

        ("FUNCTION_EXPERIENCE", "Опыт в аналитике ≥ 2 лет",
         "Аналитикадағы тәжірибе ≥ 2 жыл", "Analytics experience ≥ 2 years",
         {"job_family_code": "ANALYTICS", "min_years": 2}, 15, "must",
         "EXPERIENCE_STEP", "ANALYTICS_COMPENSATION"),

        ("ORG_UNIT_EXPERIENCE", "Опыт работы в регионах",
         "Аймақтардағы жұмыс тәжірибесі", "Regional experience",
         {"org_unit_type_code": "REGIONAL", "min_years": 0}, 10, "must",
         "PRESENCE", None),

        ("ORG_UNIT_EXPERIENCE", "Опыт работы в головном офисе",
         "Бас кеңседегі жұмыс тәжірибесі", "Headquarters experience",
         {"org_unit_type_code": "HQ", "min_years": 0}, 8, "nice",
         "PRESENCE", None),

        ("ORG_UNIT_EXPERIENCE", "Опыт в зарубежных филиалах",
         "Шетелдік филиалдардағы тәжірибе", "Foreign branch experience",
         {"org_unit_type_code": "FOREIGN", "min_years": 0}, 7, "nice",
         "PRESENCE", None),

        ("COMPETENCY", "Лидерство ≥ 3,5", "Көшбасшылық ≥ 3,5",
         "Leadership ≥ 3.5", {"competency_code": "LEADERSHIP", "min_score": 3.5},
         5, "nice", "COMPETENCY_LINEAR", None),
    ]

    for order, (type_code, ru, kk, en, condition, weight, crit, fn_code, comp_code) \
            in enumerate(rows, start=1):
        db.add(Requirement(
            vacancy_id=vacancy.id,
            requirement_type_id=types[type_code].id,
            label_ru=ru, label_kk=kk, label_en=en,
            condition=condition, weight=weight, criticality=crit,
            scoring_function_id=fns[fn_code].id if fn_code in fns else None,
            compensation_table_id=comp.id if (comp_code and comp) else None,
            sort_order=order,
        ))

    vacancy.status = "active"
    db.commit()


# ---------------------------------------------------------------------------

def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Reference data ...")
        seed_reference(db)
        print("Organisation ...")
        seed_org(db)
        print("Methodology v1.0 ...")
        model = seed_methodology(db)
        print("Employees (candidates А-Д) ...")
        seed_employees(db)
        print("Vacancy: Marketing Manager - Austria ...")
        seed_vacancy(db, model)
        print("\nDone. Weights total 100; scoring model 1.0 approved and default.")
    except Exception as exc:                                     # noqa: BLE001
        db.rollback()
        print(f"FAILED: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
