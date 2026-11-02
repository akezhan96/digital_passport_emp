"""Custom dossier tabs and the records entered for one employee."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import and_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from auth import current_user
from database import get_db
from models import AuditLog, DossierSubsection, DossierSubsectionEntry, DossierTabField, DossierTabValue, Employee
from services import candidate_sources

router = APIRouter(prefix='/api/v1', tags=['dossier-subsections'])
Tab = Literal['general', 'education', 'languages', 'training', 'career', 'candidate',
              'competencies', 'metrics', 'documents', 'history', 'custom']
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120, pattern=r'^[^\x00]*$')]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200, pattern=r'^[^\x00]*$')]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000, pattern=r'^[^\x00]*$')]
Visibility = Literal['public', 'admin']
Revision = Annotated[int, Field(gt=0, strict=True)]
CONFLICT = 'Запись уже изменилась. Обновите данные и повторите действие. / Жазба өзгерді. Деректерді жаңартып, әрекетті қайталаңыз.'
DUPLICATE = 'Название уже используется. Проверьте также архив. / Бұл атау қолданылуда. Мұрағатты да тексеріңіз.'
FieldType = Literal['text', 'date', 'number', 'boolean']
ValueMap = dict[Annotated[int, Field(gt=0, le=2147483647)], Any]
BUILTIN_NAMES = {
    'name_ru': ('Общее', 'Образование', 'Языки', 'Обучение', 'Карьера', 'Оценка кандидата', 'Компетенции',
                'Расчётные показатели', 'Документы', 'История'),
    'name_kk': ('Жалпы', 'Білімі', 'Тілдер', 'Оқыту', 'Мансап', 'Кандидатты бағалау', 'Құзыреттіліктер',
                'Есептік көрсеткіштер', 'Құжаттар', 'Тарихы'),
}


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SectionCreate(Payload):
    tab: Tab = 'custom'
    visibility: Visibility = 'public'
    name_ru: Name
    name_kk: Name


class SectionPatch(Payload):
    expected_revision: Revision
    visibility: Visibility | None = None
    name_ru: Name | None = None
    name_kk: Name | None = None
    is_active: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode='after')
    def check_changes(self):
        fields = self.model_fields_set - {'expected_revision'}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError('Укажите новое значение поля / Өрістің жаңа мәнін көрсетіңіз')
        return self


class FieldCreate(Payload):
    name_ru: Name
    name_kk: Name
    field_type: FieldType


class FieldPatch(Payload):
    expected_revision: Revision
    name_ru: Name | None = None
    name_kk: Name | None = None
    field_type: FieldType | None = None
    is_active: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode='after')
    def check_changes(self):
        fields = self.model_fields_set - {'expected_revision'}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError('Укажите новое значение поля / Өрістің жаңа мәнін көрсетіңіз')
        return self


class EntryPayload(Payload):
    title: Title = ''
    description: Description = ''
    values: ValueMap = Field(default_factory=dict)


class EntryCreate(EntryPayload):
    @model_validator(mode='after')
    def require_content(self):
        if not self.title and not self.values:
            raise ValueError('Укажите название записи или заполните поле / Жазба атауын көрсетіңіз немесе өрісті толтырыңыз')
        return self


class EntryEdit(EntryPayload):
    expected_revision: Revision


def _admin(request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Недостаточно прав / Құқықтар жеткіліксіз')
    return user['sub']


def _section_data(row):
    return dict(id=row.id, tab=row.tab, name_ru=row.name_ru, name_kk=row.name_kk,
                is_active=row.is_active, visibility=row.visibility, revision=row.revision)


def _field_data(row):
    return dict(id=row.id, subsection_id=row.subsection_id, name_ru=row.name_ru, name_kk=row.name_kk,
                field_type=row.field_type, is_active=row.is_active, revision=row.revision)


def _entry_data(row, values=None):
    return dict(id=row.id, title=row.title, description=row.description, revision=row.revision,
                values=values or {})


def _audit(db, actor, action, entity_type, entity_id, old=None, new=None):
    db.add(AuditLog(action=action, entity_type=entity_type, entity_id=entity_id,
                    old_values=old, new_values=new, changed_by=actor))


def _verify_revision(row, expected):
    if row.revision != expected:
        raise HTTPException(409, CONFLICT)


def _flush(db, *, definition=False):
    try:
        db.flush()
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(409, CONFLICT) from exc
    except IntegrityError as exc:
        db.rollback()
        if definition:
            raise HTTPException(409, DUPLICATE) from exc
        raise


def _employee(db, employee_id, *, writing=False):
    query = db.query(Employee.id, Employee.profile_status).filter(Employee.id == employee_id)
    if writing:
        # Keep archival/deletion from racing a write to a person's record.
        query = query.with_for_update(read=True)
    person = query.first()
    if person is None:
        raise HTTPException(404, 'Сотрудник не найден / Қызметкер табылмады')
    if writing and person.profile_status == 'archived':
        raise HTTPException(409, 'Сначала восстановите профиль из архива / Алдымен профильді мұрағаттан қалпына келтіріңіз')


def _section(db, section_id, *, writing_entries=False):
    # Multiple employees can edit their own entries concurrently; archiving the
    # shared definition waits until an in-flight entry write commits.
    row = (db.query(DossierSubsection).filter_by(id=section_id).populate_existing()
           .with_for_update(read=writing_entries).first())
    if row is None:
        raise HTTPException(404, 'Подраздел не найден / Ішкі бөлім табылмады')
    if writing_entries and not row.is_active:
        raise HTTPException(409, 'Сначала восстановите подраздел из архива / Алдымен ішкі бөлімді мұрағаттан қалпына келтіріңіз')
    return row


def _lock_tab_names(db):
    # Old templates can have equal names under different native tabs. Serialize
    # name changes without rewriting them into a new global uniqueness index.
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(42091, 1)'))


def _check_names(rows, changes, *, builtin=False, before=None):
    for key in ('name_ru', 'name_kk'):
        if key not in changes or before is not None and changes[key] == getattr(before, key):
            continue
        name = changes[key].casefold()
        if builtin and name in (label.casefold() for label in BUILTIN_NAMES[key]):
            raise HTTPException(409, DUPLICATE)
        if any(getattr(row, key).casefold() == name and (not before or row.id != before.id) for row in rows):
            raise HTTPException(409, DUPLICATE)


@router.get('/dossier-subsections')
def tab_list(request: Request, include_archived: bool = False, db: Session = Depends(get_db)):
    admin = current_user(request)['role'] == 'admin'
    if include_archived and not admin:
        raise HTTPException(403, 'Недостаточно прав / Құқықтар жеткіліксіз')
    rows = db.query(DossierSubsection)
    if not include_archived:
        rows = rows.filter(DossierSubsection.is_active.is_(True))
    if not admin:
        rows = rows.filter(DossierSubsection.visibility == 'public', DossierSubsection.tab != 'history')
    return {'data': [_section_data(row) for row in rows.order_by(DossierSubsection.id)]}


def _records(db, employee_id, sections, *, include_archived=False):
    if not sections:
        return {}
    eligible = (db.query(DossierTabValue.entry_id, DossierTabValue.field_id, DossierTabValue.value,
                         DossierTabField.subsection_id)
                .join(DossierTabField, DossierTabField.id == DossierTabValue.field_id)
                .filter(DossierTabField.subsection_id.in_(sections)))
    if not include_archived:
        eligible = eligible.filter(DossierTabField.is_active.is_(True))
    values = eligible.subquery()
    entry = DossierSubsectionEntry
    # Fetch each entry's revision and values in the same statement. A client
    # must not save old values using a revision from a newer concurrent write.
    rows = (db.query(entry, values.c.field_id, values.c.value)
            .outerjoin(values, and_(entry.id == values.c.entry_id, entry.subsection_id == values.c.subsection_id))
            .filter(entry.employee_id == employee_id, entry.subsection_id.in_(sections))
            .order_by(entry.id, values.c.field_id))
    result = {}
    last_id = None
    for record, field_id, value in rows:
        if record.id != last_id:
            item = _entry_data(record)
            result.setdefault(record.subsection_id, []).append(item)
            last_id = record.id
        if field_id is not None:
            item['values'][str(field_id)] = value
    return result


@router.get('/employees/{employee_id}/dossier-subsections/{section_id}')
def tab_detail(employee_id: int, section_id: int, request: Request, include_archived_fields: bool = False,
               db: Session = Depends(get_db)):
    admin = current_user(request)['role'] == 'admin'
    if include_archived_fields and not admin:
        raise HTTPException(403, 'Недостаточно прав / Құқықтар жеткіліксіз')
    _employee(db, employee_id)
    query = db.query(DossierSubsection).filter(DossierSubsection.id == section_id)
    if not admin:
        query = query.filter(DossierSubsection.is_active.is_(True), DossierSubsection.visibility == 'public',
                             DossierSubsection.tab != 'history')
    # Hold a shared lock while reading fields and values so reclassification or
    # archiving cannot expose records from a different visibility snapshot.
    row = query.with_for_update(read=True).first()
    if not row:
        raise HTTPException(404, 'Вкладка не найдена / Қойынды табылмады')
    fields = db.query(DossierTabField).filter_by(subsection_id=section_id)
    if not include_archived_fields:
        fields = fields.filter(DossierTabField.is_active.is_(True))
    return {**_section_data(row), 'fields': [_field_data(field) for field in fields.order_by(DossierTabField.id)],
            'entries': _records(db, employee_id, [section_id], include_archived=include_archived_fields).get(section_id, [])}


@router.get('/employees/{employee_id}/dossier-subsections')
def list_sections(employee_id: int, tab: Tab, request: Request, include_archived: bool = False,
                  db: Session = Depends(get_db)):
    user = current_user(request)
    if user['role'] != 'admin' and (tab == 'history' or include_archived):
        raise HTTPException(403, 'Недостаточно прав / Құқықтар жеткіліксіз')
    _employee(db, employee_id)
    section = DossierSubsection
    rows = db.query(section).filter(section.tab == tab)
    if user['role'] != 'admin':
        rows = rows.filter(section.visibility == 'public')
    if not include_archived:
        rows = rows.filter(section.is_active.is_(True))
    definitions = rows.order_by(section.id).with_for_update(read=True).all()
    records = _records(db, employee_id, [row.id for row in definitions])
    return {'data': [{**_section_data(row), 'entries': records.get(row.id, [])} for row in definitions]}


@router.post('/dossier-subsections', status_code=201)
def create_section(body: SectionCreate, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    values = body.model_dump()
    if body.tab == 'history':
        values['visibility'] = 'admin'
    _lock_tab_names(db)
    _check_names(db.query(DossierSubsection.id, DossierSubsection.name_ru, DossierSubsection.name_kk).all(),
                 values, builtin=True)
    row = DossierSubsection(**values)
    db.add(row)
    _flush(db, definition=True)
    data = _section_data(row)
    _audit(db, actor, 'create', 'dossier_subsection', row.id, new=data)
    db.commit()
    return data


@router.patch('/dossier-subsections/{section_id}')
def edit_section(section_id: int, body: SectionPatch, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    changes = body.model_dump(exclude_unset=True, exclude={'expected_revision'})
    renaming = 'name_ru' in changes or 'name_kk' in changes
    if renaming:
        _lock_tab_names(db)
    row = _section(db, section_id)
    _verify_revision(row, body.expected_revision)
    before = _section_data(row)
    if renaming:
        _check_names(db.query(DossierSubsection.id, DossierSubsection.name_ru, DossierSubsection.name_kk).all(),
                     changes, builtin=True, before=row)
    if row.tab == 'history' and changes.get('visibility') == 'public':
        raise HTTPException(422, 'Историю видит только администратор / Тарихты тек әкімші көре алады')
    candidate_sources.guard_tab_change(db, row, changes)
    for key, value in changes.items():
        setattr(row, key, value)
    _flush(db, definition=True)
    data = _section_data(row)
    if data != before:
        action = 'update'
        if row.is_active != before['is_active']:
            action = 'restore' if row.is_active else 'archive'
        _audit(db, actor, action, 'dossier_subsection', row.id, before, data)
    db.commit()
    return data


FIELDS = '/dossier-subsections/{section_id}/fields'
ENTRIES = '/employees/{employee_id}/dossier-subsections/{section_id}/entries'


def _editable_schema(db, section_id):
    section = _section(db, section_id)
    if not section.is_active:
        raise HTTPException(409, 'Сначала восстановите вкладку / Алдымен қойындыны қалпына келтіріңіз')


@router.post(FIELDS, status_code=201)
def create_field(section_id: int, body: FieldCreate, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    _editable_schema(db, section_id)
    values = body.model_dump()
    _check_names(db.query(DossierTabField).filter_by(subsection_id=section_id).all(), values)
    field = DossierTabField(subsection_id=section_id, **values)
    db.add(field)
    _flush(db, definition=True)
    data = _field_data(field)
    _audit(db, actor, 'create', 'dossier_tab_field', field.id, new=data)
    db.commit()
    return data


@router.patch(FIELDS + '/{field_id}')
def edit_field(section_id: int, field_id: int, body: FieldPatch, request: Request, db: Session = Depends(get_db)):
    actor = _admin(request)
    _editable_schema(db, section_id)
    field = (db.query(DossierTabField).filter_by(id=field_id, subsection_id=section_id)
             .populate_existing().with_for_update().first())
    if not field:
        raise HTTPException(404, 'Поле не найдено / Өріс табылмады')
    _verify_revision(field, body.expected_revision)
    changes = body.model_dump(exclude_unset=True, exclude={'expected_revision'})
    if 'name_ru' in changes or 'name_kk' in changes:
        _check_names(db.query(DossierTabField).filter_by(subsection_id=section_id).all(), changes, before=field)
    if changes.get('field_type', field.field_type) != field.field_type:
        if db.query(DossierTabValue.id).filter_by(field_id=field_id).first():
            raise HTTPException(409, 'У поля уже есть значения. Для другого типа создайте новое поле / '
                                'Өрісте мәндер бар. Басқа түр үшін жаңа өріс жасаңыз')
    candidate_sources.guard_tab_field_change(db, field, changes)
    before = _field_data(field)
    for key, value in changes.items():
        setattr(field, key, value)
    _flush(db, definition=True)
    data = _field_data(field)
    if data != before:
        action = ('restore' if field.is_active else 'archive') if before['is_active'] != field.is_active else 'update'
        _audit(db, actor, action, 'dossier_tab_field', field.id, before, data)
    db.commit()
    return data


def _entry_context(request, db, employee_id, section_id):
    actor = _admin(request)
    _employee(db, employee_id, writing=True)
    _section(db, section_id, writing_entries=True)
    return actor


def _entry(db, employee_id, section_id, entry_id, expected):
    row = (db.query(DossierSubsectionEntry).filter_by(id=entry_id, employee_id=employee_id, subsection_id=section_id)
           .populate_existing().with_for_update().first())
    if row is None:
        raise HTTPException(404, 'Запись не найдена / Жазба табылмады')
    _verify_revision(row, expected)
    return row


def _entry_snapshot(row, fields=None, values=None):
    # Attach changes to the employee history even after a record is removed.
    return {'subsection_id': row.subsection_id, 'entry_id': row.id, 'title': row.title,
            'description': row.description, 'revision': row.revision, **{
                f'{fields[field_id].name_ru} (#{field_id})': value for field_id, value in (values or {}).items()}}


def _typed_value(field, raw):
    if raw is None:
        return None
    if field.field_type == 'text' and isinstance(raw, str) and '\x00' not in raw and len(raw) <= 4000:
        return raw.strip() or None
    if field.field_type == 'boolean' and type(raw) is bool:
        return raw
    if field.field_type == 'date' and isinstance(raw, str):
        try:
            if date.fromisoformat(raw).isoformat() == raw:
                return raw
        except ValueError:
            pass
    if field.field_type == 'number' and type(raw) in (int, float):
        number = Decimal(str(raw))
        if number.is_finite() and abs(number) < 10**12 and number == number.quantize(Decimal('.0001')):
            return raw
    raise HTTPException(422, f'Недопустимое значение поля «{field.name_ru}» / «{field.name_kk}» өрісінің мәні жарамсыз')


def _record_values(db, row, requested):
    """Validate the entire change before touching the entry or its values."""
    fields = {f.id: f for f in db.query(DossierTabField).filter_by(subsection_id=row.subsection_id)}
    stored = ({v.field_id: v for v in db.query(DossierTabValue).filter_by(entry_id=row.id)} if row.id else {})
    old = {identity: value.value for identity, value in stored.items()}
    new = dict(old)
    for identity, raw in requested.items():
        field = fields.get(identity)
        if not field or not field.is_active:
            raise HTTPException(409, 'Поле архивировано или не относится к вкладке / Өріс мұрағатталған немесе басқа қойындыға жатады')
        value = _typed_value(field, raw)
        if value is None:
            new.pop(identity, None)
        else:
            new[identity] = value
    return fields, stored, old, new


def _require_content(title, fields, values):
    if not title and not any(fields[identity].is_active for identity in values):
        raise HTTPException(422, 'Укажите название записи или заполните поле / Жазба атауын көрсетіңіз немесе өрісті толтырыңыз')


def _write_values(db, row, stored, old, new):
    for identity in old.keys() - new.keys():
        db.delete(stored[identity])
    for identity, value in new.items():
        if identity not in old:
            db.add(DossierTabValue(entry_id=row.id, field_id=identity, value=value))
        elif old[identity] != value:
            stored[identity].value = value


def _visible_values(fields, values):
    return {str(identity): value for identity, value in values.items() if fields[identity].is_active}


@router.post(ENTRIES, status_code=201)
def create_entry(employee_id: int, section_id: int, body: EntryCreate,
                 request: Request, db: Session = Depends(get_db)):
    actor = _entry_context(request, db, employee_id, section_id)
    row = DossierSubsectionEntry(employee_id=employee_id, subsection_id=section_id, title=body.title, description=body.description)
    fields, stored, old, values = _record_values(db, row, body.values)
    _require_content(row.title, fields, values)
    db.add(row)
    _flush(db)
    _write_values(db, row, stored, old, values)
    data = _entry_data(row, _visible_values(fields, values))
    _audit(db, actor, 'create', 'employee', employee_id, new=_entry_snapshot(row, fields, values))
    db.commit()
    return data


@router.patch(ENTRIES + '/{entry_id}')
def edit_entry(employee_id: int, section_id: int, entry_id: int, body: EntryEdit,
               request: Request, db: Session = Depends(get_db)):
    actor = _entry_context(request, db, employee_id, section_id)
    row = _entry(db, employee_id, section_id, entry_id, body.expected_revision)
    fields, stored, old, values = _record_values(db, row, body.values)
    title = body.title if 'title' in body.model_fields_set else row.title
    _require_content(title, fields, values)
    before = _entry_snapshot(row, fields, old)
    row.title = title
    if 'description' in body.model_fields_set:
        row.description = body.description
    if old != values:
        _write_values(db, row, stored, old, values)
        row.updated_at = datetime.utcnow()  # A value-only edit must advance the entry revision.
    _flush(db)
    data = _entry_data(row, _visible_values(fields, values))
    after = _entry_snapshot(row, fields, values)
    if after != before:
        _audit(db, actor, 'update', 'employee', employee_id, before, after)
    db.commit()
    return data


@router.delete(ENTRIES + '/{entry_id}', status_code=204)
def delete_entry(employee_id: int, section_id: int, entry_id: int, request: Request,
                 expected_revision: Annotated[int, Query(gt=0)], db: Session = Depends(get_db)):
    actor = _entry_context(request, db, employee_id, section_id)
    row = _entry(db, employee_id, section_id, entry_id, expected_revision)
    fields, _, old, _ = _record_values(db, row, {})
    before = _entry_snapshot(row, fields, old)
    db.delete(row)
    _flush(db)
    _audit(db, actor, 'delete', 'employee', employee_id, old=before)
    db.commit()
