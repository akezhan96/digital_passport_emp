"""Editing the establishment: which posts exist in a unit, and how many.

Reading is open to every signed-in user -- an analyst has to be able to see
where the free posts are. Writing is admin-only, gated by the middleware, and
every change is written to the history like any other structural edit.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import AuditLog, OrgUnit, Position, PositionGrade, StaffingPosition
from services.staffing import (
    occupancy, totals_by_unit, unit_establishment,
)

router = APIRouter(prefix="/api/v1", tags=["staffing"])


def _actor(request: Request) -> str:
    return (getattr(request.state, "user", {}) or {}).get("sub", "unknown")


def _unit_or_404(db: Session, unit_id: int) -> OrgUnit:
    unit = db.query(OrgUnit).filter(OrgUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404, "Подразделение не найдено")
    return unit


def _as_id(value: Any, field: str) -> Optional[int]:
    """Coerce an id from the request, or say which field is wrong.

    Passing a string straight into a query builds SQL the database rejects,
    which surfaces as a 500 for what is really a typo.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(422, f"Некорректный идентификатор: {field}")


def _grade_or_none(db: Session, value: Any) -> Optional[int]:
    """A grade the catalogue actually holds, or nothing."""
    grade_id = _as_id(value, "grade_id")
    if grade_id is None:
        return None
    if not db.query(PositionGrade).filter(PositionGrade.id == grade_id).first():
        raise HTTPException(422, "Указан разряд, которого нет в справочнике")
    return grade_id


def _headcount(payload: Dict[str, Any], default: Optional[int] = None) -> int:
    raw = payload.get("headcount", default)
    if raw is None:
        raise HTTPException(422, "Укажите количество штатных единиц")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(422, "Количество единиц должно быть числом")
    if value < 0:
        raise HTTPException(422, "Количество единиц не может быть отрицательным")
    if value > 10000:
        raise HTTPException(422, "Слишком большое количество единиц")
    return value


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@router.get("/org/units/{unit_id}/staffing")
def get_unit_staffing(unit_id: int, db: Session = Depends(get_db)):
    """The staffing table of one unit, with occupancy derived from careers."""
    unit = _unit_or_404(db, unit_id)
    body = unit_establishment(db, unit_id)
    body.update({
        "code": unit.code,
        "name_ru": unit.name_ru,
        "name_kk": unit.name_kk,
        "name_en": unit.name_en,
    })
    return body


@router.get("/staffing/summary")
def staffing_summary(db: Session = Depends(get_db)):
    """Establishment figures for every unit, plus a company-wide total."""
    per_unit = totals_by_unit(db)
    units = db.query(OrgUnit).options(
        joinedload(OrgUnit.unit_type)).all()

    rows = []
    for unit in units:
        figures = per_unit.get(unit.id, {
            "established": 0, "occupied": 0, "vacant": 0,
            "over_established": 0, "lines": 0,
        })
        rows.append({
            "org_unit_id": unit.id,
            "code": unit.code,
            "name_ru": unit.name_ru,
            "name_kk": unit.name_kk,
            "name_en": unit.name_en,
            "unit_type": unit.unit_type.name_ru if unit.unit_type else None,
            "unit_type_code": unit.unit_type.code if unit.unit_type else None,
            "parent_id": unit.parent_id,
            **figures,
        })

    rows.sort(key=lambda r: (-r["established"], r["name_ru"]))

    return {
        "data": rows,
        "totals": {
            key: sum(r[key] for r in rows)
            for key in ("established", "occupied", "vacant",
                        "over_established", "lines")
        },
    }


@router.get("/staffing/vacant")
def vacant_posts(org_unit_id: Optional[int] = None,
                 db: Session = Depends(get_db)):
    """Every free post, so an appointment or a vacancy can start from one."""
    # Each row is rendered with its unit, post and grade; joined here they
    # arrive with the row instead of three queries apiece.
    query = (db.query(StaffingPosition)
             .options(joinedload(StaffingPosition.org_unit)
                      .joinedload(OrgUnit.unit_type),
                      joinedload(StaffingPosition.position),
                      joinedload(StaffingPosition.grade))
             .filter(StaffingPosition.is_active.is_(True)))
    if org_unit_id:
        query = query.filter(StaffingPosition.org_unit_id == org_unit_id)

    rows = query.all()
    held = occupancy(db, [r.org_unit_id for r in rows] or None)

    out: List[Dict[str, Any]] = []
    for row in rows:
        taken = len(held.get((row.org_unit_id, row.position_id), []))
        free = row.headcount - taken
        if free <= 0:
            continue
        out.append({
            "staffing_id": row.id,
            "org_unit_id": row.org_unit_id,
            "org_unit_ru": row.org_unit.name_ru,
            "org_unit_kk": row.org_unit.name_kk,
            "org_unit_en": row.org_unit.name_en,
            "unit_type_code": row.org_unit.unit_type.code
            if row.org_unit.unit_type else None,
            "position_id": row.position_id,
            "position_ru": row.position.name_ru,
            "position_kk": row.position.name_kk,
            "position_en": row.position.name_en,
            "grade": row.grade.name_ru if row.grade else None,
            "vacant": free,
            "headcount": row.headcount,
        })

    out.sort(key=lambda r: (r["org_unit_ru"], r["position_ru"]))
    return {"data": out, "count": sum(r["vacant"] for r in out)}


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

@router.post("/org/units/{unit_id}/staffing", status_code=201)
def add_staffing_line(unit_id: int, payload: Dict[str, Any], request: Request,
                      db: Session = Depends(get_db)):
    """Establish a post in a unit."""
    unit = _unit_or_404(db, unit_id)

    position_id = _as_id(payload.get("position_id"), "position_id")
    db.query(OrgUnit).filter(OrgUnit.id == unit_id).with_for_update().one()
    position = (db.query(Position).filter(Position.id == position_id).first()
                if position_id is not None else None)
    if not position:
        raise HTTPException(422, "Укажите должность из справочника")

    existing = (db.query(StaffingPosition)
                .filter(StaffingPosition.org_unit_id == unit_id,
                        StaffingPosition.position_id == position.id)
                .first())
    if existing:
        raise HTTPException(409, {
            "message": "Эта должность уже есть в штатном расписании "
                       "подразделения",
            "hint": "Измените количество единиц в существующей строке.",
            "staffing_id": existing.id,
        })

    row = StaffingPosition(
        org_unit_id=unit_id,
        position_id=position.id,
        headcount=_headcount(payload, 1),
        grade_id=(_grade_or_none(db, payload.get("grade_id"))
                  or position.grade_id),
        notes=payload.get("notes"),
        is_active=payload.get("is_active", True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(
        action="create", entity_type="staffing_position", entity_id=row.id,
        new_values={"org_unit": unit.name_ru, "position": position.name_ru,
                    "headcount": row.headcount},
        changed_by=_actor(request)))
    db.commit()

    return unit_establishment(db, unit_id)


@router.put("/staffing/{line_id}")
def update_staffing_line(line_id: int, payload: Dict[str, Any],
                         request: Request, db: Session = Depends(get_db)):
    """Change a post's headcount, grade or note.

    The headcount cannot drop below the number of people currently in post:
    that would make the table claim an establishment the career record openly
    contradicts.
    """
    row = db.query(StaffingPosition).filter(
        StaffingPosition.id == line_id).first()
    if not row:
        raise HTTPException(404, "Штатная единица не найдена")

    before = {"headcount": row.headcount, "grade_id": row.grade_id,
              "is_active": row.is_active}
    db.query(OrgUnit).filter(OrgUnit.id == row.org_unit_id).with_for_update().one()

    if "headcount" in payload:
        wanted = _headcount(payload)
        taken = len(occupancy(db, [row.org_unit_id])
                    .get((row.org_unit_id, row.position_id), []))
        if wanted < taken:
            raise HTTPException(422, {
                "message": "Нельзя сократить штат ниже числа занятых единиц",
                "occupied": taken,
                "requested": wanted,
                "hint": "Сначала переведите или освободите сотрудников.",
            })
        row.headcount = wanted

    if "grade_id" in payload:
        row.grade_id = _grade_or_none(db, payload["grade_id"])
    if "notes" in payload:
        row.notes = payload["notes"]
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])

    db.commit()

    db.add(AuditLog(
        action="update", entity_type="staffing_position", entity_id=row.id,
        old_values=before,
        new_values={"headcount": row.headcount, "grade_id": row.grade_id,
                    "is_active": row.is_active},
        changed_by=_actor(request)))
    db.commit()

    return unit_establishment(db, row.org_unit_id)


@router.delete("/staffing/{line_id}", status_code=204)
def delete_staffing_line(line_id: int, request: Request,
                         db: Session = Depends(get_db)):
    """Remove a post from the establishment, unless somebody is in it."""
    row = db.query(StaffingPosition).filter(
        StaffingPosition.id == line_id).first()
    if not row:
        raise HTTPException(404, "Штатная единица не найдена")

    db.query(OrgUnit).filter(OrgUnit.id == row.org_unit_id).with_for_update().one()
    holders = occupancy(db, [row.org_unit_id]).get(
        (row.org_unit_id, row.position_id), [])
    if holders:
        raise HTTPException(422, {
            "message": "Должность занята и не может быть удалена из штатного "
                       "расписания",
            "occupied_by": [e.full_name for e in holders],
            "hint": "Сначала переведите сотрудников на другие должности.",
        })

    db.add(AuditLog(
        action="delete", entity_type="staffing_position", entity_id=line_id,
        old_values={"org_unit": row.org_unit.name_ru,
                    "position": row.position.name_ru,
                    "headcount": row.headcount},
        changed_by=_actor(request)))
    db.delete(row)
    db.commit()
