"""Career actions for the shared work-experience timeline."""
from datetime import date, timedelta

from sqlalchemy import or_
from models import (AuditLog, Attachment, CustomFieldValue, MatchingResult, MatchingRun,
                    Vacancy, DisposalPeriod, Employee, Position, OrgUnit)


def lock_employee(db, employee_id):
    return db.query(Employee).filter_by(id=employee_id).with_for_update().populate_existing().first()


def overlaps_disposal(db, employee_id, start, end):
    query = db.query(DisposalPeriod.id).filter(DisposalPeriod.employee_id == employee_id,
        or_(DisposalPeriod.date_to.is_(None), DisposalPeriod.date_to >= start))
    if end is not None:
        query = query.filter(DisposalPeriod.date_from <= end)
    return query.first() is not None


def close_disposal_on_exit(db, employee):
    period = db.query(DisposalPeriod).filter_by(employee_id=employee.id, date_to=None).one_or_none()
    if period:
        period.date_to = date.today()


def work_post_snapshot(row):
    return {"from": str(row.date_from), "position_id": row.position_id, "org_unit_id": row.org_unit_id}


def disposal_undo_available(db, employee, period):
    if (period.date_to is not None or employee.employment_status != "active"
            or employee.profile_status == "archived" or employee.current_position_id is not None
            or employee.current_org_unit_id is not None):
        return False
    if any(r.is_internal and (r.date_to is None or r.date_to >= period.date_from)
           for r in employee.work_experience):
        return False
    if period.closed_work_id is not None and not any(
            r.id == period.closed_work_id and r.is_internal and r.date_to == period.date_from - timedelta(days=1)
            and work_post_snapshot(r) == period.closed_work_post
            for r in employee.work_experience):
        return False
    return ((period.previous_position_id is None or db.get(Position, period.previous_position_id) is not None)
            and (period.previous_org_unit_id is None or db.get(OrgUnit, period.previous_org_unit_id) is not None))


def appointment_events(db, employee):
    """Return audit evidence by period. A None value marks ambiguous legacy provenance."""
    by_id = {row.id: row for row in employee.work_experience}
    by_date = {}
    for row in by_id.values():
        by_date.setdefault((str(row.date_from), row.appointment_type), []).append(row.id)
    events = {}
    if not by_id:
        return events
    audits = (db.query(AuditLog).filter(AuditLog.action.in_(('appointment', 'appointment_undone')),
              AuditLog.entity_type == 'employee', AuditLog.entity_id == employee.id)
             .order_by(AuditLog.id))
    for event in audits:
        is_creation = event.action == 'appointment'
        data = (event.new_values if is_creation else event.old_values) or {}
        row_id = data.get('work_experience_id')
        if row_id is None:
            match = by_date.get((data.get('effective_date' if is_creation else 'date_from'),
                                 data.get('appointment_type')), [])
            if len(match) != 1:
                # Old audits did not identify the row. In an overlapping history
                # neither destructive action nor attribution of a reason is safe.
                for candidate in match:
                    events.setdefault(candidate, None)
                continue
            row_id = match[0]
        if row_id not in by_id:
            continue
        if is_creation:
            events[row_id] = event
        else:
            events.pop(row_id, None)
    return events


def official_period(row, event):
    return bool(event or row.source_vacancy_id is not None or row.source_result_id is not None)


def undo_available(row, event, employee, latest_id, disposals):
    periods = employee.work_experience
    if event is None or (event.new_values or {}).get('work_experience_id') != row.id:
        return False
    old = event.old_values or {}
    if (employee.employment_status != "active" or employee.profile_status == "archived"
            or not {'closed_work_experience_id', 'position_id', 'org_unit_id'} <= old.keys()
            or row.date_to is not None or str(row.date_from) != event.new_values.get('effective_date')
            or latest_id != row.id or row.position_id != employee.current_position_id
            or row.org_unit_id != employee.current_org_unit_id):
        return False
    if any(d.date_to is None or d.date_to >= row.date_from for d in disposals):
        return False
    prior_disposal = old.get('closed_disposal_id')
    if prior_disposal is not None and not any(
            d.id == prior_disposal and d.date_to == row.date_from - timedelta(days=1) for d in disposals):
        return False
    closed_id = old['closed_work_experience_id']
    if closed_id is None:
        return True
    return any(period.id == closed_id and period.date_to == row.date_from - timedelta(days=1)
               and ("closed_work_post" not in old or work_post_snapshot(period) == old["closed_work_post"])
               for period in periods)


def career_metadata(db, employee, *, is_admin):
    periods = employee.work_experience
    if not periods:
        return {}
    events = appointment_events(db, employee)
    period_ids = [row.id for row in periods]
    protected_files = protected_period_ids(db, period_ids) if is_admin else set()
    latest = max((p for p in periods if p.is_internal), key=lambda p: (p.date_from, p.id), default=None)
    latest_id = latest.id if latest else None
    disposals = db.query(DisposalPeriod).filter_by(employee_id=employee.id).all() if is_admin else []
    vacancy_ids = {p.source_vacancy_id for p in periods if p.source_vacancy_id is not None}
    vacancy_titles = dict(db.query(Vacancy.id, Vacancy.title).filter(Vacancy.id.in_(vacancy_ids)).all()) if vacancy_ids else {}
    result_ids = {p.source_result_id for p in periods if p.source_result_id is not None}
    public_results = set()
    if result_ids and not is_admin:
        public_results = {id_ for (id_,) in db.query(MatchingResult.id).join(MatchingRun)
                          .filter(MatchingResult.id.in_(result_ids), MatchingRun.include_confidential.is_(False))}
    result = {}
    for row in periods:
        event = events.get(row.id)
        official = official_period(row, event)
        manual = not official and row.id not in events
        can_remove = is_admin and row.id not in protected_files
        visible_source = is_admin or row.source_result_id is None or row.source_result_id in public_results
        vacancy_id = row.source_vacancy_id if visible_source else None
        result[row.id] = {
            'is_appointment': official, 'appointment_type': row.appointment_type if official else None,
            'can_edit': is_admin and manual, 'can_delete': can_remove and manual,
            'can_undo': can_remove and undo_available(row, event, employee, latest_id, disposals),
            'source_vacancy': vacancy_titles.get(vacancy_id), 'source_vacancy_id': vacancy_id,
            'reason': event.reason if is_admin and event else None,
        }
    return result


def protected_period_ids(db, ids):
    files = db.query(Attachment.entity_id).filter(Attachment.entity_type == 'work_experience', Attachment.entity_id.in_(ids))
    values = db.query(CustomFieldValue.entity_id).filter(CustomFieldValue.entity_type == 'work_experience', CustomFieldValue.entity_id.in_(ids))
    return {row_id for (row_id,) in files.union(values)}
