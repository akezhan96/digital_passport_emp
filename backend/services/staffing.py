"""The establishment, and who is actually standing in it.

A staffing table answers two questions at once, and they come from different
places:

  * how many posts a unit is *budgeted* for -- that is data, entered by HR and
    stored in ``staffing_positions``;
  * how many of them are *filled* right now -- that is not data, it is a
    consequence of the career record.

Only the first is stored. Occupancy is recomputed from the open work-experience
intervals every time it is asked for, so a unit's staffing table can never
claim a post is free while somebody is sitting in it, or the reverse. A counter
maintained alongside the appointments would drift the first time anyone edited
a career row by hand, and nothing would notice.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence
from datetime import date
from sqlalchemy import or_, func

from sqlalchemy.orm import Session, joinedload

from models import (
    Employee, OrgUnit, Position, StaffingPosition, WorkExperience,
)


# ---------------------------------------------------------------------------
# Occupancy, derived
# ---------------------------------------------------------------------------

def occupancy(db: Session,
              unit_ids: Optional[Sequence[int]] = None
              ) -> Dict[tuple, List[Employee]]:
    """Map (org_unit_id, position_id) -> the employees currently holding it.

    Only open intervals count: a posting that has ended frees its slot.
    """
    query = (db.query(WorkExperience)
             # The holder of each post is read for every row; joined here it
             # arrives with them instead of one query per open posting.
             .options(joinedload(WorkExperience.employee))
             .filter(WorkExperience.is_internal.is_(True), WorkExperience.date_from <= date.today(),
                     or_(WorkExperience.date_to.is_(None), WorkExperience.date_to >= date.today()),
                     WorkExperience.org_unit_id.isnot(None),
                     WorkExperience.position_id.isnot(None)))
    if unit_ids is not None:
        if not unit_ids:
            return {}
        query = query.filter(WorkExperience.org_unit_id.in_(list(unit_ids)))

    held: Dict[tuple, List[Employee]] = {}
    for row in query.all():
        employee = row.employee
        # An archived or departed profile does not hold a post open.
        if employee is None or employee.employment_status != "active" or employee.profile_status == "archived":
            continue
        bucket = held.setdefault((row.org_unit_id, row.position_id), [])
        if all(e.id != employee.id for e in bucket):
            bucket.append(employee)
    return held


def _person(employee: Employee, since=None) -> Dict[str, Any]:
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "personnel_number": employee.personnel_number,
        "anonymous_code": employee.anonymous_code,
        "since": str(since) if since else None,
    }


# ---------------------------------------------------------------------------
# One unit
# ---------------------------------------------------------------------------

def unit_establishment(db: Session, unit_id: int,
                       include_holders: bool = True) -> Dict[str, Any]:
    """The staffing table of a single unit, with occupancy filled in."""
    rows = (db.query(StaffingPosition)
            .options(joinedload(StaffingPosition.position),
                     joinedload(StaffingPosition.grade))
            .filter(StaffingPosition.org_unit_id == unit_id)
            .all())

    held = occupancy(db, [unit_id])

    # The career record can put somebody in a post the establishment does not
    # list -- a leftover from before the table was drawn up, or a post that was
    # removed while still occupied. Those people exist and must be visible, so
    # they are reported separately rather than quietly dropped.
    listed_positions = {r.position_id for r in rows}

    lines: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (
            -(r.position.management_level or 0),
            -(r.grade.rank if r.grade else 0),
            r.position.name_ru)):
        holders = held.get((unit_id, row.position_id), [])
        lines.append({
            "id": row.id,
            "org_unit_id": unit_id,
            "position_id": row.position_id,
            "position_code": row.position.code,
            "position_ru": row.position.name_ru,
            "position_kk": row.position.name_kk,
            "position_en": row.position.name_en,
            "job_family": row.position.job_family.name_ru
            if row.position.job_family else None,
            "grade_id": row.grade_id,
            "grade": row.grade.name_ru if row.grade else (
                row.position.grade.name_ru if row.position.grade else None),
            "headcount": row.headcount,
            "occupied": len(holders),
            "vacant": max(0, row.headcount - len(holders)),
            "over_established": max(0, len(holders) - row.headcount),
            "is_active": row.is_active,
            "notes": row.notes,
            "holders": [_person(e) for e in holders] if include_holders else [],
        })

    unlisted: List[Dict[str, Any]] = []
    for (uid, position_id), holders in held.items():
        if uid != unit_id or position_id in listed_positions:
            continue
        position = db.query(Position).filter(Position.id == position_id).first()
        unlisted.append({
            "position_id": position_id,
            "position_code": position.code if position else None,
            "position_ru": position.name_ru if position else None,
            "position_kk": position.name_kk if position else None,
            "position_en": position.name_en if position else None,
            "occupied": len(holders),
            "holders": [_person(e) for e in holders],
        })

    return {
        "org_unit_id": unit_id,
        "lines": lines,
        "off_establishment": sorted(unlisted,
                                    key=lambda r: r["position_ru"] or ""),
        "totals": _totals(lines, unlisted),
    }


def _totals(lines: Iterable[Dict[str, Any]],
            unlisted: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    lines = list(lines)
    unlisted = list(unlisted)
    established = sum(r["headcount"] for r in lines)
    occupied = sum(min(r["occupied"], r["headcount"]) for r in lines)
    return {
        "established": established,
        "occupied": occupied,
        "vacant": max(0, established - occupied),
        # People in post beyond the budgeted headcount, plus anyone holding a
        # post the table does not list at all.
        "over_established": sum(r["over_established"] for r in lines)
                            + sum(r["occupied"] for r in unlisted),
        "lines": len(lines),
    }


# ---------------------------------------------------------------------------
# Every unit at once
# ---------------------------------------------------------------------------

def totals_by_unit(db: Session) -> Dict[int, Dict[str, int]]:
    """Establishment figures for every unit, for the tree and the overview."""
    rows = db.query(StaffingPosition).all()
    # The overview needs counts, not every employee's personal file and career
    # rows. DISTINCT preserves occupancy()'s deduplication of overlapping rows.
    held_rows = (db.query(WorkExperience.org_unit_id, WorkExperience.position_id,
                          func.count(func.distinct(WorkExperience.employee_id)))
        .join(Employee, Employee.id == WorkExperience.employee_id)
        .filter(Employee.employment_status == "active", Employee.profile_status != "archived", WorkExperience.is_internal.is_(True),
                WorkExperience.date_from <= date.today(),
                or_(WorkExperience.date_to.is_(None), WorkExperience.date_to >= date.today()),
                WorkExperience.org_unit_id.isnot(None), WorkExperience.position_id.isnot(None))
        .group_by(WorkExperience.org_unit_id, WorkExperience.position_id).all())
    held = {(unit_id, position_id): count for unit_id, position_id, count in held_rows}

    by_unit: Dict[int, Dict[str, int]] = {}
    listed: Dict[int, set] = {}

    for row in rows:
        count = held.get((row.org_unit_id, row.position_id), 0)
        bucket = by_unit.setdefault(row.org_unit_id, {
            "established": 0, "occupied": 0, "vacant": 0,
            "over_established": 0, "lines": 0,
        })
        bucket["established"] += row.headcount
        bucket["occupied"] += min(count, row.headcount)
        bucket["over_established"] += max(0, count - row.headcount)
        bucket["lines"] += 1
        listed.setdefault(row.org_unit_id, set()).add(row.position_id)

    for (unit_id, position_id), count in held.items():
        if position_id in listed.get(unit_id, set()):
            continue
        bucket = by_unit.setdefault(unit_id, {
            "established": 0, "occupied": 0, "vacant": 0,
            "over_established": 0, "lines": 0,
        })
        bucket["over_established"] += count

    for bucket in by_unit.values():
        bucket["vacant"] = max(0, bucket["established"] - bucket["occupied"])

    return by_unit


# ---------------------------------------------------------------------------
# The guard used when somebody is appointed
# ---------------------------------------------------------------------------

def check_vacancy_available(db: Session, unit_id: int, position_id: int,
                            exclude_employee_id: Optional[int] = None
                            ) -> Optional[Dict[str, Any]]:
    """Return a description of the problem, or None when the post is free.

    A unit with no establishment at all is not yet staffed on paper, so nothing
    is refused there -- the check only bites once somebody has drawn the table
    up. That keeps the guard from blocking data entry in a half-configured
    system while still making the establishment mean something the moment it
    exists.
    """
    unit_lines = (db.query(StaffingPosition)
                  .filter(StaffingPosition.org_unit_id == unit_id).all())
    if not unit_lines:
        return None

    line = next((r for r in unit_lines if r.position_id == position_id), None)
    if line is None:
        unit = db.query(OrgUnit).filter(OrgUnit.id == unit_id).first()
        position = db.query(Position).filter(Position.id == position_id).first()
        return {
            "reason": "not_established",
            "message": "Этой должности нет в штатном расписании подразделения",
            "org_unit": unit.name_ru if unit else None,
            "position": position.name_ru if position else None,
            "hint": "Добавьте должность в штатное расписание подразделения "
                    "или выберите другую.",
        }

    if not line.is_active:
        return {
            "reason": "inactive",
            "message": "Штатная единица отключена",
            "hint": "Включите штатную единицу или выберите другую должность.",
        }

    holders = occupancy(db, [unit_id]).get((unit_id, position_id), [])
    if exclude_employee_id is not None:
        holders = [e for e in holders if e.id != exclude_employee_id]

    if len(holders) >= line.headcount:
        return {
            "reason": "full",
            "message": "Все штатные единицы по этой должности заняты",
            "headcount": line.headcount,
            "occupied": len(holders),
            "occupied_by": [e.full_name for e in holders],
            "hint": "Увеличьте количество единиц в штатном расписании "
                    "или освободите занятую.",
        }

    return None
