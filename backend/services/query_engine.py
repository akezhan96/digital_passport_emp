"""User-built analytics queries.

The ready-made questions answer what HR asks most often. This module answers
everything else: the user picks a field, an operator and a value, combines a
few of those, and gets the same three-part answer -- a count, a breakdown and
the matching people.

Two things keep it honest rather than a toy:

  * The field catalogue is derived from live data, not hardcoded. Job families,
    unit types, competencies, languages and administrator-defined custom fields
    all appear as queryable fields because they exist, not because someone
    listed them here.
  * Every field resolves through the same metrics the matching engine uses, so
    a query and a shortlist can never disagree about how long somebody has
    worked in marketing.
"""

from datetime import date
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload, selectinload

from models import (
    Employee, JobFamily, OrgUnitType, Country, Competency, Language,
    EducationLevel, Nationality, OrgUnit, Position, CustomFieldDefinition,
    CustomFieldValue, LanguageLevel, EmployeeTraining,
)
from services.metrics import compute_employee_metrics, compute_metrics_bulk
from services.candidate_queries import active_method, query_data, CANDIDATE_FIELDS
from services.candidate_sources import confidential as criterion_confidential

# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

NUMBER_OPS = [
    ("gte", "не менее", "кемінде", "at least"),
    ("gt", "больше", "артық", "greater than"),
    ("eq", "равно", "тең", "equals"),
    ("lt", "меньше", "кем", "less than"),
    ("lte", "не более", "көп емес", "at most"),
    ("between", "в диапазоне", "аралығында", "between"),
]

ENUM_OPS = [
    ("eq", "равно", "тең", "is"),
    ("ne", "не равно", "тең емес", "is not"),
    ("in", "один из", "біреуі", "is one of"),
]

BOOL_OPS = [
    ("is_true", "да", "иә", "yes"),
    ("is_false", "нет", "жоқ", "no"),
]

TEXT_OPS = [
    ("contains", "содержит", "қамтиды", "contains"),
    ("eq", "равно", "тең", "equals"),
    ("not_empty", "заполнено", "толтырылған", "is filled in"),
]

OPS_BY_KIND = {
    "number": NUMBER_OPS,
    "enum": ENUM_OPS,
    "ref": ENUM_OPS,
    "boolean": BOOL_OPS,
    "text": TEXT_OPS,
}


def _ops(kind: str) -> List[Dict[str, str]]:
    return [{"code": c, "name_ru": ru, "name_kk": kk, "name_en": en}
            for c, ru, kk, en in OPS_BY_KIND.get(kind, ENUM_OPS)]


# ---------------------------------------------------------------------------
# Field catalogue
# ---------------------------------------------------------------------------

def _field(code, kind, ru, kk, en, group, options=None, argument=None,
           suffix=None):
    out = {
        "code": code, "kind": kind, "group": group,
        "name_ru": ru, "name_kk": kk, "name_en": en,
        "operators": _ops(kind),
    }
    if options is not None:
        out["options"] = options
    if code in ("language_level", "max_education_level"):
        out["operators"] = [o for o in _ops("number") if o["code"] != "between"] + _ops("enum")[1:]
    if argument is not None:
        out["argument"] = argument
    if suffix:
        out["suffix_ru"], out["suffix_kk"], out["suffix_en"] = suffix
    return out


def _choices(rows, lang_rows=True):
    return [{"value": r.code, "name_ru": r.name_ru,
             "name_kk": r.name_kk, "name_en": r.name_en} for r in rows]


YEARS = ("лет", "жыл", "years")


def build_field_catalogue(db: Session, *, include_confidential=False) -> List[Dict[str, Any]]:
    """Every field a user may query, assembled from what is actually in the
    database right now."""
    families = db.query(JobFamily).order_by(JobFamily.name_ru).all()
    unit_types = db.query(OrgUnitType).order_by(OrgUnitType.name_ru).all()
    countries = db.query(Country).order_by(Country.name_ru).all()
    competencies = db.query(Competency).filter(
        Competency.is_active.is_(True), Competency.is_confidential.is_(False)).order_by(Competency.name_ru).all()
    languages = db.query(Language).order_by(Language.name_ru).all()
    levels = db.query(LanguageLevel).order_by(LanguageLevel.rank).all()
    edu_levels = db.query(EducationLevel).order_by(EducationLevel.rank).all()
    nationalities = db.query(Nationality).order_by(Nationality.name_ru).all()
    units = db.query(OrgUnit).order_by(OrgUnit.name_ru).all()
    positions = db.query(Position).order_by(Position.name_ru).all()

    G_EXP = ("Стаж и опыт", "Өтіл және тәжірибе", "Experience")
    G_PROFILE = ("Профиль", "Профиль", "Profile")
    G_EDU = ("Образование и языки", "Білім және тілдер", "Education & languages")
    G_ASSESS = ("Оценки", "Бағалау", "Assessment")
    G_EXTRA = ("Дополнительные поля", "Қосымша өрістер", "Custom fields")

    def group(triple):
        return {"name_ru": triple[0], "name_kk": triple[1], "name_en": triple[2]}

    fields = [
        _field("company_experience_years", "number",
               "Стаж в компании", "Компаниядағы өтіл", "Company tenure",
               group(G_EXP), suffix=YEARS),
        _field("total_experience_years", "number",
               "Общий стаж", "Жалпы өтіл", "Total experience",
               group(G_EXP), suffix=YEARS),
        _field("management_experience_years", "number",
               "Управленческий стаж", "Басшылық өтілі", "Management experience",
               group(G_EXP), suffix=YEARS),
        _field("function_experience", "number",
               "Опыт по функции", "Функция бойынша тәжірибе",
               "Experience in function", group(G_EXP), suffix=YEARS,
               argument={"name_ru": "Функция", "name_kk": "Функция",
                         "name_en": "Function", "options": _choices(families)}),
        _field("org_unit_experience", "number",
               "Опыт в типе подразделения", "Бөлімше түріндегі тәжірибе",
               "Experience in unit type", group(G_EXP), suffix=YEARS,
               argument={"name_ru": "Тип подразделения",
                         "name_kk": "Бөлімше түрі", "name_en": "Unit type",
                         "options": _choices(unit_types)}),
        _field("country_experience", "number",
               "Опыт работы в стране", "Елдегі жұмыс тәжірибесі",
               "Experience in country", group(G_EXP), suffix=YEARS,
               argument={"name_ru": "Страна", "name_kk": "Ел",
                         "name_en": "Country", "options": _choices(countries)}),

        _field("profile_status", "enum",
               "Статус профиля", "Профиль мәртебесі", "Profile status",
               group(G_PROFILE), options=[
                   {"value": "draft", "name_ru": "Черновик",
                    "name_kk": "Жоба", "name_en": "Draft"},
                   {"value": "in_review", "name_ru": "На проверке",
                    "name_kk": "Тексерілуде", "name_en": "In review"},
                   {"value": "verified", "name_ru": "Подтверждён",
                    "name_kk": "Расталған", "name_en": "Verified"},
                   {"value": "archived", "name_ru": "В архиве",
                    "name_kk": "Мұрағатта", "name_en": "Archived"},
               ]),
        _field("employment_status", "enum",
               "Статус занятости", "Жұмыспен қамту мәртебесі",
               "Employment status", group(G_PROFILE), options=[
                   {"value": "active", "name_ru": "Работает",
                    "name_kk": "Жұмыс істейді", "name_en": "Active"},
                   {"value": "terminated", "name_ru": "Не работает",
                    "name_kk": "Жұмыс істемейді", "name_en": "Inactive"},
               ]),
        _field("current_org_unit", "ref",
               "Текущее подразделение", "Ағымдағы бөлімше", "Current unit",
               group(G_PROFILE), options=_choices(units)),
        _field("current_unit_type", "ref",
               "Тип текущего подразделения", "Ағымдағы бөлімше түрі",
               "Current unit type", group(G_PROFILE),
               options=_choices(unit_types)),
        _field("current_position", "ref",
               "Текущая должность", "Ағымдағы лауазым", "Current position",
               group(G_PROFILE), options=_choices(positions)),
        _field("current_job_family", "ref",
               "Текущая функция", "Ағымдағы функция", "Current function",
               group(G_PROFILE), options=_choices(families)),
        _field("nationality", "ref",
               "Национальность", "Ұлты", "Nationality",
               group(G_PROFILE), options=_choices(nationalities)),
        _field("age", "number", "Возраст", "Жасы", "Age",
               group(G_PROFILE), suffix=YEARS),
        _field("has_open_posting", "boolean",
               "Есть действующее назначение", "Қолданыстағы тағайындау бар",
               "Has an open posting", group(G_PROFILE)),

        _field("max_education_level", "ref",
               "Уровень образования (высший)", "Білім деңгейі (ең жоғары)",
               "Education level (highest)", group(G_EDU),
               options=_choices(edu_levels)),
        _field("language_level", "ref",
               "Уровень владения языком", "Тіл меңгеру деңгейі",
               "Language level", group(G_EDU), options=_choices(levels),
               argument={"name_ru": "Язык", "name_kk": "Тіл",
                         "name_en": "Language", "options": _choices(languages)}),
        _field("has_training", "boolean",
               "Проходил обучение по направлению",
               "Бағыт бойынша оқудан өткен", "Has training in discipline",
               group(G_EDU),
               argument={"name_ru": "Направление", "name_kk": "Бағыт",
                         "name_en": "Discipline", "options": _choices(families)}),

        _field("competency", "number",
               "Оценка компетенции", "Құзыреттілік бағасы", "Competency score",
               group(G_ASSESS), suffix=("балл", "ұпай", "points"),
               argument={"name_ru": "Компетенция", "name_kk": "Құзыреттілік",
                         "name_en": "Competency",
                         "options": _choices(competencies)}),
    ]

    method = active_method(db)
    if method is not None:
        private_criteria = any(c.enabled and criterion_confidential(c) for c in method.criteria)
        partial = not include_confidential and private_criteria
        tail_ru = ' (без закрытых показателей)' if partial else ''
        tail_kk = ' (жабық көрсеткіштерсіз)' if partial else ''
        assessment_group = group(('Методика из личного дела', 'Жеке істегі әдістеме', 'Dossier methodology'))
        labels = [
            ('candidate_points', 'number', 'Общий балл по новой методике', 'Жаңа әдістеме бойынша жалпы ұпай'),
            ('candidate_max_points', 'number', 'Максимальный балл по методике', 'Әдістеме бойынша ең жоғары ұпай'),
            ('candidate_percent', 'number', 'Итоговый коэффициент по методике, %', 'Әдістеме бойынша қорытынды коэффициент, %'),
            ('candidate_complete', 'boolean', 'Оценка по методике заполнена полностью', 'Әдістеме бағасы толық толтырылған'),
            ('candidate_missing_count', 'number', 'Незаполненные показатели методики', 'Әдістеменің толтырылмаған көрсеткіштері'),
            ('candidate_version', 'number', 'Версия действующей методики', 'Қолданыстағы әдістеме нұсқасы'),
            ('candidate_technical_profile', 'boolean', 'Технический профиль в оценке', 'Бағалаудағы техникалық бейін'),
        ]
        for code, kind, ru, kk in labels:
            fields.append(_field(code, kind, ru + tail_ru, kk + tail_kk,
                                 code, assessment_group))
        fields.append(_field('candidate_criterion', 'number',
            'Балл показателя новой методики', 'Жаңа әдістеме көрсеткішінің ұпайы',
            'Dossier criterion points', assessment_group, suffix=('балл', 'ұпай', 'points'),
            argument={'name_ru': f'Показатель, версия {method.version}',
                      'name_kk': f'Көрсеткіш, {method.version}-нұсқа', 'name_en': 'Criterion',
                      'options': [{'value': str(c.id), 'position': c.position, 'name_ru': c.name_ru, 'name_kk': c.name_kk, 'confidential': criterion_confidential(c)}
                                  for c in sorted(method.criteria, key=lambda c: c.position)
                                  if c.enabled and (include_confidential or not criterion_confidential(c))]}))

        for field in fields:
            if field['code'] in CANDIDATE_FIELDS:
                field['methodology_id'] = method.id
                field['confidential'] = bool(include_confidential and private_criteria and field['code'] != 'candidate_criterion')

    # Administrator-defined fields become queryable the moment they exist.
    for definition in db.query(CustomFieldDefinition).filter(
            CustomFieldDefinition.entity_type == "employee",
            CustomFieldDefinition.is_active.is_(True)).all():
        if definition.visibility == 'admin' and not include_confidential:
            continue
        kind = {"number": "number", "date": "text", "boolean": "boolean",
                "select": "enum"}.get(definition.field_type, "text")
        options = None
        if definition.field_type == "select":
            options = [{"value": (o.get("value") if isinstance(o, dict) else o),
                        "name_ru": (o.get("name_ru") or o.get("label") or o.get('value') if isinstance(o, dict) else o),
                        "name_kk": (o.get('name_kk') or o.get('name_ru') or o.get('label') if isinstance(o, dict) else o), "name_en": None}
                       for o in (definition.options or [])]
        fields.append(_field(
            f"custom:{definition.code}", kind,
            definition.name_ru, definition.name_kk, definition.name_en,
            group(G_EXTRA), options=options))
        fields[-1]['confidential'] = definition.visibility == 'admin'

    return fields


def groupable_fields(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only enum-like fields make sensible breakdowns."""
    return [f for f in fields if f["kind"] in ("enum", "ref")
            and not f.get("argument")]


# ---------------------------------------------------------------------------
# Resolving a field for one employee
# ---------------------------------------------------------------------------

def _age(employee: Employee) -> Optional[float]:
    if not employee.birth_date:
        return None
    today = date.today()
    return round((today - employee.birth_date).days / 365.25, 1)


def resolve(db: Session, employee: Employee, metrics: Dict[str, float],
            field_code: str, argument: Optional[str],
            custom_values: Dict[str, Any]) -> Any:
    """The employee's value for one field. None means 'no data'."""

    if field_code == "company_experience_years":
        return metrics.get("company_experience_years", 0.0)
    if field_code == "total_experience_years":
        return metrics.get("total_experience_years", 0.0)
    if field_code == "management_experience_years":
        return metrics.get("management_experience_years", 0.0)
    if field_code == "function_experience":
        return metrics.get(f"function_experience_years:{argument}", 0.0)
    if field_code == "org_unit_experience":
        return metrics.get(f"org_unit_experience_years:{argument}", 0.0)
    if field_code == "country_experience":
        return metrics.get(f"country_experience_years:{argument}", 0.0)
    if field_code in CANDIDATE_FIELDS:
        return metrics.get(f"candidate_criterion:{argument}" if field_code == "candidate_criterion" else field_code)
    if field_code == "competency":
        return metrics.get(f"competency:{argument}")

    if field_code == "profile_status":
        return employee.profile_status
    if field_code == "employment_status":
        return employee.employment_status
    if field_code == "current_org_unit":
        return employee.current_org_unit.code if employee.current_org_unit else None
    if field_code == "current_unit_type":
        unit = employee.current_org_unit
        return unit.unit_type.code if unit and unit.unit_type else None
    if field_code == "current_position":
        return employee.current_position.code if employee.current_position else None
    if field_code == "current_job_family":
        position = employee.current_position
        return position.job_family.code if position and position.job_family else None
    if field_code == "nationality":
        return employee.nationality.code if employee.nationality else None
    if field_code == "age":
        return _age(employee)
    if field_code == "has_open_posting":
        return any(r.date_from <= date.today() and (r.date_to is None or r.date_to >= date.today()) for r in employee.work_experience)

    if field_code == "max_education_level":
        best = None
        for row in employee.educations:
            if row.level and (best is None or row.level.rank > best.rank):
                best = row.level
        return best.code if best else None

    if field_code == "language_level":
        today = date.today()
        best = None
        for row in employee.languages:
            if not row.language or row.language.code != argument:
                continue
            if row.valid_until and row.valid_until < today:
                continue
            if row.level and (best is None or row.level.rank > best.rank):
                best = row.level
        return best.code if best else None

    if field_code == "has_training":
        today = date.today()
        return any(t.date_to and t.date_to <= today
                   and (not t.date_from or t.date_from <= today)
                   and (not t.valid_until or t.valid_until >= today)
                   and t.job_family and t.job_family.code == argument
                   for t in employee.trainings)

    if field_code.startswith("custom:"):
        return custom_values.get(field_code.split(":", 1)[1])

    return None


# ---------------------------------------------------------------------------
# Applying a condition
# ---------------------------------------------------------------------------

def _as_number(value) -> Optional[float]:
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _rank_of(db: Session, level_code: str) -> Optional[int]:
    row = (db.query(LanguageLevel).filter(LanguageLevel.code == level_code)
           .order_by(LanguageLevel.rank).first())
    return row.rank if row else None


def matches(db: Session, actual: Any, operator: str, expected: Any,
            kind: str, field_code: str = "") -> bool:
    if operator == "is_true":
        return bool(actual)
    if operator == "is_false":
        return not bool(actual)
    if operator == "not_empty":
        return actual not in (None, "", [])

    if actual is None:
        return False

    if kind == "number":
        left = _as_number(actual)
        if left is None:
            return False
        if operator == "between":
            bounds = expected if isinstance(expected, (list, tuple)) else []
            low = _as_number(bounds[0]) if len(bounds) > 0 else None
            high = _as_number(bounds[1]) if len(bounds) > 1 else None
            if low is None or high is None:
                return False
            return low <= left <= high
        right = _as_number(expected)
        if right is None:
            return False
        return {
            "gte": left >= right, "gt": left > right, "eq": left == right,
            "lt": left < right, "lte": left <= right,
        }.get(operator, False)

    # Ordered catalogues have explicit comparison operators; equality is exact.
    if field_code in ("language_level", "max_education_level"):
        if operator == "in":
            wanted = expected if isinstance(expected, list) else [expected]
            return str(actual) in [str(v) for v in wanted]
        model = LanguageLevel if field_code == "language_level" else EducationLevel
        key = f"query_ranks_{field_code}"
        if key not in db.info:
            db.info[key] = {r.code: r.rank for r in db.query(model).all()}
        ranks = db.info[key]
        left, right = ranks.get(str(actual)), ranks.get(str(expected))
        if left is None or right is None:
            return False
        return {"eq": left == right, "ne": left != right, "gte": left >= right,
                "gt": left > right, "lte": left <= right, "lt": left < right}.get(operator, False)

    if operator == "in":
        wanted = expected if isinstance(expected, list) else [expected]
        return str(actual) in [str(v) for v in wanted]
    if operator == "eq":
        return str(actual) == str(expected)
    if operator == "ne":
        return str(actual) != str(expected)
    if operator == "contains":
        return str(expected).lower() in str(actual).lower()

    return False


# ---------------------------------------------------------------------------
# Running a query
# ---------------------------------------------------------------------------

def _custom_values_for(db: Session, employee_id: int) -> Dict[str, Any]:
    rows = (db.query(CustomFieldValue)
            .filter(CustomFieldValue.entity_type == "employee",
                    CustomFieldValue.entity_id == employee_id).all())
    return {r.definition.code: r.as_python() for r in rows if r.definition}


def _custom_values_bulk(db: Session,
                        employee_ids: List[int], *, include_confidential=False) -> Dict[int, Dict[str, Any]]:
    """Every employee's extra fields in one statement instead of one each."""
    if not employee_ids:
        return {}
    rows = (db.query(CustomFieldValue)
            .options(joinedload(CustomFieldValue.definition))
            .filter(CustomFieldValue.entity_type == "employee",
                    CustomFieldValue.entity_id.in_(employee_ids)).all())
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if not row.definition or (row.definition.visibility == 'admin' and not include_confidential):
            continue
        out.setdefault(row.entity_id, {})[row.definition.code] = row.as_python()
    return out


def _label_for(db: Session, field: Dict[str, Any], value: Any, lang: str) -> str:
    if value is None:
        return "көрсетілмеген" if lang == "kk" else "не указано"
    for option in (field.get("options") or []):
        if str(option.get("value")) == str(value):
            return (option.get(f"name_{lang}") or option.get("name_ru")
                    or str(value))
    return str(value)


# Operators that ask a question about the field itself and so take no value.
VALUELESS_OPS = {"is_true", "is_false", "not_empty"}


def _validate_condition(condition: Dict[str, Any],
                        field: Dict[str, Any]) -> None:
    """Refuse a condition that cannot be evaluated as written.

    Falling through to False would report "no matches" for a question that was
    never actually asked, which reads exactly like a real answer.
    """
    name = field.get("name_ru") or field["code"]
    if field.get("argument"):
        valid_arguments = {str(o["value"]) for o in field["argument"]["options"]}
        if str(condition.get("argument")) not in valid_arguments:
            raise ValueError(f"Укажите допустимый параметр поля «{name}» / Өрістің жарамды параметрін көрсетіңіз")
    operator = condition.get("operator")
    allowed = [o["code"] for o in field.get("operators", [])]

    if not operator:
        raise ValueError(f"Не выбрано условие для поля «{name}»")
    if operator not in allowed:
        raise ValueError(
            f"Условие «{operator}» неприменимо к полю «{name}»")

    if operator in VALUELESS_OPS:
        return

    value = condition.get("value")
    if field.get("options") is not None and operator not in VALUELESS_OPS:
        values = value if isinstance(value, list) else [value]
        valid_values = {str(o["value"]) for o in field["options"]}
        if not values or any(str(v) not in valid_values for v in values):
            raise ValueError(f"Неизвестное значение поля «{name}» / Өріс мәні белгісіз")

    if operator == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2 \
                or any(_as_number(v) is None for v in value):
            raise ValueError(f"Для диапазона «{name}» укажите обе границы")
        low, high = (_as_number(v) for v in value)
        if low > high:
            raise ValueError(
                f"Нижняя граница «{name}» больше верхней")
        return

    if operator == "in":
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError(f"Выберите хотя бы одно значение для «{name}»")
        return

    if value is None or value == "":
        raise ValueError(f"Не указано значение для поля «{name}»")

    if field.get("kind") == "number" and _as_number(value) is None:
        raise ValueError(f"Для поля «{name}» нужно число, а не «{value}»")


def prepare_query_population(db: Session, *, include_confidential=False) -> Dict[str, Any]:
    """Load a population once for the queries in one request or report.

    Keep this structure within its owning database session. It is a snapshot
    for evaluating multiple questions, never a process cache or client input.
    References used by filters, grouping and response rows must be loaded even
    when every employee has a distinct position or organisational unit.
    """
    employees = (db.query(Employee)
        .filter(Employee.employment_status == "active")
        .options(
            selectinload(Employee.current_position).selectinload(Position.job_family),
            selectinload(Employee.current_org_unit).selectinload(OrgUnit.unit_type),
            selectinload(Employee.nationality),
            selectinload(Employee.trainings).selectinload(EmployeeTraining.job_family),
        ).order_by(Employee.id).all())
    candidate = query_data(db, employees, include_confidential=include_confidential)
    metrics = compute_metrics_bulk(db, employees)
    for employee in employees:
        metrics.setdefault(employee.id, {}).update(candidate['values'].get(employee.id, {}))
    return {
        "employees": employees,
        "metrics": metrics,
        "candidate": candidate,
        "include_confidential": include_confidential,
        "custom": _custom_values_bulk(db, [employee.id for employee in employees], include_confidential=include_confidential),
    }


def run_query(db: Session, definition: Dict[str, Any],
              fields: List[Dict[str, Any]],
              group_by: Optional[str] = None,
              lang: str = "ru", *,
              population: Optional[Dict[str, Any]] = None,
              include_confidential=False) -> Dict[str, Any]:
    """Evaluate a user-built query against every active employee."""
    by_code = {f["code"]: f for f in fields}
    if not isinstance(definition, dict):
        raise ValueError("Некорректные условия / Шарттар жарамсыз")
    conditions = definition.get("conditions") or []
    if not isinstance(conditions, list) or len(conditions) > 30 or any(not isinstance(c, dict) for c in conditions):
        raise ValueError("Некорректные условия / Шарттар қате")
    if definition.get("match", "all") not in ("all", "any"):
        raise ValueError("Некорректный способ объединения / Біріктіру тәсілі қате")
    if group_by and group_by not in {f["code"] for f in groupable_fields(fields)}:
        raise ValueError("Некорректная группировка / Топтау қате")
    match_all = (definition.get("match") or "all") == "all"

    for condition in conditions:
        if condition.get("field") not in by_code:
            raise ValueError(f"Неизвестное поле: {condition.get('field')}")
        _validate_condition(condition, by_code[condition["field"]])
    from services.candidate_queries import query_uses_confidential
    if not include_confidential and query_uses_confidential(definition, fields, group_by):
        raise ValueError('Закрытые показатели недоступны / Жабық көрсеткіштер қолжетімсіз')

    population = prepare_query_population(db, include_confidential=include_confidential) if population is None else population
    if population.get('include_confidential', False) != include_confidential:
        raise ValueError('Изменились права доступа к оценкам / Бағаларға қол жеткізу құқықтары өзгерді')
    expected_methods = {f['methodology_id'] for f in fields if 'methodology_id' in f}
    loaded_method = population.get('candidate', {}).get('methodology_id')
    if population.get('employees') and expected_methods and loaded_method not in expected_methods:
        raise ValueError('Действующая методика изменилась. Повторите запрос / Қолданыстағы әдістеме өзгерді. Сұрауды қайталаңыз')
    employees = population["employees"]
    all_metrics, all_custom = population["metrics"], population["custom"]

    matched: List[Employee] = []
    breakdown: Dict[str, int] = {}
    group_field = by_code.get(group_by) if group_by else None

    for employee in employees:
        metrics = all_metrics.get(employee.id, {})
        custom = all_custom.get(employee.id, {})

        results = []
        for condition in conditions:
            field = by_code[condition["field"]]
            actual = resolve(db, employee, metrics, field["code"],
                             condition.get("argument"), custom)
            results.append(matches(db, actual, condition.get("operator", "eq"),
                                   condition.get("value"), field["kind"],
                                   field["code"]))

        hit = (all(results) if match_all else any(results)) if results else True
        if hit:
            matched.append(employee)
            if group_field:
                value = resolve(db, employee, metrics, group_field["code"],
                                None, custom)
                label = _label_for(db, group_field, value, lang)
                breakdown[label] = breakdown.get(label, 0) + 1

    return {
        "matched": matched,
        "candidate": population.get("candidate", {}),
        "total": len(employees),
        "breakdown": [{"label": k, "count": v}
                      for k, v in sorted(breakdown.items(),
                                         key=lambda kv: -kv[1])],
    }


def describe(definition: Dict[str, Any], fields: List[Dict[str, Any]],
             lang: str = "ru") -> str:
    """A one-line, human-readable rendering of the conditions."""
    by_code = {f["code"]: f for f in fields}
    joiner = {"ru": {"all": " и ", "any": " или "},
              "kk": {"all": " және ", "any": " немесе "},
              "en": {"all": " and ", "any": " or "}}.get(lang, {})
    parts = []

    for condition in definition.get("conditions") or []:
        field = by_code.get(condition.get("field"))
        if not field:
            continue
        if field["code"] == "has_open_posting" and condition.get("operator") in ("is_true", "is_false"):
            phrases = {
                "ru": {"is_true": "Есть действующее назначение", "is_false": "Действующее назначение отсутствует"},
                "kk": {"is_true": "Қолданыстағы тағайындау бар", "is_false": "Қолданыстағы тағайындау жоқ"},
            }
            parts.append(phrases.get(lang, phrases["ru"])[condition["operator"]])
            continue
        name = field.get(f"name_{lang}") or field["name_ru"]
        if condition.get("argument") and field.get("argument"):
            for option in field["argument"]["options"]:
                if option["value"] == condition["argument"]:
                    name += f" ({option.get(f'name_{lang}') or option['name_ru']})"
                    break
        op = next((o for o in field["operators"]
                   if o["code"] == condition.get("operator")), None)
        op_name = (op.get(f"name_{lang}") or op["name_ru"]) if op else ""
        value = condition.get("value")
        if isinstance(value, list):
            value = ", ".join(_label_for(None, field, v, lang) for v in value)
        elif value is not None:
            value = _label_for(None, field, value, lang)
        suffix = field.get(f"suffix_{lang}") or field.get("suffix_ru") or ""
        parts.append(" ".join(str(p) for p in (name, op_name, value, suffix)
                              if p not in (None, "")))

    return (joiner.get(definition.get("match", "all"), " и ")).join(parts)
