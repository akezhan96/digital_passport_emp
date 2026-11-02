"""Derived employee metrics, computed in the backend -- never typed by a user.

Everything here follows one rule from the specification: tenure is calculated
from the union of work-experience intervals, so two overlapping records are
never counted twice.
"""

from datetime import date
from typing import List, Dict, Iterable, Tuple, Optional, Set
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from models import (
    Employee, WorkExperience, EmployeeMetric, JobFamily,
    AssessmentSession, CompetencyScore, Competency, EmployeeLanguage, EmployeeEducation,
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


def credited_days(intervals, excluded=()):
    """Inclusive days in the union of work intervals, minus all disposal days."""
    work = _merge_intervals(intervals)
    blocked = _merge_intervals(excluded)
    days = sum((end - start).days + 1 for start, end in work)
    i = j = 0
    while i < len(work) and j < len(blocked):
        left, right = work[i], blocked[j]
        start, end = max(left[0], right[0]), min(left[1], right[1])
        if start <= end:
            days -= (end - start).days + 1
        if left[1] <= right[1]:
            i += 1
        else:
            j += 1
    return days


def _total_years(intervals, excluded=()):
    return round(credited_days(intervals, excluded) / DAYS_PER_YEAR, 3)


def disposal_intervals(db, employee_ids, today):
    """Load exclusions in bounded batches, including the first day of disposal."""
    from models import DisposalPeriod
    result = {}
    ids = list(employee_ids)
    for start in range(0, len(ids), 500):
        rows = (db.query(DisposalPeriod.employee_id, DisposalPeriod.date_from, DisposalPeriod.date_to)
                .filter(DisposalPeriod.employee_id.in_(ids[start:start + 500]), DisposalPeriod.date_from <= today))
        for employee_id, begin, end in rows:
            result.setdefault(employee_id, []).append((begin, min(end or today, today)))
    return result


def employee_tenure_days(db, employee, today):
    blocked = disposal_intervals(db, [employee.id], today).get(employee.id, [])
    every, internal = [], []
    for row in employee.work_experience:
        interval = _as_interval(row, today)
        if interval:
            every.append(interval)
            if row.is_internal:
                internal.append(interval)
    return {'total_days': credited_days(every, blocked), 'company_days': credited_days(internal, blocked),
            'has_work_periods': bool(every)}


def _as_interval(row: WorkExperience, today: date) -> Optional[Tuple[date, date]]:
    if not row.date_from:
        return None
    end = min(row.date_to or today, today)
    if end < row.date_from:
        return None
    return (row.date_from, end)


def build_family_ancestry(db: Session) -> Dict[int, Set[int]]:
    """Every job family mapped to itself plus its ancestors, in one query.

    The hierarchy is a handful of rows and cannot change while a request is
    running, so walking it per career row -- which is what this replaced --
    was paying the database thousands of times for an answer that was already
    known after the first.
    """
    families = db.query(JobFamily).all()
    parent_of = {f.id: f.parent_id for f in families}

    ancestry: Dict[int, Set[int]] = {}
    for family_id in parent_of:
        found: Set[int] = set()
        current = family_id
        guard = 0
        while current is not None and guard < 10:
            if current in found:            # a cycle in the data, not a crash
                break
            found.add(current)
            current = parent_of.get(current)
            guard += 1
        ancestry[family_id] = found
    return ancestry


def _family_with_ancestors(db: Session, family_id: int,
                           ancestry: Optional[Dict[int, Set[int]]] = None
                           ) -> Set[int]:
    """A family plus its parents, so Marketing Analytics counts toward Analytics."""
    if ancestry is not None:
        return ancestry.get(family_id, {family_id})

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
                             today: Optional[date] = None,
                             ancestry: Optional[Dict[int, Set[int]]] = None,
                             families: Optional[Dict[int, JobFamily]] = None,
                             excluded_intervals=None
                             ) -> Dict[str, float]:
    """Return every derived figure for one employee, keyed by metric code.

    `ancestry` and `families` are the job-family hierarchy, read once by the
    caller when it is looping over many employees. Left out, they are read
    here -- correct either way, but one query instead of none.
    """
    today = today or date.today()
    if ancestry is None:
        ancestry = build_family_ancestry(db)
    if families is None:
        families = {f.id: f for f in db.query(JobFamily).all()}
    if excluded_intervals is None:
        excluded_intervals = disposal_intervals(db, [employee.id], today).get(employee.id, [])
    rows = [r for r in employee.work_experience if r.date_from]

    metrics: Dict[str, float] = {}

    # --- total company tenure (internal rows only) -------------------------
    internal = [_as_interval(r, today) for r in rows if r.is_internal]
    metrics["company_experience_years"] = _total_years([i for i in internal if i], excluded_intervals)

    # --- total professional tenure incl. external employers ---------------
    every = [_as_interval(r, today) for r in rows]
    metrics["total_experience_years"] = _total_years([i for i in every if i], excluded_intervals)

    # --- per job family (function), inheriting to parent families ---------
    family_ids = set().union(*(ancestry.get(r.job_family_id, {r.job_family_id})
                              for r in rows if r.job_family_id))
    for fid in family_ids:
        family = families.get(fid)
        if not family:
            continue
        # every row whose family is this family or a descendant of it
        matching = []
        for r in rows:
            if not r.job_family_id:
                continue
            if fid in ancestry.get(r.job_family_id, {r.job_family_id}):
                iv = _as_interval(r, today)
                if iv:
                    matching.append(iv)
        metrics[f"function_experience_years:{family.code}"] = _total_years(matching, excluded_intervals)

    # --- per organisation-unit type (regional / HQ / foreign) -------------
    by_unit_type: Dict[str, List[Tuple[date, date]]] = {}
    for r in rows:
        if not r.org_unit_type:
            continue
        iv = _as_interval(r, today)
        if iv:
            by_unit_type.setdefault(r.org_unit_type.code, []).append(iv)
    for code, ivs in by_unit_type.items():
        metrics[f"org_unit_experience_years:{code}"] = _total_years(ivs, excluded_intervals)

    # --- per country ------------------------------------------------------
    by_country: Dict[str, List[Tuple[date, date]]] = {}
    for r in rows:
        if not r.country:
            continue
        iv = _as_interval(r, today)
        if iv:
            by_country.setdefault(r.country.code, []).append(iv)
    for code, ivs in by_country.items():
        metrics[f"country_experience_years:{code}"] = _total_years(ivs, excluded_intervals)

    # --- management experience -------------------------------------------
    mgmt = [_as_interval(r, today) for r in rows if (r.management_level or 0) > 0]
    metrics["management_experience_years"] = _total_years([i for i in mgmt if i], excluded_intervals)

    # --- latest competency scores ----------------------------------------
    # Off the already-loaded relationship, ordered here: a fresh query per
    # employee is exactly the cost this function is called in a loop to avoid.
    latest = sorted(employee.assessment_sessions,
                    key=lambda row: row.session_date, reverse=True)
    seen_codes: Set[str] = set()
    for session in latest:
        if session.session_type != "professional" or session.status != "confirmed" or session.session_date > today:
            continue
        if session.valid_until and session.valid_until < today:
            continue
        scale_max = float(session.scale.max_value) if session.scale else 10.0
        for score_row in session.scores:
            if score_row.competency.is_confidential:
                continue
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


# ---------------------------------------------------------------------------
# Computing for many employees at once
# ---------------------------------------------------------------------------

def prefetch_for_metrics(db: Session, employees: Iterable[Employee]) -> None:
    """Load everything the computation walks, in a fixed number of statements.

    SQLAlchemy resolves a relationship the first time it is touched, one query
    each. Over five hundred employees with several career rows apiece that is
    thousands of round trips for data that could arrive in six. Loading the
    same objects through the session populates its identity map, so the
    attribute access that follows costs nothing.
    """
    ids = [e.id for e in employees]
    if not ids:
        return

    # Chunked: a single IN list of many thousands of ids is its own problem.
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]
        (db.query(Employee)
         .filter(Employee.id.in_(batch))
         .options(
             selectinload(Employee.work_experience)
             .selectinload(WorkExperience.org_unit_type),
             selectinload(Employee.work_experience)
             .selectinload(WorkExperience.country),
             selectinload(Employee.work_experience)
             .selectinload(WorkExperience.job_family),
             selectinload(Employee.assessment_sessions)
             .selectinload(AssessmentSession.scale),
             selectinload(Employee.assessment_sessions)
             .selectinload(AssessmentSession.scores)
             .selectinload(CompetencyScore.competency).selectinload(Competency.category),
             # Not used by the metric arithmetic itself, but walked by every
             # caller that computes metrics in bulk -- scoring a language
             # requirement, resolving a query field, rendering a CV. Loading
             # them here costs two statements and saves one per employee.
             selectinload(Employee.languages)
             .selectinload(EmployeeLanguage.language),
             selectinload(Employee.languages)
             .selectinload(EmployeeLanguage.level),
             selectinload(Employee.educations)
             .selectinload(EmployeeEducation.level),
             selectinload(Employee.trainings),
         ).all())


def compute_metrics_bulk(db: Session, employees: List[Employee],
                         today: Optional[date] = None
                         ) -> Dict[int, Dict[str, float]]:
    """Derived figures for a whole population, keyed by employee id.

    Identical arithmetic to computing them one at a time -- the difference is
    only in how many times the database is asked for the same reference rows.
    """
    if not employees:
        return {}

    prefetch_for_metrics(db, employees)
    ancestry = build_family_ancestry(db)
    families = {f.id: f for f in db.query(JobFamily).all()}
    today = today or date.today()

    excluded = disposal_intervals(db, [employee.id for employee in employees], today)
    return {
        employee.id: compute_employee_metrics(db, employee, today,
                                              ancestry, families, excluded.get(employee.id, []))
        for employee in employees
    }


def persist_employee_metrics(db: Session, employee: Employee, *, commit=True) -> Dict[str, float]:
    """Recompute and materialise metrics for one employee."""
    values = compute_employee_metrics(db, employee)
    _store_metrics(db, employee, values)
    if commit:
        db.commit()
    return values


def _store_metrics(db: Session, employee: Employee,
                   values: Dict[str, float]) -> None:
    """Write one employee's figures, without committing."""
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


def recompute_all(db: Session) -> int:
    employees = db.query(Employee).all()
    values = compute_metrics_bulk(db, employees)
    for employee in employees:
        _store_metrics(db, employee, values.get(employee.id, {}))
    db.commit()
    return len(employees)


# ---------------------------------------------------------------------------
# Keeping the denormalised "current post" honest
# ---------------------------------------------------------------------------

def reconcile_current_post(db: Session, employee: Employee) -> bool:
    """Point employee.current_position / current_org_unit at the open posting.

    Those two columns are a convenience copy; the career timeline is the fact.
    Any path that changes work experience -- an appointment, a correction, a
    deletion -- can leave the copy stale, and a stale copy shows the wrong
    office next to somebody's name. Returns True when something moved.
    """
    from models import DisposalPeriod
    today = date.today()
    in_disposal = (db.query(DisposalPeriod.id).filter(DisposalPeriod.employee_id == employee.id,
                   DisposalPeriod.date_from <= today,
                   or_(DisposalPeriod.date_to.is_(None), DisposalPeriod.date_to >= today)).first())
    if in_disposal:
        changed = employee.current_org_unit_id is not None or employee.current_position_id is not None
        if changed:
            employee.current_org_unit_id = employee.current_position_id = None
            db.commit()
        return changed
    current = next((r for r in employee.work_experience if r.is_internal and r.date_to is None
                    and r.date_from and r.date_from <= today),
                   None)

    if current is None:
        # No open posting: keep the last known post rather than blanking it,
        # so the card still says where the person last worked.
        return False

    changed = False
    if current.org_unit_id and employee.current_org_unit_id != current.org_unit_id:
        employee.current_org_unit_id = current.org_unit_id
        changed = True
    if current.position_id and employee.current_position_id != current.position_id:
        employee.current_position_id = current.position_id
        changed = True

    if changed:
        db.commit()
    return changed


def reconcile_all_current_posts(db: Session) -> int:
    """Repair every employee whose current post disagrees with their timeline."""
    fixed = 0
    for employee in db.query(Employee).all():
        if reconcile_current_post(db, employee):
            fixed += 1
    return fixed
