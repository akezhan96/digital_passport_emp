"""Date-based personnel indicators derived when a dossier or report is opened."""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import Date, Integer, cast, func, literal, or_, select

from models import DisposalPeriod, Employee, EmployeePersonnelRecord, OrgUnit
from services.career import appointment_events, official_period
from services.metrics import employee_tenure_days


def record_dict(row):
    return {'id': row.id, 'kind': row.kind, 'title': row.title,
            'event_date': row.event_date.isoformat(), 'end_date': row.end_date.isoformat() if row.end_date else None,
            'indefinite': row.indefinite, 'planned_date': row.planned_date.isoformat() if row.planned_date else None,
            'revision': row.revision}


def current_assignment(db, employee, day):
    candidates = [row for row in employee.work_experience if row.is_internal and row.date_from <= day
                  and (row.date_to is None or row.date_to >= day)]
    if not candidates:
        return None
    # Current profile pointers disambiguate present records, not positions held in the past.
    if day == date.today() and (employee.current_position_id or employee.current_org_unit_id):
        candidates = [row for row in candidates if
                      (not employee.current_position_id or row.position_id == employee.current_position_id) and
                      (not employee.current_org_unit_id or row.org_unit_id == employee.current_org_unit_id)]
    if len(candidates) != 1:
        return None
    row = candidates[0]
    event = appointment_events(db, employee).get(row.id)
    return {'since': row.date_from.isoformat(), 'duration_days': (day-row.date_from).days + 1,
            'basis': 'appointment' if official_period(row, event) else 'work_period'}


def personnel_summary(db, employee, day):
    row_type = EmployeePersonnelRecord
    # Three bounded index lookups, even if one type has decades of events.
    latest_ids = [select(row_type.id).where(row_type.employee_id == employee.id, row_type.kind == kind,
                  row_type.event_date <= day).order_by(row_type.event_date.desc(), row_type.id.desc())
                  .limit(1).correlate(None).scalar_subquery() for kind in ('contract', 'rank', 'recognition')]
    latest = {row.kind: row for row in db.scalars(select(row_type).where(row_type.id.in_(latest_ids)))}
    tenure = employee_tenure_days(db, employee, day)
    period = (db.query(DisposalPeriod).filter(DisposalPeriod.employee_id == employee.id, DisposalPeriod.date_from <= day,
              or_(DisposalPeriod.date_to.is_(None), DisposalPeriod.date_to >= day))
              .order_by(DisposalPeriod.date_from.desc(), DisposalPeriod.id.desc()).first())
    working = day != date.today() or (employee.employment_status == 'active' and employee.profile_status != 'archived')
    disposal = ({'since': period.date_from.isoformat(), 'duration_days': (day-period.date_from).days + 1,
                 'org_unit_id': period.org_unit_id} if period and working else None)
    contract = latest.get('contract')
    if contract:
        remaining = (contract.end_date-day).days if contract.end_date else None
        status = ('indefinite' if contract.indefinite else 'unknown' if remaining is None else
                  'valid' if remaining > 0 else 'expired' if remaining < 0 else 'expires_today')
        contract = {**record_dict(contract), 'remaining_days': remaining, 'status': status}
    rank = latest.get('rank')
    if rank:
        rank = {**record_dict(rank), 'elapsed_days': (day-rank.event_date).days,
                'until_planned_days': (rank.planned_date-day).days if rank.planned_date else None}
    recognition = latest.get('recognition')
    if recognition:
        recognition = {**record_dict(recognition), 'elapsed_days': (day-recognition.event_date).days}
    return {'as_of': day.isoformat(), 'tenure': tenure, 'disposal': disposal,
            'appointment': current_assignment(db, employee, day) if working and not disposal else None,
            'contract': contract, 'rank': rank, 'recognition': recognition}


def disposal_statistics(db, day, query):
    if query.org_unit_id is not None and not db.get(OrgUnit, query.org_unit_id):
        raise HTTPException(404, 'Подразделение не найдено / Бөлімше табылмады')
    # Count people, even if an imported database contains overlapping records.
    periods = (select(DisposalPeriod.employee_id, DisposalPeriod.org_unit_id, DisposalPeriod.date_from,
               func.row_number().over(partition_by=DisposalPeriod.employee_id,
                   order_by=(DisposalPeriod.date_from.desc(), DisposalPeriod.id.desc())).label('rn'))
               .join(Employee, Employee.id == DisposalPeriod.employee_id)
               .where(Employee.employment_status == 'active', Employee.profile_status != 'archived',
                      DisposalPeriod.date_from <= day,
                      or_(DisposalPeriod.date_to.is_(None), DisposalPeriod.date_to >= day)).cte('disposal_periods_today'))
    scope = select(periods).where(periods.c.rn == 1).cte('disposal_people')
    unit_rows = (db.execute(select(scope.c.org_unit_id, OrgUnit.name_ru, OrgUnit.name_kk, func.count().label('population'))
                 .select_from(scope).outerjoin(OrgUnit, OrgUnit.id == scope.c.org_unit_id)
                 .group_by(scope.c.org_unit_id, OrgUnit.name_ru, OrgUnit.name_kk)
                 .order_by(OrgUnit.name_ru, scope.c.org_unit_id)).all())
    unit_info = {r.org_unit_id: {'id': r.org_unit_id, 'name_ru': r.name_ru, 'name_kk': r.name_kk}
                 if r.org_unit_id is not None else None for r in unit_rows}
    units = [{'org_unit': unit_info[r.org_unit_id], 'count': r.population} for r in unit_rows]
    if query.org_unit_id is not None:
        scope = select(scope).where(scope.c.org_unit_id == query.org_unit_id).cte('selected_disposal_people')
    since = scope.c.date_from
    duration = (cast(func.julianday(day)-func.julianday(since), Integer) + 1 if db.get_bind().dialect.name == 'sqlite'
                else cast(literal(day, Date) - since, Integer) + 1)
    total, average, maximum = db.execute(select(func.count(), func.avg(duration), func.max(duration)).select_from(scope)).one()
    cols = [scope.c.employee_id, scope.c.org_unit_id, since, Employee.anonymous_code]
    if query.reveal_names:
        cols.extend((Employee.last_name, Employee.first_name, Employee.middle_name))
    rows = db.execute(select(*cols).select_from(scope).join(Employee, Employee.id == scope.c.employee_id)
                      .order_by(since, scope.c.employee_id).limit(query.limit).offset(query.offset)).all()
    items = []
    for row in rows:
        display_name = row.anonymous_code or f'#{row.employee_id}'
        if query.reveal_names:
            display_name = ' '.join(part for part in (row.last_name, row.first_name, row.middle_name) if part)
        items.append({'employee_id': row.employee_id, 'display_name': display_name,
                      'org_unit': unit_info.get(row.org_unit_id), 'since': row.date_from.isoformat(),
                      'duration_days': (day-row.date_from).days + 1})
    return {'as_of': day.isoformat(), 'total': total, 'company_total': sum(r.population for r in unit_rows),
            'average_days': round(float(average), 1) if average is not None else None, 'max_days': maximum,
            'units': units, 'items': items, 'names_revealed': query.reveal_names}
