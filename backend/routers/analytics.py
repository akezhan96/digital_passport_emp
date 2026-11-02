"""Analytics: answering headcount questions about the workforce.

"How many employees hold a higher degree?", "How many speak German or English
at B2 or above?", "How is readiness distributed for this vacancy?"

Each question is declared once, with a form specification the UI renders into
real inputs -- the same pattern the requirement builder uses, so a question is
configured rather than coded. Every answer returns three things: a headline
number, a breakdown, and the matching people (pseudonymised unless names are
deliberately revealed, which is audited).

Available to both roles: analysis is precisely what the viewer account is for.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from auth import current_user
from models import (
    Employee, EmployeeEducation, EmployeeLanguage, EmployeeTraining,
    WorkExperience, EducationLevel, Language, LanguageLevel, JobFamily,
    OrgUnit, OrgUnitType, Country, Competency, AuditLog,
    MatchingRun, MatchingResult, Vacancy,
)
from services.metrics import compute_employee_metrics, compute_metrics_bulk
from services.employee_ranking import RankingFilters, employee_ranking

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.post("/employee-ranking")
def rank_employees(payload: RankingFilters, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    result = employee_ranking(db, payload, include_confidential=user['role'] == 'admin')
    if payload.reveal_names and result['items']:
        db.add(AuditLog(action='reveal_identities', entity_type='analytics_query',
                        changed_by=user['sub'], new_values={
                            'query': 'employee_ranking', 'methodology_id': result['methodology']['id'],
                            'org_unit_id': payload.org_unit_id, 'include_subunits': payload.include_subunits,
                            'employee_ids': [item['employee_id'] for item in result['items']]}))
        db.commit()
    return result


# ---------------------------------------------------------------------------
# Question catalogue -- declared as data, rendered by the UI
# ---------------------------------------------------------------------------

def _ref(key, catalog, ru, kk, en, required=True, multiple=False):
    return {"key": key, "kind": "ref", "catalog": catalog, "value_field": "code",
            "required": required, "multiple": multiple,
            "label_ru": ru, "label_kk": kk, "label_en": en}


def _num(key, ru, kk, en, default=0, step=0.5, required=False,
         suffix=("лет", "жыл", "years")):
    return {"key": key, "kind": "number", "required": required,
            "label_ru": ru, "label_kk": kk, "label_en": en,
            "min": 0, "step": step, "default": default,
            "suffix_ru": suffix[0], "suffix_kk": suffix[1], "suffix_en": suffix[2]}


QUESTIONS: List[Dict[str, Any]] = [
    {
        "code": "education_level",
        "name_ru": "Сколько сотрудников с образованием не ниже уровня",
        "name_kk": "Білім деңгейі кемінде болатын қызметкерлер саны",
        "name_en": "Employees holding at least this level of education",
        "hint_ru": "Учитывается высший из имеющихся уровней образования.",
        "hint_kk": "Бар білім деңгейлерінің ең жоғарысы ескеріледі.",
        "hint_en": "The highest level the person holds is used.",
        "fields": [_ref("min_level_code", "education-levels",
                        "Минимальный уровень", "Ең төменгі деңгей",
                        "Minimum level")],
        "group_by_ru": "Уровень образования",
    },
    {
        "code": "language_knowledge",
        "name_ru": "Сколько сотрудников владеют языком",
        "name_kk": "Тілді меңгерген қызметкерлер саны",
        "name_en": "Employees who speak a language",
        "hint_ru": "Достаточно владения любым из выбранных языков. "
                   "Просроченные сертификаты не засчитываются.",
        "hint_kk": "Таңдалған тілдердің кез келгенін білу жеткілікті. "
                   "Мерзімі өткен сертификаттар есептелмейді.",
        "hint_en": "Knowing any one of the chosen languages is enough. "
                   "Expired certificates do not count.",
        "fields": [
            _ref("language_codes", "languages", "Языки (любой из)",
                 "Тілдер (кез келгені)", "Languages (any of)", multiple=True),
            _ref("min_level", "language-levels", "Минимальный уровень",
                 "Ең төменгі деңгей", "Minimum level", required=False),
            {"key": "confirmed_only", "kind": "boolean", "default": True,
             "label_ru": "Только подтверждённые документом",
             "label_kk": "Тек құжатпен расталған",
             "label_en": "Confirmed by a document only"},
        ],
        "group_by_ru": "Язык",
    },
    {
        "code": "company_tenure",
        "name_ru": "Сколько сотрудников со стажем в компании не менее",
        "name_kk": "Компаниядағы өтілі кемінде болатын қызметкерлер саны",
        "name_en": "Employees with at least this much company tenure",
        "hint_ru": "Стаж рассчитывается по объединённым интервалам карьеры.",
        "hint_kk": "Өтіл мансаптың біріктірілген аралықтары бойынша есептеледі.",
        "hint_en": "Tenure is computed from the union of career intervals.",
        "fields": [_num("min_years", "Минимальный стаж", "Ең аз өтіл",
                        "Minimum tenure", default=5, required=True)],
        "group_by_ru": "Диапазон стажа",
    },
    {
        "code": "function_experience",
        "name_ru": "Сколько сотрудников с опытом по функции",
        "name_kk": "Функция бойынша тәжірибесі бар қызметкерлер саны",
        "name_en": "Employees with experience in a professional function",
        "hint_ru": "Опыт считается по job family, а не по названию должности.",
        "hint_kk": "Тәжірибе лауазым атауы бойынша емес, job family бойынша.",
        "hint_en": "Counted by job family, not by job title.",
        "fields": [
            _ref("job_family_code", "job-families", "Профессиональная функция",
                 "Кәсіби функция", "Job family"),
            _num("min_years", "Минимальный опыт", "Ең аз тәжірибе",
                 "Minimum experience", default=3),
        ],
        "group_by_ru": "Функция",
    },
    {
        "code": "org_unit_experience",
        "name_ru": "Сколько сотрудников с опытом в типе подразделения",
        "name_kk": "Бөлімше түрінде тәжірибесі бар қызметкерлер саны",
        "name_en": "Employees with experience in a type of unit",
        "hint_ru": "Например, кто работал в зарубежных филиалах.",
        "hint_kk": "Мысалы, шетелдік филиалдарда жұмыс істегендер.",
        "hint_en": "For example, who has worked in foreign branches.",
        "fields": [
            _ref("org_unit_type_code", "org-unit-types", "Тип подразделения",
                 "Бөлімше түрі", "Unit type"),
            _num("min_years", "Минимальный опыт", "Ең аз тәжірибе",
                 "Minimum experience", default=0),
        ],
        "group_by_ru": "Тип подразделения",
    },
    {
        "code": "competency_threshold",
        "name_ru": "Сколько сотрудников с оценкой компетенции не ниже",
        "name_kk": "Құзыреттілік бағасы кемінде болатын қызметкерлер саны",
        "name_en": "Employees scoring at least this on a competency",
        "hint_ru": "Берётся балл из последней проведённой оценки.",
        "hint_kk": "Соңғы бағалаудың ұпайы алынады.",
        "hint_en": "The score from the most recent assessment is used.",
        "fields": [
            _ref("competency_code", "competencies", "Компетенция",
                 "Құзыреттілік", "Competency"),
            _num("min_score", "Минимальный балл", "Ең төменгі ұпай",
                 "Minimum score", default=3.5, step=0.1, required=True,
                 suffix=("балл", "ұпай", "points")),
        ],
        "group_by_ru": "Компетенция",
    },
    {
        "code": "training_recent",
        "name_ru": "Сколько сотрудников прошли обучение по направлению",
        "name_kk": "Бағыт бойынша оқудан өткен қызметкерлер саны",
        "name_en": "Employees who completed training in a discipline",
        "hint_ru": "Оставьте 0 месяцев, чтобы не ограничивать срок давности.",
        "hint_kk": "Мерзімді шектемеу үшін 0 ай қалдырыңыз.",
        "hint_en": "Leave 0 months to ignore how recent the course was.",
        "fields": [
            _ref("job_family_code", "job-families", "Направление обучения",
                 "Оқыту бағыты", "Discipline"),
            _num("within_months", "Пройдено не ранее чем", "Өткізілген мерзімі",
                 "Completed within", default=0, step=1,
                 suffix=("мес.", "ай", "months")),
        ],
        "group_by_ru": "Направление",
    },
    {
        "code": "headcount_by_unit",
        "name_ru": "Численность по подразделениям",
        "name_kk": "Бөлімшелер бойынша сан",
        "name_en": "Headcount by organisational unit",
        "hint_ru": "Распределение действующих сотрудников.",
        "hint_kk": "Жұмыс істеп тұрған қызметкерлердің таралуы.",
        "hint_en": "Distribution of active employees.",
        "fields": [],
        "group_by_ru": "Подразделение",
    },
    {
        "code": "profile_completeness",
        "name_ru": "Готовность данных: статусы профилей",
        "name_kk": "Деректердің дайындығы: профиль мәртебелері",
        "name_en": "Data readiness: profile statuses",
        "hint_ru": "Только подтверждённые профили участвуют в подборе.",
        "hint_kk": "Іріктеуге тек расталған профильдер қатысады.",
        "hint_en": "Only verified profiles take part in matching.",
        "fields": [],
        "group_by_ru": "Статус профиля",
    },
]

QUESTION_BY_CODE = {q["code"]: q for q in QUESTIONS}


@router.get("/questions")
def list_questions():
    """Every question the UI can offer, with its parameter form."""
    return {"data": QUESTIONS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active(db: Session) -> List[Employee]:
    return db.query(Employee).filter(Employee.employment_status == "active").all()


def _person(employee: Employee, reveal: bool) -> Dict[str, Any]:
    return {
        "id": employee.id,
        "code": employee.anonymous_code,
        "display_name": (employee.full_name if reveal
                         else (employee.anonymous_code or f"#{employee.id}")),
        "position": (employee.current_position.name_ru
                     if employee.current_position else None),
        "org_unit": (employee.current_org_unit.name_ru
                     if employee.current_org_unit else None),
        "profile_status": employee.profile_status,
        "position_kk": employee.current_position.name_kk if employee.current_position else None,
        "org_unit_kk": employee.current_org_unit.name_kk if employee.current_org_unit else None,
    }


def _tenure_band(years: float) -> str:
    if years < 1:
        return "< 1"
    if years < 3:
        return "1-3"
    if years < 5:
        return "3-5"
    if years < 10:
        return "5-10"
    return "10+"


# ---------------------------------------------------------------------------
# Handlers -- each returns (matched employees, breakdown)
# ---------------------------------------------------------------------------

def _q_education_level(db, employees, params):
    code = params.get("min_level_code")
    level = db.query(EducationLevel).filter(EducationLevel.code == code).first()
    if not level:
        raise HTTPException(422, "Укажите уровень образования")

    matched, breakdown = [], {}
    for employee in employees:
        best = None
        for row in employee.educations:
            if row.level and (best is None or row.level.rank > best.rank):
                best = row.level
        if best:
            breakdown[best.name_ru] = breakdown.get(best.name_ru, 0) + 1
        if best and best.rank >= level.rank:
            matched.append(employee)
    return matched, breakdown


def _q_language_knowledge(db, employees, params):
    codes = params.get("language_codes") or []
    if isinstance(codes, str):
        codes = [codes]
    if not codes:
        raise HTTPException(422, "Выберите хотя бы один язык")

    min_level = params.get("min_level")
    confirmed_only = params.get("confirmed_only", True)

    required_rank = 0
    if min_level:
        row = (db.query(LanguageLevel)
               .filter(LanguageLevel.code == min_level)
               .order_by(LanguageLevel.rank).first())
        required_rank = row.rank if row else 0

    today = date.today()

    matched, breakdown = [], {}
    for employee in employees:
        hit = False
        for row in employee.languages:
            if not row.language or row.language.code not in codes:
                continue
            if confirmed_only and not row.is_confirmed:
                continue
            if row.valid_until and row.valid_until < today:
                continue          # expired certificate does not count
            if row.level and row.level.rank >= required_rank:
                hit = True
                name = row.language.name_ru
                breakdown[name] = breakdown.get(name, 0) + 1
        if hit:
            matched.append(employee)
    return matched, breakdown


def _q_company_tenure(db, employees, params):
    minimum = float(params.get("min_years") or 0)
    all_metrics = compute_metrics_bulk(db, employees)
    matched, breakdown = [], {}
    for employee in employees:
        years = all_metrics.get(employee.id, {}).get(
            "company_experience_years", 0)
        band = _tenure_band(years)
        breakdown[band] = breakdown.get(band, 0) + 1
        if years >= minimum:
            matched.append(employee)
    return matched, breakdown


def _q_function_experience(db, employees, params):
    code = params.get("job_family_code")
    minimum = float(params.get("min_years") or 0)
    if not code:
        raise HTTPException(422, "Выберите профессиональную функцию")

    all_metrics = compute_metrics_bulk(db, employees)
    matched, breakdown = [], {}
    for employee in employees:
        metrics = all_metrics.get(employee.id, {})
        years = metrics.get(f"function_experience_years:{code}", 0)
        if years > 0:
            band = _tenure_band(years)
            breakdown[band] = breakdown.get(band, 0) + 1
        if years >= minimum and (years > 0 or minimum == 0):
            matched.append(employee)
    return matched, breakdown


def _q_org_unit_experience(db, employees, params):
    code = params.get("org_unit_type_code")
    minimum = float(params.get("min_years") or 0)
    if not code:
        raise HTTPException(422, "Выберите тип подразделения")

    all_metrics = compute_metrics_bulk(db, employees)
    matched, breakdown = [], {}
    for employee in employees:
        metrics = all_metrics.get(employee.id, {})
        years = metrics.get(f"org_unit_experience_years:{code}", 0)
        label = "есть опыт" if years > 0 else "нет опыта"
        breakdown[label] = breakdown.get(label, 0) + 1
        if years > 0 and years >= minimum:
            matched.append(employee)
    return matched, breakdown


def _q_competency_threshold(db, employees, params):
    code = params.get("competency_code")
    minimum = float(params.get("min_score") or 0)
    if not code:
        raise HTTPException(422, "Выберите компетенцию")

    all_metrics = compute_metrics_bulk(db, employees)
    matched, breakdown = [], {}
    for employee in employees:
        score = all_metrics.get(employee.id, {}).get(f"competency:{code}")
        if score is None:
            breakdown["нет оценки"] = breakdown.get("нет оценки", 0) + 1
            continue
        band = f"{int(score)}-{int(score) + 1}"
        breakdown[band] = breakdown.get(band, 0) + 1
        if score >= minimum:
            matched.append(employee)
    return matched, breakdown


def _q_training_recent(db, employees, params):
    code = params.get("job_family_code")
    months = int(params.get("within_months") or 0)
    if not code:
        raise HTTPException(422, "Выберите направление обучения")

        today = date.today()

    matched, breakdown = [], {}
    for employee in employees:
        hit = False
        for row in employee.trainings:
            if not row.job_family or row.job_family.code != code:
                continue
            if months and row.date_to and (today - row.date_to).days > months * 30:
                continue
            hit = True
            year = str(row.date_to.year) if row.date_to else "без даты"
            breakdown[year] = breakdown.get(year, 0) + 1
        if hit:
            matched.append(employee)
    return matched, breakdown


def _q_headcount_by_unit(db, employees, params):
    breakdown = {}
    for employee in employees:
        name = (employee.current_org_unit.name_ru
                if employee.current_org_unit else "не указано")
        breakdown[name] = breakdown.get(name, 0) + 1
    return employees, breakdown


def _q_profile_completeness(db, employees, params):
    labels = {"draft": "Черновик", "in_review": "На проверке",
              "verified": "Подтверждён", "archived": "В архиве"}
    breakdown = {}
    verified = []
    for employee in employees:
        label = labels.get(employee.profile_status, employee.profile_status)
        breakdown[label] = breakdown.get(label, 0) + 1
        if employee.profile_status == "verified":
            verified.append(employee)
    return verified, breakdown


HANDLERS = {
    "education_level": _q_education_level,
    "language_knowledge": _q_language_knowledge,
    "company_tenure": _q_company_tenure,
    "function_experience": _q_function_experience,
    "org_unit_experience": _q_org_unit_experience,
    "competency_threshold": _q_competency_threshold,
    "training_recent": _q_training_recent,
    "headcount_by_unit": _q_headcount_by_unit,
    "profile_completeness": _q_profile_completeness,
}


@router.post("/run")
def run_query(payload: Dict[str, Any], request: Request,
              db: Session = Depends(get_db)):
    """Answer one question. Body: {code, params, reveal_names}"""
    code = payload.get("code")
    question = QUESTION_BY_CODE.get(code)
    if not question:
        raise HTTPException(404, f"Неизвестный запрос '{code}'")

    handler = HANDLERS.get(code)
    if not handler:
        raise HTTPException(500, f"Обработчик для '{code}' не реализован")

    params = payload.get("params") or {}
    reveal = bool(payload.get("reveal_names"))

    # Revealing identities from an analytics answer is the same deliberate,
    # audited act as revealing them on a short list.
    if reveal:
        user = getattr(request.state, "user", {}) or {}
        db.add(AuditLog(action="reveal_identities", entity_type="analytics_query",
                        new_values={"query": code},
                        changed_by=user.get("sub", "unknown")))
        db.commit()

    employees = _active(db)
    matched, breakdown = handler(db, employees, params)

    # Preset breakdowns retain their historical Russian labels for compatibility.
    # Return the second language explicitly, without translating user-entered names.
    label_kk = {}
    label_model = {"education_level": EducationLevel, "language_knowledge": Language,
                   "headcount_by_unit": OrgUnit}.get(code)
    if label_model:
        label_kk = {row.name_ru: row.name_kk for row in db.query(label_model).all() if row.name_kk}

    total = len(employees)
    count = len(matched)

    return {
        "code": code,
        "name_ru": question["name_ru"],
        "name_kk": question.get("name_kk"),
        "name_en": question.get("name_en"),
        "count": count,
        "total": total,
        "percent": round(count / total * 100, 1) if total else 0.0,
        "group_by_ru": question.get("group_by_ru"),
        "breakdown": [{"label": k, "label_kk": label_kk.get(k), "count": v}
                      for k, v in sorted(breakdown.items(),
                                         key=lambda kv: -kv[1])],
        "employees": [_person(e, reveal) for e in matched],
        "names_revealed": reveal,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Headline figures for the analytics landing screen."""
    employees = _active(db)
    total = len(employees)

    verified = sum(1 for e in employees if e.profile_status == "verified")
    with_higher = 0
    with_language = 0
    with_foreign = 0

    higher = db.query(EducationLevel).filter(
        EducationLevel.code == "BACHELOR").first()
    higher_rank = higher.rank if higher else 3

    all_metrics = compute_metrics_bulk(db, employees)
    for employee in employees:
        if any(r.level and r.level.rank >= higher_rank for r in employee.educations):
            with_higher += 1
        if any(r.is_confirmed for r in employee.languages):
            with_language += 1
        if all_metrics.get(employee.id, {}).get(
                "org_unit_experience_years:FOREIGN", 0) > 0:
            with_foreign += 1

    def pct(n):
        return round(n / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "cards": [
            {"code": "verified", "value": verified, "percent": pct(verified),
             "label_ru": "Профилей подтверждено",
             "label_kk": "Расталған профильдер",
             "label_en": "Verified profiles"},
            {"code": "higher_education", "value": with_higher,
             "percent": pct(with_higher),
             "label_ru": "С высшим образованием",
             "label_kk": "Жоғары білімі барлар",
             "label_en": "With higher education"},
            {"code": "languages", "value": with_language,
             "percent": pct(with_language),
             "label_ru": "С подтверждённым языком",
             "label_kk": "Расталған тілі барлар",
             "label_en": "With a confirmed language"},
            {"code": "foreign_experience", "value": with_foreign,
             "percent": pct(with_foreign),
             "label_ru": "С зарубежным опытом",
             "label_kk": "Шетелдік тәжірибесі барлар",
             "label_en": "With foreign experience"},
        ],
    }


# ===========================================================================
# USER-BUILT QUERIES
#
# The ready-made questions above answer what HR asks most often. Everything
# below lets a user assemble their own from fields, operators and values, and
# save it for re-use.
# ===========================================================================

from models import SavedQuery                                    # noqa: E402
from services.candidate_queries import uses_candidate, plan_visible, query_uses_confidential  # noqa: E402
from services.query_engine import (                              # noqa: E402
    build_field_catalogue, groupable_fields, run_query, describe,
)


def _include_confidential(request):
    return (getattr(request.state, 'user', {}) or {}).get('role') == 'admin'


@router.get("/fields")
def list_fields(request: Request, db: Session = Depends(get_db)):
    """Every field a query can be built from, grouped for the picker."""
    fields = build_field_catalogue(db, include_confidential=_include_confidential(request))
    groups: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}

    for field in fields:
        key = field["group"]["name_ru"]
        if key not in seen:
            seen[key] = {**field["group"], "fields": []}
            groups.append(seen[key])
        seen[key]["fields"].append(field)

    return {
        "groups": groups,
        "group_by": groupable_fields(fields),
        "match_modes": [
            {"code": "all", "name_ru": "все условия", "name_kk": "барлық шарттар",
             "name_en": "all conditions"},
            {"code": "any", "name_ru": "любое из условий",
             "name_kk": "шарттардың кез келгені", "name_en": "any condition"},
        ],
    }


def _answer(db: Session, definition: Dict[str, Any], group_by, lang, reveal, *, include_confidential=False):
    fields = build_field_catalogue(db, include_confidential=include_confidential)
    try:
        outcome = run_query(db, definition, fields, group_by, lang, include_confidential=include_confidential)
    except ValueError as e:
        raise HTTPException(422, str(e))

    matched = outcome["matched"]
    total = outcome["total"]
    return {
        "count": len(matched),
        "total": total,
        "percent": round(len(matched) / total * 100, 1) if total else 0.0,
        "breakdown": outcome["breakdown"],
        "employees": [{**_person(e, reveal), "methodology_summary": outcome["candidate"].get("summaries", {}).get(e.id)} for e in matched],
        "names_revealed": reveal,
        "summary": describe(definition, fields, lang),
    }


@router.post("/custom/preview")
def preview_custom(payload: Dict[str, Any], request: Request,
                   db: Session = Depends(get_db)):
    """Run a query without saving it."""
    definition = payload.get("definition") or {}
    if not isinstance(definition, dict):
        raise HTTPException(422, "Некорректные условия / Шарттар жарамсыз")
    reveal = bool(payload.get("reveal_names"))

    if reveal:
        user = getattr(request.state, "user", {}) or {}
        db.add(AuditLog(action="reveal_identities",
                        entity_type="analytics_custom",
                        new_values={"conditions": len(
                            definition.get("conditions") or [])},
                        changed_by=user.get("sub", "unknown")))
        db.commit()

    return _answer(db, definition, payload.get("group_by"),
                   payload.get("lang", "ru"), reveal, include_confidential=_include_confidential(request))


@router.get("/saved")
def list_saved(request: Request, db: Session = Depends(get_db)):
    rows = [r for r in db.query(SavedQuery).order_by(SavedQuery.name).all()
            if plan_visible(r.definition, _include_confidential(request))]
    fields = build_field_catalogue(db, include_confidential=_include_confidential(request))
    return {"data": [{
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "definition": r.definition,
        "group_by": r.group_by,
        "created_by": r.created_by,
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
        "last_run_count": r.last_run_count,
        "summary": describe(r.definition or {}, fields),
        "mine": r.created_by == (getattr(request.state, "user", {}) or {})
                                 .get("sub"),
    } for r in rows]}


@router.post("/saved", status_code=201)
def create_saved(payload: Dict[str, Any], request: Request,
                 db: Session = Depends(get_db)):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Укажите название запроса")

    definition = payload.get("definition") or {}
    if not isinstance(definition, dict) or not definition.get("conditions"):
        raise HTTPException(422, "Добавьте хотя бы одно условие")

    # Reject a query that cannot run, rather than saving a broken one.
    fields = build_field_catalogue(db, include_confidential=_include_confidential(request))
    try:
        run_query(db, definition, fields, payload.get("group_by"), include_confidential=_include_confidential(request))
    except ValueError as e:
        raise HTTPException(422, str(e))

    user = getattr(request.state, "user", {}) or {}
    if (uses_candidate(definition) or query_uses_confidential(definition, fields, payload.get("group_by"))) and _include_confidential(request):
        definition = {**definition, 'confidential': True}
    row = SavedQuery(
        name=name,
        description=payload.get("description"),
        definition=definition,
        group_by=payload.get("group_by"),
        created_by=user.get("sub", "hr"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="create", entity_type="saved_query",
                    entity_id=row.id, new_values={"name": name},
                    changed_by=user.get("sub", "hr")))
    db.commit()
    return {"id": row.id, "name": row.name}


def _owned_query(db: Session, query_id: int, request: Request) -> SavedQuery:
    """Fetch a saved query the caller is entitled to change.

    An administrator maintains all of them; anyone else keeps only what they
    saved themselves, so one analyst cannot discard another's work.
    """
    row = db.query(SavedQuery).filter(SavedQuery.id == query_id).first()
    if not row:
        raise HTTPException(404, "Запрос не найден")

    user = getattr(request.state, "user", {}) or {}
    if not plan_visible(row.definition, _include_confidential(request)):
        raise HTTPException(403, 'Запрос содержит закрытые оценки / Сұрауда жабық бағалар бар')
    if user.get("role") != "admin" and row.created_by != user.get("sub"):
        raise HTTPException(403, "Этот запрос сохранён другим пользователем")
    return row


@router.put("/saved/{query_id}")
def update_saved(query_id: int, payload: Dict[str, Any], request: Request,
                 db: Session = Depends(get_db)):
    row = _owned_query(db, query_id, request)
    if "name" in payload and not str(payload["name"] or "").strip():
        raise HTTPException(422, "Укажите название / Атауын көрсетіңіз")
    try:
        run_query(db, payload.get("definition", row.definition), build_field_catalogue(db, include_confidential=_include_confidential(request)),
                  payload.get("group_by", row.group_by), include_confidential=_include_confidential(request))
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    for key in ("name", "description", "definition", "group_by"):
        if key in payload:
            setattr(row, key, payload[key])
    if (uses_candidate(row.definition) or query_uses_confidential(row.definition, build_field_catalogue(db, include_confidential=True), row.group_by)) and _include_confidential(request):
        row.definition = {**row.definition, 'confidential': True}
    db.commit()
    return {"id": row.id, "name": row.name}


@router.delete("/saved/{query_id}", status_code=204)
def delete_saved(query_id: int, request: Request,
                 db: Session = Depends(get_db)):
    row = _owned_query(db, query_id, request)

    user = getattr(request.state, "user", {}) or {}
    db.add(AuditLog(action="delete", entity_type="saved_query",
                    entity_id=query_id, old_values={"name": row.name},
                    changed_by=user.get("sub", "hr")))
    db.delete(row)
    db.commit()


@router.post("/saved/{query_id}/run")
def run_saved(query_id: int, payload: Dict[str, Any], request: Request,
              db: Session = Depends(get_db)):
    row = db.query(SavedQuery).filter(SavedQuery.id == query_id).first()
    if not row:
        raise HTTPException(404, "Запрос не найден")

    if not plan_visible(row.definition, _include_confidential(request)):
        raise HTTPException(403, 'Запрос содержит закрытые оценки / Сұрауда жабық бағалар бар')
    reveal = bool((payload or {}).get("reveal_names"))
    if reveal:
        user = getattr(request.state, "user", {}) or {}
        db.add(AuditLog(action="reveal_identities", entity_type="saved_query",
                        entity_id=query_id,
                        changed_by=user.get("sub", "unknown")))
        db.commit()

    result = _answer(db, row.definition or {}, row.group_by,
                     (payload or {}).get("lang", "ru"), reveal, include_confidential=_include_confidential(request))

    row.last_run_at = datetime.utcnow()
    row.last_run_count = None if uses_candidate(row.definition) or row.definition.get("confidential") else result["count"]
    db.commit()

    result["name"] = row.name
    result["id"] = row.id
    return result
