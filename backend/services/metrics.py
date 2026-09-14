"""Derived employee metrics, computed in the backend -- never typed by a user.

Everything here follows one rule from the specification: tenure is calculated
from the union of work-experience intervals, so two overlapping records are
never counted twice.
"""

from datetime import date
from typing import List, Dict, Tuple, Optional, Set
from sqlalchemy.orm import Session

from models import (
    Employee, WorkExperience, EmployeeMetric, JobFamily,
    AssessmentSession, CompetencyScore,
)

DAYS_PER_YEAR = 365.25


def _merge_intervals(intervals: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    """Union of possibly overlapping [from, to] intervals."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:                      # overlapping or touching
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _total_years(intervals: List[Tuple[date, date]]) -> float:
    merged = _merge_intervals(intervals)
    days = sum((end - start).days for start, end in merged)
    return round(days / DAYS_PER_YEAR, 3)


def _as_interval(row: WorkExperience, today: date) -> Optional[Tuple[date, date]]:
    if not row.date_from:
        return None
    end = row.date_to or today
    if end < row.date_from:
        return None
    return (row.date_from, end)


def _family_with_ancestors(db: Session, family_id: int) -> Set[int]:
    """A family plus its parents, so Marketing Analytics counts toward Analytics."""
    found: Set[int] = set()
    current = db.query(JobFamily).filter(JobFamily.id == family_id).first()
    guard = 0
    while current and guard < 10:
        found.add(current.id)
        current = (
            db.query(JobFamily).filter(JobFamily.id == current.parent_id).first()
            if current.parent_id else None
        )
        guard += 1
    return found


def compute_employee_metrics(db: Session, employee: Employee,
                             today: Optional[date] = None) -> Dict[str, float]:
    """Return every derived figure for one employee, keyed by metric code."""
    today = today or date.today()
    rows = [r for r in employee.work_experience if r.date_from]

    metrics: Dict[str, float] = {}

    # --- total company tenure (internal rows only) -------------------------
    internal = [_as_interval(r, today) for r in rows if r.is_internal]
    metrics["company_experience_years"] = _total_years([i for i in internal if i])

    # --- total professional tenure incl. external employers ---------------
    every = [_as_interval(r, today) for r in rows]
    metrics["total_experience_years"] = _total_years([i for i in every if i])

    # --- per job family (function), inheriting to parent families ---------
    family_ids = {r.job_family_id for r in rows if r.job_family_id}
    for fid in family_ids:
        family = db.query(JobFamily).filter(JobFamily.id == fid).first()
        if not family:
            continue
        # every row whose family is this family or a descendant of it
        matching = []
        for r in rows:
            if not r.job_family_id:
                continue
            if fid in _family_with_ancestors(db, r.job_family_id):
                iv = _as_interval(r, today)
                if iv:
                    matching.append(iv)
        metrics[f"function_experience_years:{family.code}"] = _total_years(matching)

    # --- per organisation-unit type (regional / HQ / foreign) -------------
    by_unit_type: Dict[str, List[Tuple[date, date]]] = {}
    for r in rows:
        if not r.org_unit_type:
            continue
        iv = _as_interval(r, today)
        if iv:
            by_unit_type.setdefault(r.org_unit_type.code, []).append(iv)
    for code, ivs in by_unit_type.items():
        metrics[f"org_unit_experience_years:{code}"] = _total_years(ivs)

    # --- per country ------------------------------------------------------
    by_country: Dict[str, List[Tuple[date, date]]] = {}
    for r in rows:
        if not r.country:
            continue
        iv = _as_interval(r, today)
        if iv:
            by_country.setdefault(r.country.code, []).append(iv)
    for code, ivs in by_country.items():
        metrics[f"country_experience_years:{code}"] = _total_years(ivs)

    # --- management experience -------------------------------------------
    mgmt = [_as_interval(r, today) for r in rows if (r.management_level or 0) > 0]
    metrics["management_experience_years"] = _total_years([i for i in mgmt if i])

    # --- latest competency scores ----------------------------------------
    latest = (
        db.query(AssessmentSession)
        .filter(AssessmentSession.employee_id == employee.id)
        .order_by(AssessmentSession.session_date.desc())
        .all()
    )
    seen_codes: Set[str] = set()
    for session in latest:
        scale_max = float(session.scale.max_value) if session.scale else 10.0
        for score_row in session.scores:
            code = score_row.competency.code
            if code in seen_codes:
                continue          # a newer session already provided this one
            seen_codes.add(code)
            raw = float(score_row.score)
            metrics[f"competency:{code}"] = round(raw, 3)
            # normalised 0..1 so requirements can compare across scales
            if scale_max:
                metrics[f"competency_norm:{code}"] = round(raw / scale_max, 4)

    return metrics


def persist_employee_metrics(db: Session, employee: Employee) -> Dict[str, float]:
    """Recompute and materialise metrics for one employee."""
    values = compute_employee_metrics(db, employee)

    existing = {m.metric_code: m for m in employee.metrics}
    for code, value in values.items():
        if code in existing:
            existing[code].metric_value = value
        else:
            db.add(EmployeeMetric(employee_id=employee.id,
                                  metric_code=code, metric_value=value))
    # drop metrics that no longer apply
    for code, row in existing.items():
        if code not in values:
            db.delete(row)

    db.commit()
    return values


def recompute_all(db: Session) -> int:
    employees = db.query(Employee).all()
    for employee in employees:
        persist_employee_metrics(db, employee)
    return len(employees)
