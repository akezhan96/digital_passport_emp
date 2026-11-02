"""Vacancy follow-up derived from human decisions and recorded appointments."""
from datetime import date
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, load_only
from models import Decision, Employee, MatchingResult, MatchingRun, WorkExperience


def latest_decision(db, employee_id, vacancy_id):
    return (db.query(Decision).join(MatchingResult).join(MatchingRun)
            .filter(MatchingResult.employee_id == employee_id, MatchingRun.vacancy_id == vacancy_id)
            .order_by(Decision.decided_at.desc(), Decision.id.desc()).populate_existing().first())


def latest_appointment(db, employee_id, vacancy_id, *, public_only=False):
    query = (db.query(WorkExperience).options(joinedload(WorkExperience.position), joinedload(WorkExperience.org_unit))
             .filter(WorkExperience.employee_id == employee_id, WorkExperience.source_vacancy_id == vacancy_id))
    if public_only:
        query = (query.outerjoin(MatchingResult, MatchingResult.id == WorkExperience.source_result_id)
                 .outerjoin(MatchingRun, MatchingRun.id == MatchingResult.run_id)
                 .filter(or_(WorkExperience.source_result_id.is_(None), MatchingRun.include_confidential.is_(False))))
    return query.order_by(WorkExperience.date_from.desc(), WorkExperience.id.desc()).first()


def appointment_dict(row):
    if row is None:
        return None
    return {'id': row.id, 'effective_date': row.date_from.isoformat(),
            'date_to': row.date_to.isoformat() if row.date_to else None,
            'position_id': row.position_id,
            'position_ru': row.position.name_ru if row.position else row.external_position_title,
            'position_kk': row.position.name_kk if row.position else row.external_position_title,
            'org_unit_id': row.org_unit_id,
            'org_unit_ru': row.org_unit.name_ru if row.org_unit else row.external_employer,
            'org_unit_kk': row.org_unit.name_kk if row.org_unit else row.external_employer,
            'is_current': row.date_from <= date.today() and (row.date_to is None or row.date_to >= date.today())}


def decision_dict(row):
    if row is None:
        return None
    return {'decision': row.decision, 'final_rank': row.final_rank,
            'reason': row.reason, 'decided_by': row.decided_by,
            'decided_at': row.decided_at.isoformat() if row.decided_at else None}


def appointment_state(db, result, *, is_admin):
    vacancy = result.run.vacancy
    appointment = latest_appointment(db, result.employee_id, vacancy.id, public_only=not is_admin)
    current = latest_decision(db, result.employee_id, vacancy.id)
    if not is_admin:
        reason = 'forbidden'
    elif appointment:
        reason = 'already_appointed'
    elif vacancy.status == 'closed':
        reason = 'vacancy_closed'
    elif not result.employee or result.employee.employment_status != 'active':
        reason = 'employee_inactive'
    elif not current or current.decision != 'selected':
        reason = 'not_selected'
    elif current.result_id != result.id:
        reason = 'selection_superseded'
    elif result.run.requirements_version != vacancy.requirements_version:
        reason = 'vacancy_changed'
    else:
        reason = None
    return {'can_appoint': reason is None, 'reason_code': reason}, appointment_dict(appointment)


def vacancy_recruitment(db, vacancy, *, is_admin, reveal_names=False, status=None, offset=0, limit=20):
    # Resolve the last human decision across all calculations first. A private
    # replacement must not resurrect an obsolete public decision for a viewer.
    ranked = (db.query(Decision.id.label('decision_id'), func.row_number().over(
        partition_by=MatchingResult.employee_id,
        order_by=(Decision.decided_at.desc(), Decision.id.desc())).label('ordinal'))
        .join(MatchingResult).join(MatchingRun).filter(MatchingRun.vacancy_id == vacancy.id).subquery())
    query = (db.query(Decision, MatchingResult.id, MatchingResult.employee_id, MatchingResult.run_id,
                     MatchingResult.score, MatchingResult.explanation['methodology_summary'].label('summary'),
                     MatchingResult.readiness_code, MatchingResult.is_qualified)
             .select_from(Decision).join(ranked, Decision.id == ranked.c.decision_id).join(MatchingResult).join(MatchingRun)
             .filter(ranked.c.ordinal == 1))
    if not is_admin:
        query = query.filter(MatchingRun.include_confidential.is_(False))
    records = {}
    for decision, result_id, employee_id, run_id, score, summary, readiness, qualified in query.all():
        records[employee_id] = {'result_id': result_id, 'run_id': run_id, 'employee_id': employee_id,
            'score': float(score), 'methodology_summary': summary, 'readiness_code': readiness, 'is_qualified': qualified,
            'decision': decision_dict(decision), 'appointment': None,
            'status_code': decision.decision, '_changed_at': decision.decided_at.isoformat()}

    appointments = (db.query(WorkExperience, MatchingResult.run_id, MatchingResult.score,
        MatchingResult.explanation['methodology_summary'].label('summary'), MatchingResult.readiness_code,
        MatchingResult.is_qualified).options(joinedload(WorkExperience.position), joinedload(WorkExperience.org_unit))
        .outerjoin(MatchingResult, MatchingResult.id == WorkExperience.source_result_id)
        .outerjoin(MatchingRun, MatchingRun.id == MatchingResult.run_id)
        .filter(WorkExperience.source_vacancy_id == vacancy.id))
    if not is_admin:
        appointments = appointments.filter(or_(WorkExperience.source_result_id.is_(None),
                                               MatchingRun.include_confidential.is_(False)))
    seen = set()
    for appointment, source_run_id, source_score, source_summary, readiness, qualified in appointments.order_by(WorkExperience.date_from.desc(), WorkExperience.id.desc()).all():
        if appointment.employee_id in seen:
            continue
        seen.add(appointment.employee_id)
        item = records.setdefault(appointment.employee_id, {'result_id': appointment.source_result_id,
            'run_id': source_run_id, 'employee_id': appointment.employee_id,
            'score': float(source_score) if source_score is not None else None, 'methodology_summary': source_summary,
            'readiness_code': readiness, 'is_qualified': qualified,
            'decision': None, '_changed_at': appointment.date_from.isoformat()})
        item['appointment'] = appointment_dict(appointment)
        item['status_code'] = 'appointed'

    visible_runs = db.query(MatchingRun).filter(MatchingRun.vacancy_id == vacancy.id)
    if not is_admin:
        visible_runs = visible_runs.filter(MatchingRun.include_confidential.is_(False))
    counts = {key: sum(item['status_code'] == key for item in records.values())
              for key in ('selected', 'on_hold', 'reserve', 'rejected', 'appointed')}
    counts['runs'] = visible_runs.with_entities(MatchingRun.id).count()
    last = (visible_runs.options(load_only(MatchingRun.id, MatchingRun.created_at, MatchingRun.status,
        MatchingRun.total_evaluated, MatchingRun.total_qualified, MatchingRun.candidate_methodology_id))
        .order_by(MatchingRun.created_at.desc(), MatchingRun.id.desc()).first())
    latest = None if last is None else {'id': last.id, 'vacancy_id': vacancy.id,
        'vacancy_title': vacancy.title, 'vacancy_title_kk': vacancy.title_kk, 'status': last.status,
        'created_at': last.created_at.isoformat(), 'total_evaluated': last.total_evaluated,
        'total_qualified': last.total_qualified, 'candidate_methodology_id': last.candidate_methodology_id}
    priority = {'selected': 0, 'on_hold': 1, 'reserve': 2, 'appointed': 3, 'rejected': 4}
    items = [item for item in records.values() if status is None or item['status_code'] == status]
    items.sort(key=lambda item: (item['_changed_at'], item['employee_id']), reverse=True)
    items.sort(key=lambda item: priority[item['status_code']])
    total = len(items)
    page = items[offset:offset + limit]
    employees = {e.id: e for e in db.query(Employee).options(load_only(Employee.id, Employee.anonymous_code,
        Employee.first_name, Employee.last_name, Employee.middle_name))
        .filter(Employee.id.in_([r['employee_id'] for r in page])).all()} if page else {}
    for item in page:
        employee = employees.get(item['employee_id'])
        item['anonymous_code'] = employee.anonymous_code if employee else None
        item['display_name'] = (employee.full_name if employee and reveal_names
                                else employee.anonymous_code if employee else '—')
        item.pop('_changed_at', None)
    return {'vacancy_id': vacancy.id, 'vacancy_status': vacancy.status, 'org_unit_id': vacancy.org_unit_id,
            'names_revealed': reveal_names, 'counts': counts, 'latest_run': latest,
            'candidates': page, 'total': total, 'offset': offset, 'limit': limit}
