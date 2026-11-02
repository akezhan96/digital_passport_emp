from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from auth import current_user
from database import get_db
from models import AuditLog, Employee, EmployeePersonnelRecord
from services.career import lock_employee
from services.personnel import disposal_statistics, personnel_summary, record_dict

router = APIRouter(prefix='/api/v1', tags=['personnel'])
CONFLICT = 'Запись изменилась. Обновите историю / Жазба өзгерді. Тарихты жаңартыңыз'


class PersonnelRecordIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['contract', 'rank', 'recognition']
    title: str = Field(default='', max_length=180)
    event_date: date
    end_date: date | None = None
    indefinite: StrictBool = False
    planned_date: date | None = None

    @model_validator(mode='after')
    def validate_event(self):
        if self.event_date > date.today():
            raise ValueError('Дата события ещё не наступила / Оқиға күні әлі келген жоқ')
        if '\x00' in self.title or (self.kind != 'contract' and not self.title):
            raise ValueError('Укажите название / Атауын көрсетіңіз')
        if self.kind != 'contract' and (self.end_date or self.indefinite):
            raise ValueError('Срок действия относится только к контракту / Қолданылу мерзімі тек келісімшартқа қатысты')
        if self.end_date and (self.indefinite or self.end_date < self.event_date):
            raise ValueError('Проверьте дату окончания контракта / Келісімшарттың аяқталу күнін тексеріңіз')
        if self.planned_date and (self.kind != 'rank' or self.planned_date < self.event_date):
            raise ValueError('Проверьте плановую дату звания / Атақтың жоспарланған күнін тексеріңіз')
        return self


class PersonnelRecordEdit(PersonnelRecordIn):
    expected_revision: int = Field(strict=True, ge=1)


class DisposalFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    org_unit_id: int | None = Field(default=None, gt=0)
    reveal_names: StrictBool = False
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


def _employee(db, employee_id, writing=False):
    employee = lock_employee(db, employee_id) if writing else db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(404, 'Сотрудник не найден / Қызметкер табылмады')
    if writing and employee.profile_status == 'archived':
        raise HTTPException(409, 'Профиль в архиве / Профиль мұрағатта')
    return employee


def _actor(request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Изменения доступны администратору / Өзгерістерді әкімші енгізеді')
    return user['sub']


def _editable_record(db, employee_id, record_id, expected_revision):
    _employee(db, employee_id, writing=True)
    row = (db.query(EmployeePersonnelRecord).filter_by(employee_id=employee_id, id=record_id)
           .with_for_update().populate_existing().one_or_none())
    if row is None:
        raise HTTPException(404, 'Запись не найдена / Жазба табылмады')
    if row.revision != expected_revision:
        raise HTTPException(409, CONFLICT)
    return row


def _audit_values(data):
    if data is None:
        return None
    data = dict(data)
    data['personnel_record_id'] = data.pop('id')
    data['personnel_kind'] = data.pop('kind')
    return data


def _save_record(db, row, actor, action, before=None):
    try:
        db.flush()
        after = None if action == 'delete' else record_dict(row)
        db.add(AuditLog(action='personnel_record_' + action, entity_type='employee', entity_id=row.employee_id, changed_by=actor,
                        old_values=_audit_values(before), new_values=_audit_values(after)))
        db.commit()
    except StaleDataError as error:
        db.rollback()
        raise HTTPException(409, CONFLICT) from error
    return after


def next_refresh_at(today):
    # Midnight in the configured personnel timezone, including its UTC offset on that date.
    midnight = datetime.combine(today + timedelta(days=1), time.min)
    return midnight.astimezone().isoformat()


@router.get('/employees/{employee_id}/personnel-summary')
def get_summary(employee_id: int, request: Request, as_of: date | None = None, db: Session = Depends(get_db)):
    current_user(request)
    today = date.today()
    if as_of and as_of > today:
        raise HTTPException(422, 'Выберите прошедшую дату или сегодня / Өткен күнді немесе бүгінгі күнді таңдаңыз')
    result = personnel_summary(db, _employee(db, employee_id), as_of or today)
    result['next_refresh_at'] = next_refresh_at(today)
    return result


@router.get('/employees/{employee_id}/personnel-records')
def list_records(employee_id: int, request: Request, db: Session = Depends(get_db)):
    current_user(request)
    _employee(db, employee_id)
    rows = (db.query(EmployeePersonnelRecord).filter_by(employee_id=employee_id)
            .order_by(EmployeePersonnelRecord.event_date.desc(), EmployeePersonnelRecord.id.desc()))
    return {'items': [record_dict(row) for row in rows]}


@router.post('/employees/{employee_id}/personnel-records', status_code=201)
def create_record(employee_id: int, payload: PersonnelRecordIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request)
    _employee(db, employee_id, writing=True)
    row = EmployeePersonnelRecord(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    return _save_record(db, row, actor, 'create')


@router.put('/employees/{employee_id}/personnel-records/{record_id}')
def update_record(employee_id: int, record_id: int, payload: PersonnelRecordEdit, request: Request,
                  db: Session = Depends(get_db)):
    actor = _actor(request)
    row = _editable_record(db, employee_id, record_id, payload.expected_revision)
    if row.kind != payload.kind:
        raise HTTPException(422, 'Вид записи изменить нельзя / Жазбаның түрін өзгертуге болмайды')
    before = record_dict(row)
    for key, value in payload.model_dump(exclude={'expected_revision'}).items():
        setattr(row, key, value)
    if not db.is_modified(row):
        return before
    return _save_record(db, row, actor, 'update', before)


@router.delete('/employees/{employee_id}/personnel-records/{record_id}', status_code=204)
def delete_record(employee_id: int, record_id: int, request: Request, expected_revision: int = Query(..., ge=1),
                  db: Session = Depends(get_db)):
    actor = _actor(request)
    row = _editable_record(db, employee_id, record_id, expected_revision)
    before = record_dict(row)
    db.delete(row)
    _save_record(db, row, actor, 'delete', before)
    return Response(status_code=204)


@router.post('/analytics/disposal-statistics')
def count_disposals(payload: DisposalFilters, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    today = date.today()
    result = disposal_statistics(db, today, payload)
    result['next_refresh_at'] = next_refresh_at(today)
    if payload.reveal_names and result['items']:
        db.add(AuditLog(action='reveal_identities', entity_type='analytics_query', changed_by=user['sub'],
                        new_values={'query': 'disposal_statistics', 'org_unit_id': payload.org_unit_id,
                                    'employee_ids': [item['employee_id'] for item in result['items']]}))
        db.commit()
    return result
