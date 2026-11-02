"""Generic CRUD over every reference catalogue.

One router serves all of them, so adding a competency, an assessment scale or
a job family is a data operation through the UI -- never a code change.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import DataError, IntegrityError
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
    "position-grades":       ("Реестр должностей", "Лауазымдар тізілімі", "Position registry"),
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
    "grade_id":        ("Категория реестра должностей", "Лауазымдар тізілімінің санаты", "Position registry category"),
    "management_level": ("Уровень руководства", "Басшылық деңгейі", "Management level"),
}


def _labels(mapping, key):
    ru, kk, en = mapping.get(key, (key, key, key))
    return {"name_ru": ru, "name_kk": kk, "name_en": en}




from models import CustomCatalog, CustomCatalogItem                # noqa: E402

CUSTOM_PREFIX = "custom:"


def _custom_catalog(db: Session, code: str) -> CustomCatalog:
    row = db.query(CustomCatalog).filter(CustomCatalog.code == code).first()
    if not row:
        raise HTTPException(404, f"Справочник '{code}' не найден")
    return row


def _resolve(catalog: str):
    if catalog not in REGISTRY:
        raise HTTPException(404, f"Unknown catalogue '{catalog}'. "
                                 f"Available: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[catalog]


def _is_custom(catalog: str) -> bool:
    """A user-defined catalogue is addressed as 'custom:<code>'."""
    return catalog.startswith("custom:")


def _custom_code(catalog: str) -> str:
    return catalog.split(":", 1)[1]


CUSTOM_ITEM_FIELDS = ["description", "sort_order"]


def _serialise_custom(item) -> Dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name_ru": item.name_ru,
        "name_kk": item.name_kk,
        "name_en": item.name_en,
        "description": item.description,
        "sort_order": item.sort_order,
    }


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
def list_catalogs(db: Session = Depends(get_db)):
    """Every catalogue the admin UI can edit -- built-in and user-defined."""
    built_in = [
        {
            "name": name,
            **_labels(CATALOG_LABELS, name),
            "extra_fields": [
                {"field": f, **_labels(FIELD_LABELS, f)} for f in extra
            ],
            "is_custom": False,
        }
        for name, (_model, extra) in sorted(
            REGISTRY.items(),
            key=lambda kv: CATALOG_LABELS.get(kv[0], (kv[0],))[0],
        )
    ]

    from models import CustomCatalog as _CustomCatalog
    custom = [
        {
            "name": f"custom:{row.code}",
            "name_ru": row.name_ru,
            "name_kk": row.name_kk or row.name_ru,
            "name_en": row.name_en or row.name_ru,
            "extra_fields": [
                {"field": "description", **_labels(FIELD_LABELS, "description")},
                {"field": "sort_order", **_labels(FIELD_LABELS, "sort_order")},
            ],
            "is_custom": True,
            "catalog_id": row.id,
            "description": row.description,
        }
        for row in db.query(_CustomCatalog)
        .filter(_CustomCatalog.is_active.is_(True))
        .order_by(_CustomCatalog.name_ru).all()
    ]

    return {"catalogs": built_in + custom}


@router.get("/{catalog}")
def list_items(catalog: str, db: Session = Depends(get_db)):
    if _is_custom(catalog):
        from models import CustomCatalogItem as _Item
        parent = _custom_catalog(db, _custom_code(catalog))
        rows = (db.query(_Item).filter(_Item.catalog_id == parent.id)
                .order_by(_Item.sort_order, _Item.id).all())
        return {"data": [_serialise_custom(r) for r in rows],
                "total": len(rows)}

    model, extra = _resolve(catalog)
    rows = db.query(model).order_by(model.id).all()
    return {"data": [_serialise(r, extra) for r in rows], "total": len(rows)}


@router.post("/{catalog}", status_code=201)
def create_item(catalog: str, payload: Dict[str, Any], request: Request,
                db: Session = Depends(get_db)):
    if _is_custom(catalog):
        from models import CustomCatalogItem as _Item
        parent = _custom_catalog(db, _custom_code(catalog))
        code = (payload.get("code") or "").strip()
        name_ru = (payload.get("name_ru") or "").strip()
        if not code or not name_ru:
            raise HTTPException(422, "Both 'code' and 'name_ru' are required")
        if db.query(_Item).filter(_Item.catalog_id == parent.id,
                                  _Item.code == code).first():
            raise HTTPException(409, f"'{code}' already exists in {catalog}")

        item = _Item(catalog_id=parent.id, code=code, name_ru=name_ru,
                     name_kk=payload.get("name_kk"),
                     name_en=payload.get("name_en"),
                     description=payload.get("description"),
                     sort_order=int(payload.get("sort_order") or 0))
        db.add(item)
        _commit(db, catalog)
        db.refresh(item)
        db.add(AuditLog(action="create", entity_type=catalog, entity_id=item.id,
                        new_values={"code": code, "name": name_ru},
                        changed_by=_actor(request)))
        _commit(db, catalog)
        return _serialise_custom(item)

    model, extra = _resolve(catalog)

    allowed = set(BASE_FIELDS + extra)
    data = {k: v for k, v in payload.items() if k in allowed}

    if not data.get("code") or not data.get("name_ru"):
        raise HTTPException(422, "Both 'code' and 'name_ru' are required")

    if db.query(model).filter(model.code == data["code"]).first():
        raise HTTPException(409, f"'{data['code']}' already exists in {catalog}")

    row = model(**data)
    db.add(row)
    _commit(db, catalog)
    db.refresh(row)

    db.add(AuditLog(action="create", entity_type=catalog, entity_id=row.id,
                    new_values=data, changed_by=_actor(request)))
    _commit(db, catalog)
    return _serialise(row, extra)



# ---------------------------------------------------------------------------
# Failure translation
#
# A catalogue is edited by HR, not by a developer reading a stack trace. The
# database refuses three things here -- a value pointing at a row that is not
# there, a duplicate code, and text longer than the column -- and each of them
# has a plain answer. Without this they all surface as 500.
# ---------------------------------------------------------------------------

def _actor(request: Request) -> str:
    return (getattr(request.state, "user", {}) or {}).get("sub", "unknown")


def _commit(db: Session, catalog: str, *, deleting: bool = False) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        text = str(getattr(exc, "orig", exc))
        if "foreign key" in text or "still referenced" in text:
            # The same constraint fails for opposite reasons depending on
            # direction: on a delete something still points here; on a write
            # this row points at nothing.
            if deleting:
                raise HTTPException(409, {
                    "message": "Запись используется в других данных "
                               "и не может быть удалена",
                    "catalog": catalog,
                    "hint": "Сначала уберите ссылки на неё, затем повторите.",
                })
            raise HTTPException(422, {
                "message": "Указана ссылка на запись, которой нет",
                "catalog": catalog,
                "hint": "Выберите значение из списка.",
            })
        if "duplicate key" in text or "unique constraint" in text:
            raise HTTPException(409, {
                "message": "Такая запись уже существует",
                "catalog": catalog,
            })
        raise HTTPException(422, {
            "message": "Запись не соответствует правилам базы данных",
            "catalog": catalog,
        })
    except DataError as exc:
        db.rollback()
        text = str(getattr(exc, "orig", exc))
        if "too long" in text or "value too long" in text:
            raise HTTPException(422, {
                "message": "Значение слишком длинное для этого поля",
                "catalog": catalog,
            })
        raise HTTPException(422, {
            "message": "Недопустимое значение поля",
            "catalog": catalog,
        })


@router.put("/{catalog}/{item_id}")
def update_item(catalog: str, item_id: int, payload: Dict[str, Any],
                request: Request, db: Session = Depends(get_db)):
    if _is_custom(catalog):
        from models import CustomCatalogItem as _Item
        item = db.query(_Item).filter(_Item.id == item_id).first()
        if not item:
            raise HTTPException(404, "Not found")
        before = _serialise_custom(item)
        for key in BASE_FIELDS + CUSTOM_ITEM_FIELDS:
            if key in payload:
                setattr(item, key, payload[key])
        _commit(db, catalog)
        db.refresh(item)
        after = _serialise_custom(item)
        db.add(AuditLog(action="update", entity_type=catalog, entity_id=item.id,
                        old_values=before, new_values=after,
                        changed_by=_actor(request)))
        _commit(db, catalog)
        return after

    model, extra = _resolve(catalog)
    row = db.query(model).filter(model.id == item_id).first()
    if not row:
        raise HTTPException(404, "Not found")

    allowed = set(BASE_FIELDS + extra)
    before = _serialise(row, extra)

    for key, value in payload.items():
        if key in allowed:
            setattr(row, key, value)
    _commit(db, catalog)
    db.refresh(row)

    after = _serialise(row, extra)
    db.add(AuditLog(action="update", entity_type=catalog, entity_id=row.id,
                    old_values=before, new_values=after,
                    changed_by=_actor(request)))
    _commit(db, catalog)
    return after


@router.delete("/{catalog}/{item_id}", status_code=204)
def delete_item(catalog: str, item_id: int, request: Request,
                db: Session = Depends(get_db)):
    if _is_custom(catalog):
        from models import CustomCatalogItem as _Item
        item = db.query(_Item).filter(_Item.id == item_id).first()
        if not item:
            raise HTTPException(404, "Not found")
        db.add(AuditLog(action="delete", entity_type=catalog, entity_id=item_id,
                        old_values=_serialise_custom(item),
                        changed_by=_actor(request)))
        db.delete(item)
        _commit(db, catalog, deleting=True)
        return None

    model, extra = _resolve(catalog)
    query = db.query(model).filter(model.id == item_id)
    row = (query.with_for_update() if model is OrgUnit else query).first()
    if not row:
        raise HTTPException(404, "Not found")

    if model is OrgUnit:
        # The ORM nulls children's parent_id when deleting a parent, so SQL
        # foreign-key errors alone cannot protect an organisational subtree.
        from routers.org import unit_usage
        usage = unit_usage(item_id, db)
        if not usage["can_delete"]:
            raise HTTPException(409, {
                "message": "Подразделение нельзя удалить: на него есть ссылки",
                "usage": usage,
                "hint": "Сначала перенесите дочерние подразделения, сотрудников "
                        "и штатные позиции; историю назначений необходимо сохранить.",
            })

    before = _serialise(row, extra)
    db.add(AuditLog(action="delete", entity_type=catalog, entity_id=item_id,
                    old_values=before, changed_by=_actor(request)))
    db.delete(row)
    _commit(db, catalog, deleting=True)
    return None


# ===========================================================================
# USER-DEFINED CATALOGUES
#
# The catalogues above are real tables with real foreign keys, so their set is
# fixed by the schema. These are the ones the organisation invents later. They
# are served through the same shape as the built-ins -- the admin screen calls
# /reference/<name> either way and cannot tell them apart.
# ===========================================================================

@router.get("/custom-catalogs/list")
def list_custom_catalogs(db: Session = Depends(get_db)):
    rows = db.query(CustomCatalog).order_by(CustomCatalog.name_ru).all()
    return {"data": [{
        "id": r.id,
        "code": r.code,
        "name_ru": r.name_ru,
        "name_kk": r.name_kk,
        "name_en": r.name_en,
        "description": r.description,
        "is_active": r.is_active,
        "item_count": len(r.items),
        # The slug the generic endpoints answer to.
        "slug": f"{CUSTOM_PREFIX}{r.code}",
    } for r in rows]}


@router.post("/custom-catalogs/list", status_code=201)
def create_custom_catalog(payload: Dict[str, Any], request: Request,
                          db: Session = Depends(get_db)):
    code = (payload.get("code") or "").strip()
    name_ru = (payload.get("name_ru") or "").strip()
    if not code or not name_ru:
        raise HTTPException(422, "Укажите код и наименование справочника")

    if code in REGISTRY:
        raise HTTPException(409, f"'{code}' — системный справочник, "
                                 f"выберите другой код")
    if db.query(CustomCatalog).filter(CustomCatalog.code == code).first():
        raise HTTPException(409, f"Справочник '{code}' уже существует")

    row = CustomCatalog(
        code=code, name_ru=name_ru,
        name_kk=payload.get("name_kk"), name_en=payload.get("name_en"),
        description=payload.get("description"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="create", entity_type="custom_catalog",
                    entity_id=row.id, new_values={"code": code, "name": name_ru},
                    changed_by=_actor(request)))
    db.commit()
    return {"id": row.id, "code": row.code, "slug": f"{CUSTOM_PREFIX}{row.code}"}


@router.put("/custom-catalogs/list/{catalog_id}")
def update_custom_catalog(catalog_id: int, payload: Dict[str, Any],
                          db: Session = Depends(get_db)):
    row = db.query(CustomCatalog).filter(CustomCatalog.id == catalog_id).first()
    if not row:
        raise HTTPException(404, "Справочник не найден")
    for key in ("name_ru", "name_kk", "name_en", "description", "is_active"):
        if key in payload:
            setattr(row, key, payload[key])
    db.commit()
    return {"id": row.id, "code": row.code}


@router.delete("/custom-catalogs/list/{catalog_id}", status_code=204)
def delete_custom_catalog(catalog_id: int, request: Request,
                          db: Session = Depends(get_db)):
    row = db.query(CustomCatalog).filter(CustomCatalog.id == catalog_id).first()
    if not row:
        raise HTTPException(404, "Справочник не найден")

    db.add(AuditLog(action="delete", entity_type="custom_catalog",
                    entity_id=catalog_id,
                    old_values={"code": row.code, "items": len(row.items)},
                    changed_by=_actor(request)))
    db.delete(row)          # items cascade
    db.commit()
