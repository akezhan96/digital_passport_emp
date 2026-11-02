"""Organisational structure and employee segments.

Two views of the same workforce:

  * the tree -- the org hierarchy with headcount at every level, so a manager
    can see the whole company and drill down to the people in one unit;
  * segments -- the standing questions about assignment state: who has no
    posting yet, who has come back from a foreign office, who is waiting to
    leave for one.

Segments are derived from the career timeline and the decision record rather
than stored as a flag, so they cannot drift out of step with the facts.
"""

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from database import get_db
from services.staffing import totals_by_unit
from models import (
    Employee, OrgUnit, OrgUnitType, WorkExperience, Vacancy,
    MatchingResult, MatchingRun, Decision, AuditLog, Position, StaffingPosition, DisposalPeriod,
)

router = APIRouter(prefix="/api/v1/org", tags=["organisation"])

FOREIGN_TYPES = ("FOREIGN",)


# ---------------------------------------------------------------------------
# Segment predicates
# ---------------------------------------------------------------------------

def _current_posting(employee: Employee) -> Optional[WorkExperience]:
    return next((r for r in employee.work_experience if r.date_to is None), None)


def _is_unassigned(db: Session, employee: Employee) -> bool:
    """No open posting at all -- newly entered, or between assignments."""
    return _current_posting(employee) is None


def _is_abroad(db: Session, employee: Employee) -> bool:
    current = _current_posting(employee)
    return bool(current and current.org_unit_type
                and current.org_unit_type.code in FOREIGN_TYPES)


def _is_returned(db: Session, employee: Employee) -> bool:
    """Has completed a foreign posting and is now working somewhere else."""
    if _is_abroad(db, employee):
        return False
    return any(r.date_to is not None and r.org_unit_type
               and r.org_unit_type.code in FOREIGN_TYPES
               for r in employee.work_experience)


def _awaiting_foreign(db: Session, employee: Employee) -> bool:
    """Selected for a vacancy in a foreign unit, but not yet moved there.

    Read from the decision record: a 'selected' decision on a foreign vacancy
    with no appointment yet pointing at that result.
    """
    if _is_abroad(db, employee):
        return False
    return employee.id in _awaiting_foreign_ids(db)


SEGMENTS = {
    "all": {
        "name_ru": "Все сотрудники", "name_kk": "Барлық қызметкерлер",
        "name_en": "All employees",
        "hint_ru": "Полный список действующих сотрудников.",
        "predicate": lambda db, e: True,
    },
    "unassigned": {
        "name_ru": "В распоряжении", "name_kk": "Қарамағында",
        "name_en": "At disposal",
        "hint_ru": "Нет действующей записи трудовой деятельности.",
        "predicate": _is_unassigned,
    },
    "abroad": {
        "name_ru": "В заграничном представительстве", "name_kk": "Шетелдік өкілдікте",
        "name_en": "On a foreign assignment",
        "hint_ru": "Текущая должность — в заграничном представительстве.",
        "predicate": _is_abroad,
    },
    "returned": {
        "name_ru": "Вернулись из заграничных представительств",
        "name_kk": "Шетелдік өкілдіктерден оралғандар",
        "name_en": "Returned from a foreign office",
        "hint_ru": "Завершили зарубежное назначение и работают внутри страны.",
        "predicate": _is_returned,
    },
    "awaiting_foreign": {
        "name_ru": "Ожидают зарубежного назначения",
        "name_kk": "Шетелдік тағайындауды күтуде",
        "name_en": "Awaiting a foreign assignment",
        "hint_ru": "Выбраны на зарубежную вакансию, назначение ещё не оформлено.",
        "predicate": _awaiting_foreign,
    },
}


def _workforce_query(db: Session, ordered: bool = False):
    """Active employees with everything the segment predicates read.

    Without the eager options each predicate resolves the career record one
    employee at a time; with five predicates over several hundred profiles
    that is thousands of round trips to answer six counts.
    """
    query = db.query(Employee).filter(Employee.employment_status == "active")
    if ordered:
        query = query.order_by(Employee.last_name, Employee.first_name, Employee.id)
    return query.options(
        selectinload(Employee.work_experience)
        .selectinload(WorkExperience.org_unit_type),
        selectinload(Employee.work_experience)
        .selectinload(WorkExperience.org_unit),
        selectinload(Employee.work_experience)
        .selectinload(WorkExperience.position),
        selectinload(Employee.current_position),
        selectinload(Employee.current_org_unit),
    )


def _workforce(db: Session, ordered: bool = False) -> List[Employee]:
    return _workforce_query(db, ordered).all()


def _awaiting_foreign_ids(db: Session) -> set:
    """Everyone selected for a post abroad who has not yet moved there.

    One query for the whole workforce. Asked per employee -- which is what
    this replaced -- it joined decisions to results to runs to vacancies once
    for each person, against the two tables that grow fastest in the system.
    """
    cached = getattr(db, "_awaiting_foreign_cache", None)
    if cached is not None:
        return cached

    rows = (
        db.query(MatchingResult.employee_id, MatchingResult.id)
        .join(Decision, Decision.result_id == MatchingResult.id)
        .join(MatchingRun, MatchingResult.run_id == MatchingRun.id)
        .join(Vacancy, MatchingRun.vacancy_id == Vacancy.id)
        .join(OrgUnit, Vacancy.org_unit_id == OrgUnit.id)
        .join(OrgUnitType, OrgUnit.unit_type_id == OrgUnitType.id)
        .filter(Decision.decision == "selected",
                OrgUnitType.code.in_(FOREIGN_TYPES))
        .all()
    )
    selected: Dict[int, set] = {}
    for employee_id, result_id in rows:
        selected.setdefault(employee_id, set()).add(result_id)

    # A selection that has already been acted on no longer counts as waiting.
    acted = (db.query(WorkExperience.employee_id,
                      WorkExperience.source_result_id)
             .filter(WorkExperience.source_result_id.isnot(None)).all())
    for employee_id, result_id in acted:
        if employee_id in selected:
            selected[employee_id].discard(result_id)

    found = {eid for eid, results in selected.items() if results}
    try:
        db._awaiting_foreign_cache = found
    except AttributeError:
        pass
    return found


def _person(db: Session, employee: Employee) -> Dict[str, Any]:
    current = _current_posting(employee)
    position = current.position if current and current.position else employee.current_position
    org_unit = current.org_unit if current and current.org_unit else employee.current_org_unit
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "anonymous_code": employee.anonymous_code,
        "personnel_number": employee.personnel_number,
        # Read the open posting first: it is the fact, while the columns on
        # Employee are a convenience copy that can lag behind it.
        "position": ((current.position.name_ru if current and current.position
                      else None)
                     or (employee.current_position.name_ru
                         if employee.current_position else None)),
        "position_kk": position.name_kk if position else None,
        "org_unit": ((current.org_unit.name_ru if current and current.org_unit
                      else None)
                     or (employee.current_org_unit.name_ru
                         if employee.current_org_unit else None)),
        "org_unit_kk": org_unit.name_kk if org_unit else None,
        "org_unit_id": ((current.org_unit_id if current else None)
                        or employee.current_org_unit_id),
        "unit_type": (current.org_unit_type.name_ru
                      if current and current.org_unit_type else None),
        "unit_type_kk": (current.org_unit_type.name_kk
                         if current and current.org_unit_type else None),
        "unit_type_code": (current.org_unit_type.code
                           if current and current.org_unit_type else None),
        "profile_status": employee.profile_status,
        "since": str(current.date_from) if current else None,
    }


@router.get("/segments")
def list_segments(db: Session = Depends(get_db)):
    """Every segment with its current headcount."""
    employees = _workforce(db)

    out = []
    for code, segment in SEGMENTS.items():
        count = sum(1 for e in employees if segment["predicate"](db, e))
        out.append({
            "code": code,
            "name_ru": segment["name_ru"],
            "name_kk": segment["name_kk"],
            "name_en": segment["name_en"],
            "hint_ru": segment.get("hint_ru"),
            "count": count,
        })
    return {"data": out, "total": len(employees)}


@router.get("/segments/{code}")
def segment_members(code: str, db: Session = Depends(get_db),
                    offset: int = Query(0, ge=0),
                    limit: Optional[int] = Query(None, ge=1, le=100),
                    q: str = Query("", max_length=200)):
    segment = SEGMENTS.get(code)
    if not segment:
        raise HTTPException(404, f"Неизвестная выборка '{code}'. "
                                 f"Доступны: {', '.join(SEGMENTS)}")

    employees = _workforce(db, ordered=True)
    members = [e for e in employees if segment["predicate"](db, e)]
    if q.strip():
        words = q.casefold().strip().split()
        members = [e for e in members if all(word in
            f"{e.full_name} {e.personnel_number or ''} {e.anonymous_code}".casefold()
            for word in words)]
    count = len(members)
    page = members[offset:offset + limit] if limit is not None else members[offset:]

    return {
        "code": code,
        "name_ru": segment["name_ru"],
        "name_kk": segment["name_kk"],
        "name_en": segment["name_en"],
        "count": count,
        "offset": offset,
        "limit": limit,
        "data": [_person(db, e) for e in page],
    }


# ---------------------------------------------------------------------------
# Organisational tree
# ---------------------------------------------------------------------------

def _natural_key(text: str):
    """Sort "Подразделение 2" before "Подразделение 10" -- plain text sorting puts 10 first."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text or "")]


@router.get("/tree")
def org_tree(include_employees: bool = Query(True),
             db: Session = Depends(get_db)):
    """The unit hierarchy with headcount, rolled up to every parent."""
    units = sorted(db.query(OrgUnit).options(
                       selectinload(OrgUnit.unit_type),
                       selectinload(OrgUnit.country)).all(),
                   key=lambda u: (u.parent_id is None and u.code == "HQ", _natural_key(u.name_ru)))
    employees = _workforce(db, ordered=True) if include_employees else []

    by_unit: Dict[Optional[int], List[Employee]] = {}
    for employee in employees:
        by_unit.setdefault(employee.current_org_unit_id, []).append(employee)
    counts = (dict(db.query(Employee.current_org_unit_id, func.count(Employee.id))
        .filter(Employee.employment_status == "active")
        .group_by(Employee.current_org_unit_id).all()) if not include_employees
        else {key: len(value) for key, value in by_unit.items()})

    children: Dict[Optional[int], List[OrgUnit]] = {}
    for unit in units:
        children.setdefault(unit.parent_id, []).append(unit)

    # How many posts each unit is budgeted for, and how many are filled. The
    # figures are derived from the career record, not stored, so they cannot
    # disagree with the people listed under the same node.
    staffing = totals_by_unit(db)

    def build(unit: OrgUnit) -> Dict[str, Any]:
        own = by_unit.get(unit.id, [])
        kids = [build(child) for child in children.get(unit.id, [])]
        # Roll the count up so a parent shows the whole sub-tree.
        own_count = counts.get(unit.id, 0)
        total = own_count + sum(k["total_count"] for k in kids)

        figures = staffing.get(unit.id, {})
        established = figures.get("established", 0)
        filled = figures.get("occupied", 0)
        node = {
            "id": unit.id,
            "code": unit.code,
            "name_ru": unit.name_ru,
            "name_kk": unit.name_kk,
            "name_en": unit.name_en,
            "region": unit.region,
            "unit_type": unit.unit_type.name_ru if unit.unit_type else None,
            "unit_type_kk": unit.unit_type.name_kk if unit.unit_type else None,
            "unit_type_code": unit.unit_type.code if unit.unit_type else None,
            "unit_type_id": unit.unit_type_id,
            "country": unit.country.name_ru if unit.country else None,
            "country_kk": unit.country.name_kk if unit.country else None,
            "country_id": unit.country_id,
            "parent_id": unit.parent_id,
            "own_count": own_count,
            "total_count": total,
            "established": established,
            "occupied": filled,
            "vacant": max(0, established - filled),
            "over_established": figures.get("over_established", 0),
            "staffing_lines": figures.get("lines", 0),
            # Whole-branch figures, so a parent shows what it governs.
            "established_total": established
                                 + sum(k["established_total"] for k in kids),
            "occupied_total": filled + sum(k["occupied_total"] for k in kids),
            "children": kids,
        }
        node["vacant_total"] = max(
            0, node["established_total"] - node["occupied_total"])
        if include_employees:
            node["employees"] = [_person(db, e) for e in own]
        return node

    roots = [build(unit) for unit in children.get(None, [])]
    unplaced = by_unit.get(None, [])

    return {
        "roots": roots,
        "total_employees": sum(counts.values()),
        "establishment": {
            "established": sum(f.get("established", 0)
                               for f in staffing.values()),
            "occupied": sum(f.get("occupied", 0) for f in staffing.values()),
            "vacant": sum(max(0, f.get("established", 0) - f.get("occupied", 0))
                          for f in staffing.values()),
        },
        "unplaced": {
            "count": counts.get(None, 0),
            "employees": [_person(db, e) for e in unplaced]
            if include_employees else [],
        },
    }


@router.get("/units/{unit_id}/members")
def unit_members(unit_id: int, db: Session = Depends(get_db),
                 offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                 q: str = Query("", max_length=200)):
    """Load only one page of a selected unit, never all personal files."""
    if not db.query(OrgUnit.id).filter(OrgUnit.id == unit_id).first():
        raise HTTPException(404, "Подразделение не найдено / Бөлімше табылмады")
    query = _workforce_query(db, ordered=True).filter(Employee.current_org_unit_id == unit_id)
    for word in q.strip().split():
        pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(*(column.ilike(pattern, escape="\\") for column in
            (Employee.first_name, Employee.last_name, Employee.middle_name,
             Employee.personnel_number, Employee.anonymous_code))))
    total = query.order_by(None).count()
    return {"unit_id": unit_id, "total": total, "offset": offset, "limit": limit,
            "data": [_person(db, employee) for employee in query.offset(offset).limit(limit).all()]}


# ---------------------------------------------------------------------------
# Editing the structure
#
# Units are reference data, so the generic catalogue endpoints can already
# create and rename them. What those cannot do is refuse a delete that would
# orphan a sub-tree or strand employees, or move a whole branch safely -- both
# of which need to know about the hierarchy.
# ---------------------------------------------------------------------------


def _actor(request: Request) -> str:
    return (getattr(request.state, "user", {}) or {}).get("sub", "unknown")


def _descendants(db: Session, unit_id: int) -> List[int]:
    """Every unit below this one, breadth-first."""
    found: List[int] = []
    frontier = [unit_id]
    guard = 0
    while frontier and guard < 100:
        rows = db.query(OrgUnit).filter(OrgUnit.parent_id.in_(frontier)).all()
        frontier = [r.id for r in rows]
        found.extend(frontier)
        guard += 1
    return found


@router.get("/units/{unit_id}/usage")
def unit_usage(unit_id: int, db: Session = Depends(get_db)):
    """What would be affected by changing or removing this unit."""
    unit = db.query(OrgUnit).filter(OrgUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404, "Подразделение не найдено")

    children = db.query(OrgUnit).filter(OrgUnit.parent_id == unit_id).count()
    employees = db.query(Employee).filter(
        Employee.current_org_unit_id == unit_id).count()
    disposals = db.query(DisposalPeriod).filter(or_(
        DisposalPeriod.org_unit_id == unit_id, DisposalPeriod.previous_org_unit_id == unit_id,
        DisposalPeriod.closed_work_post['org_unit_id'].as_integer() == unit_id)).count()
    postings = db.query(WorkExperience).filter(
        WorkExperience.org_unit_id == unit_id).count()
    vacancies = db.query(Vacancy).filter(Vacancy.org_unit_id == unit_id).count()
    staffing = db.query(StaffingPosition).filter(
        StaffingPosition.org_unit_id == unit_id).count()

    return {
        "id": unit_id,
        "children": children,
        "employees": employees,
        "work_experience_rows": postings,
        "disposal_periods": disposals,
        "vacancies": vacancies,
        "staffing_lines": staffing,
        "can_delete": children == 0 and employees == 0
                      and postings == 0 and vacancies == 0 and staffing == 0 and disposals == 0,
    }


@router.delete("/units/{unit_id}", status_code=204)
def delete_unit(unit_id: int, request: Request,
                db: Session = Depends(get_db)):
    """Remove a unit, but only when nothing depends on it.

    Deleting a unit that still holds people or history would either fail on a
    foreign key deep inside a transaction or silently detach records, so the
    check happens up front and says exactly what is in the way.
    """
    unit = db.query(OrgUnit).filter(OrgUnit.id == unit_id).with_for_update().first()
    if not unit:
        raise HTTPException(404, "Подразделение не найдено")

    usage = unit_usage(unit_id, db)
    if not usage["can_delete"]:
        raise HTTPException(422, {
            "message": "Подразделение нельзя удалить: на него есть ссылки",
            "children": usage["children"],
            "employees": usage["employees"],
            "work_experience_rows": usage["work_experience_rows"],
            "disposal_periods": usage["disposal_periods"],
            "vacancies": usage["vacancies"],
            "staffing_lines": usage["staffing_lines"],
            "hint": "Сначала перенесите дочерние подразделения, сотрудников "
                    "и штатные позиции; историю назначений необходимо сохранить.",
        })

    db.add(AuditLog(action="delete", entity_type="org_unit", entity_id=unit_id,
                    old_values={"code": unit.code, "name": unit.name_ru},
                    changed_by=_actor(request)))
    db.delete(unit)
    db.commit()


@router.put("/units/{unit_id}/parent")
def move_unit(unit_id: int, payload: Dict[str, Any], request: Request,
              db: Session = Depends(get_db)):
    """Re-parent a unit, refusing moves that would create a cycle."""
    unit = db.query(OrgUnit).filter(OrgUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(404, "Подразделение не найдено")

    # An absent key is not the same as an explicit null: without this an empty
    # body would read as "move to the top level" and silently detach a branch.
    if "parent_id" not in payload:
        raise HTTPException(422, "Не указано новое вышестоящее подразделение")

    new_parent_id = payload["parent_id"]
    if new_parent_id is not None:
        try:
            new_parent_id = int(new_parent_id)
        except (TypeError, ValueError):
            raise HTTPException(422, "Некорректный идентификатор подразделения")

    if new_parent_id == unit_id:
        raise HTTPException(422, "Подразделение не может подчиняться само себе")

    if new_parent_id is not None:
        parent = db.query(OrgUnit).filter(OrgUnit.id == new_parent_id).first()
        if not parent:
            raise HTTPException(422, "Новое родительское подразделение не найдено")
        # Moving a unit under its own descendant would detach the branch from
        # the tree entirely and make the walk loop forever.
        if new_parent_id in _descendants(db, unit_id):
            raise HTTPException(422, {
                "message": "Нельзя подчинить подразделение его же дочернему",
                "unit": unit.name_ru, "target": parent.name_ru,
            })

    before = unit.parent_id
    unit.parent_id = new_parent_id
    db.commit()

    db.add(AuditLog(action="move", entity_type="org_unit", entity_id=unit_id,
                    old_values={"parent_id": before},
                    new_values={"parent_id": new_parent_id},
                    changed_by=_actor(request)))
    db.commit()
    return {"id": unit_id, "parent_id": new_parent_id}
