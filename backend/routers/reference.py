"""Generic CRUD over every reference catalogue.

One router serves all of them, so adding a competency, an assessment scale or
a job family is a data operation through the UI -- never a code change.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from database import get_db
from models import (
    Country, Nationality, Language, LanguageScale, LanguageLevel,
    EducationLevel, EducationField, JobFamily, OrgUnitType, PositionGrade,
    TrainingType, AssessmentScale, CompetencyCategory, Competency,
    RequirementType, OrgUnit, Position, AuditLog,
)

router = APIRouter(prefix="/api/v1/reference", tags=["reference"])

# name in the URL -> (model, extra writable columns)
REGISTRY: Dict[str, Any] = {
    "countries":            (Country, []),
    "nationalities":        (Nationality, []),
    "languages":            (Language, []),
    "language-scales":      (LanguageScale, []),
    "language-levels":      (LanguageLevel, ["scale_id", "rank"]),
    "education-levels":     (EducationLevel, ["rank"]),
    "education-fields":     (EducationField, ["job_family_id"]),
    "job-families":         (JobFamily, ["parent_id"]),
    "org-unit-types":       (OrgUnitType, []),
    "position-grades":      (PositionGrade, ["rank"]),
    "training-types":       (TrainingType, []),
    "assessment-scales":    (AssessmentScale, ["min_value", "max_value", "step"]),
    "competency-categories": (CompetencyCategory, ["is_confidential"]),
    "competencies":         (Competency, ["category_id", "description", "is_active", "sort_order"]),
    "requirement-types":    (RequirementType, ["handler", "condition_schema", "description"]),
    "org-units":            (OrgUnit, ["parent_id", "country_id", "region", "unit_type_id"]),
    "positions":            (Position, ["job_family_id", "grade_id", "management_level"]),
}

BASE_FIELDS = ["code", "name_ru", "name_kk", "name_en"]

# Human-readable catalogue names. The URL slug stays technical; the UI shows
# these instead, in the user's language.
CATALOG_LABELS = {
    "countries":             ("Страны", "Елдер", "Countries"),
    "nationalities":         ("Национальности", "Ұлттар", "Nationalities"),
    "languages":             ("Языки", "Тілдер", "Languages"),
    "language-scales":       ("Шкалы языков", "Тіл шкалалары", "Language scales"),
    "language-levels":       ("Уровни языков", "Тіл деңгейлері", "Language levels"),
    "education-levels":      ("Уровни образования", "Білім деңгейлері", "Education levels"),
    "education-fields":      ("Специальности", "Мамандықтар", "Fields of study"),
    "job-families":          ("Профессиональные функции", "Кәсіби функциялар", "Job families"),
    "org-unit-types":        ("Типы подразделений", "Бөлімше түрлері", "Org-unit types"),
    "position-grades":       ("Грейды должностей", "Лауазым грейдтері", "Position grades"),
    "training-types":        ("Типы обучения", "Оқыту түрлері", "Training types"),
    "assessment-scales":     ("Шкалы оценивания", "Бағалау шкалалары", "Assessment scales"),
    "competency-categories": ("Категории компетенций", "Құзыреттілік санаттары",
                              "Competency categories"),
    "competencies":          ("Компетенции", "Құзыреттіліктер", "Competencies"),
    "requirement-types":     ("Типы требований", "Талап түрлері", "Requirement types"),
    "org-units":             ("Оргструктура", "Ұйымдық құрылым", "Organisational units"),
    "positions":             ("Должности", "Лауазымдар", "Positions"),
}

# Localised captions for the extra columns of particular catalogues, so the
# admin screen never shows a raw database column name.
FIELD_LABELS = {
    "scale_id":        ("Шкала", "Шкала", "Scale"),
    "rank":            ("Порядок", "Реті", "Rank"),
    "job_family_id":   ("Профессиональная функция", "Кәсіби функция", "Job family"),
    "parent_id":       ("Родительская запись", "Аталық жазба", "Parent"),
    "min_value":       ("Минимум", "Ең аз мән", "Minimum"),
    "max_value":       ("Максимум", "Ең көп мән", "Maximum"),
    "step":            ("Шаг", "Қадам", "Step"),
    "is_confidential": ("Конфиденциально", "Құпия", "Confidential"),
    "category_id":     ("Категория", "Санат", "Category"),
    "description":     ("Описание", "Сипаттама", "Description"),
    "is_active":       ("Активна", "Белсенді", "Active"),
    "sort_order":      ("Порядок", "Реті", "Sort order"),
    "handler":         ("Обработчик", "Өңдеуші", "Handler"),
    "condition_schema": ("Схема условия", "Шарт схемасы", "Condition schema"),
    "country_id":      ("Страна", "Ел", "Country"),
    "region":          ("Регион", "Аймақ", "Region"),
    "unit_type_id":    ("Тип подразделения", "Бөлімше түрі", "Unit type"),
    "grade_id":        ("Грейд", "Грейд", "Grade"),
    "management_level": ("Уровень руководства", "Басшылық деңгейі", "Management level"),
}


def _labels(mapping, key):
    ru, kk, en = mapping.get(key, (key, key, key))
    return {"name_ru": ru, "name_kk": kk, "name_en": en}




def _resolve(catalog: str):
    if catalog not in REGISTRY:
        raise HTTPException(404, f"Unknown catalogue '{catalog}'. "
                                 f"Available: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[catalog]


def _serialise(row, extra_fields: List[str]) -> Dict[str, Any]:
    out = {"id": row.id}
    for field in BASE_FIELDS + extra_fields:
        value = getattr(row, field, None)
        # Numeric -> float so JSON stays clean
        if hasattr(value, "quantize"):
            value = float(value)
        out[field] = value
    return out


@router.get("/catalogs")
def list_catalogs():
    """Every catalogue the admin UI can edit, with localised captions."""
    return {
        "catalogs": [
            {
                "name": name,
                **_labels(CATALOG_LABELS, name),
                "extra_fields": [
                    {"field": f, **_labels(FIELD_LABELS, f)} for f in extra
                ],
            }
            for name, (_model, extra) in sorted(
                REGISTRY.items(),
                key=lambda kv: CATALOG_LABELS.get(kv[0], (kv[0],))[0],
            )
        ]
    }


@router.get("/{catalog}")
def list_items(catalog: str, db: Session = Depends(get_db)):
    model, extra = _resolve(catalog)
    rows = db.query(model).order_by(model.id).all()
    return {"data": [_serialise(r, extra) for r in rows], "total": len(rows)}


@router.post("/{catalog}", status_code=201)
def create_item(catalog: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    model, extra = _resolve(catalog)

    allowed = set(BASE_FIELDS + extra)
    data = {k: v for k, v in payload.items() if k in allowed}

    if not data.get("code") or not data.get("name_ru"):
        raise HTTPException(422, "Both 'code' and 'name_ru' are required")

    if db.query(model).filter(model.code == data["code"]).first():
        raise HTTPException(409, f"'{data['code']}' already exists in {catalog}")

    row = model(**data)
    db.add(row)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="create", entity_type=catalog, entity_id=row.id,
                    new_values=data, changed_by="admin"))
    db.commit()
    return _serialise(row, extra)


@router.put("/{catalog}/{item_id}")
def update_item(catalog: str, item_id: int, payload: Dict[str, Any],
                db: Session = Depends(get_db)):
    model, extra = _resolve(catalog)
    row = db.query(model).filter(model.id == item_id).first()
    if not row:
        raise HTTPException(404, "Not found")

    allowed = set(BASE_FIELDS + extra)
    before = _serialise(row, extra)

    for key, value in payload.items():
        if key in allowed:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)

    after = _serialise(row, extra)
    db.add(AuditLog(action="update", entity_type=catalog, entity_id=row.id,
                    old_values=before, new_values=after, changed_by="admin"))
    db.commit()
    return after


@router.delete("/{catalog}/{item_id}", status_code=204)
def delete_item(catalog: str, item_id: int, db: Session = Depends(get_db)):
    model, extra = _resolve(catalog)
    row = db.query(model).filter(model.id == item_id).first()
    if not row:
        raise HTTPException(404, "Not found")

    before = _serialise(row, extra)
    db.add(AuditLog(action="delete", entity_type=catalog, entity_id=item_id,
                    old_values=before, changed_by="admin"))
    db.delete(row)
    db.commit()
    return None
