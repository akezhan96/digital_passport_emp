"""Small, typed dossier-to-score rules. No expressions, inference or model calls."""
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from types import SimpleNamespace
from fastapi import HTTPException
from models import (CustomFieldDefinition, CustomFieldValue, EducationLevel, Language,
                    LanguageLevel, LanguageScale, CandidateCriterion, CandidateMethodology)
from candidate_schemas import CandidateSource
from services import candidate_tab_fields as tab_fields
from services.candidate_tab_fields import guard_tab_change, guard_tab_field_change


def confidential(criterion):
    return criterion.block == 'psychological' or (criterion.source or {}).get('visibility') == 'admin'


def fail(message, status=422):
    raise HTTPException(status, message)


def number(value):
    if isinstance(value, bool):
        fail('Нужно число / Сан қажет')
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        fail('Нужно конечное число / Ақырлы сан қажет')


def options(definition):
    if definition.field_type == 'boolean':
        return [{'value': True, 'name_ru': 'Да', 'name_kk': 'Иә'},
                {'value': False, 'name_ru': 'Нет', 'name_kk': 'Жоқ'}]
    return [{'value': str(o.get('value') if isinstance(o, dict) else o),
             'name_ru': str(o.get('name_ru') or o.get('label') or o.get('value')) if isinstance(o, dict) else str(o),
             'name_kk': str(o.get('name_kk') or o.get('name_ru') or o.get('label') or o.get('value')) if isinstance(o, dict) else str(o)}
            for o in (definition.options or [])]


def catalogue(db, *, include_confidential=False):
    fields = db.query(CustomFieldDefinition).filter_by(entity_type='employee', is_active=True).order_by(CustomFieldDefinition.sort_order, CustomFieldDefinition.id).all()
    data = [{'id': f.id, 'name_ru': f.name_ru, 'name_kk': f.name_kk or f.name_ru,
             'field_type': f.field_type, 'options': options(f), 'visibility': f.visibility or 'public'}
            for f in fields if f.field_type in ('select', 'number', 'boolean')
            and (include_confidential or f.visibility != 'admin')]
    def named(row, value):
        return {'value': value, 'name_ru': row.name_ru or row.code, 'name_kk': row.name_kk or row.name_ru or row.code}
    facts = [
        {'code': 'education_level', 'name_ru': 'Уровень завершённого образования', 'name_kk': 'Аяқталған білім деңгейі',
         'field_type': 'number', 'options': [named(r, r.rank) for r in db.query(EducationLevel).order_by(EducationLevel.rank).all()]},
        {'code': 'language_level', 'name_ru': 'Подтверждённый уровень языка', 'name_kk': 'Расталған тіл деңгейі',
         'field_type': 'number', 'options': [{**named(r, r.rank), 'scale_id': r.scale_id} for r in db.query(LanguageLevel).order_by(LanguageLevel.rank).all()],
         'arguments': [named(r, r.id) for r in db.query(Language).order_by(Language.name_ru).all()],
         'scales': [named(r, r.id) for r in db.query(LanguageScale).order_by(LanguageScale.id).all()]},
        {'code': 'company_experience_years', 'name_ru': 'Стаж в организации, лет', 'name_kk': 'Ұйымдағы еңбек өтілі, жыл',
         'field_type': 'number', 'options': []},
    ]
    return {'fields': data, 'facts': facts, 'tab_fields': tab_fields.catalogue_fields(db, include_confidential)}


class SourceContext:
    """Per-operation cache only: never reuse personnel facts across requests."""
    def __init__(self, db, employee=None, field_sources=()):
        self.db, self.employee = db, employee
        self._definitions = self._values = self._catalogue = None
        self.readings = {}
        tab_ids = [s['field_id'] for s in field_sources if s and s.get('kind') == 'tab_field' and s.get('field_id')]
        self.tabs = tab_fields.TabReadings(db, tab_ids, employee) if tab_ids else None

    def definition(self, identity):
        if self._definitions is None:
            self._definitions = {f.id:f for f in self.db.query(CustomFieldDefinition).filter_by(entity_type='employee').all()}
        return self._definitions.get(identity)

    def value(self, identity):
        if self._values is None:
            self._values = {v.definition_id:v for v in self.db.query(CustomFieldValue).filter_by(
                entity_type='employee',entity_id=self.employee.id).all()}
        return self._values.get(identity)

    def facts(self):
        if self._catalogue is None:
            self._catalogue = {f['code']:f for f in catalogue(self.db, include_confidential=True)['facts']}
        return self._catalogue


def normalize_source(db, source, block, maximum, *, context=None):
    source = CandidateSource.model_validate(source or {}).model_dump(mode='json', exclude_none=True)
    if source['kind'] == 'manual':
        return None
    if block == 'psychological':
        fail('Психологические показатели подтверждаются вручную / Психологиялық көрсеткіштер қолмен расталады')
    if not source['rules']:
        fail('Добавьте правило начисления баллов / Ұпай беру ережесін қосыңыз')
    if source['kind'] == 'tab_field':
        context = context or SourceContext(db, field_sources=[source])
        tabs = context.tabs or tab_fields.TabReadings(db, [source.get('field_id')])
        field, section = tabs.definition(source.get('field_id'))
        kind, choices = field.field_type, []
        source.update(visibility=section.visibility, label_ru=f'{section.name_ru} / {field.name_ru}',
                      label_kk=f'{section.name_kk} / {field.name_kk}')
        for key in ('fact', 'argument', 'scale_id'):
            source.pop(key, None)
    elif source['kind'] == 'dossier_field':
        field = (context.definition(source['field_id']) if context else db.get(CustomFieldDefinition, source['field_id'])) if source.get('field_id') else None
        if not field or field.entity_type != 'employee' or not field.is_active or field.field_type not in ('number', 'boolean', 'select'):
            fail('Поле личного дела недоступно / Жеке іс өрісі қолжетімсіз')
        kind, choices = field.field_type, options(field)
        source.update(visibility=field.visibility or 'public', label_ru=field.name_ru, label_kk=field.name_kk or field.name_ru)
        source.pop('fact', None); source.pop('argument', None); source.pop('scale_id', None)
    else:
        facts = context.facts() if context else {f['code']: f for f in catalogue(db, include_confidential=True)['facts']}
        fact = facts.get(source.get('fact'))
        if not fact:
            fail('Выберите источник из личного дела / Жеке істен дереккөзді таңдаңыз')
        source.pop('field_id', None)
        kind, choices = 'number', fact['options']
        if source['fact'] == 'language_level':
            if source.get('argument') not in {o['value'] for o in fact['arguments']} or source.get('scale_id') not in {o['value'] for o in fact['scales']}:
                fail('Выберите язык и шкалу / Тіл мен шкаланы таңдаңыз')
            choices = [o for o in choices if o['scale_id'] == source['scale_id']]
        else:
            source.pop('argument', None); source.pop('scale_id', None)
        source.update(visibility='public', label_ru=fact['name_ru'], label_kk=fact['name_kk'])
    seen = set()
    for rule in source['rules']:
        if number(rule['points']) > maximum:
            fail('Баллы правила превышают максимум показателя / Ереже ұпайы көрсеткіш максимумынан асады')
        value = rule['value']
        if source['kind'] == 'tab_field':
            tab_fields.validate_rule(kind, rule, number)
        elif rule['operator'] == 'present':
            fail('Это условие доступно только для полей вкладки / Бұл шарт тек қойынды өрістеріне қолжетімді')
        elif kind == 'boolean':
            if type(value) is not bool or rule['operator'] != 'eq':
                fail('Для Да/Нет выберите значение без сравнения / Иә/Жоқ үшін салыстырусыз мәнді таңдаңыз')
        elif kind == 'select':
            if rule['operator'] != 'eq' or not isinstance(value, str) or value not in {o['value'] for o in choices}:
                fail('Выберите допустимый вариант поля / Өрістің жарамды нұсқасын таңдаңыз')
        else:
            value = number(value)
            if choices and value not in {number(o['value']) for o in choices}:
                fail('Выберите уровень из справочника / Анықтамалықтан деңгейді таңдаңыз')
            rule['value'] = float(value)
        signature = (rule['operator'], str(rule['value']).casefold() if kind == 'text' else str(rule['value']))
        if signature in seen:
            fail('Повторяющиеся условия начисления / Қайталанатын ұпай беру шарттары')
        seen.add(signature)
    return source


def field_usage(db, definition_id, *, active_only=False):
    query = db.query(CandidateCriterion).join(CandidateMethodology)
    if active_only:
        query = query.filter(CandidateMethodology.status == 'active')
    return [c for c in query.all() if (c.source or {}).get('kind') == 'dossier_field'
            and (c.source or {}).get('field_id') == definition_id]


def guard_field_change(db, definition, payload=None, *, deleting=False):
    payload = payload or {}
    usage = field_usage(db, definition.id)
    published = [c for c in usage if c.methodology.status in ('active', 'archived')]
    if payload.get('visibility', definition.visibility or 'public') != (definition.visibility or 'public'):
        # Past query/report snapshots can mention any field, even before it
        # is linked to a methodology. Do not silently reclassify their data.
        fail('Права поля задаются при создании. Для других прав создайте новое поле / Өріс құқықтары жасалғанда белгіленеді. Басқа құқықтар үшін жаңа өріс жасаңыз', 409)
    if usage and payload.get('field_type', definition.field_type) != definition.field_type:
        fail('Тип используемого поля изменить нельзя / Қолданылатын өріс түрін өзгертуге болмайды', 409)
    if published and (deleting or payload.get('is_active') is False):
        fail('Поле используется опубликованной методикой. Сохраните его для оценки и истории / Өріс жарияланған әдістемеде қолданылады. Оны бағалау мен тарих үшін сақтаңыз', 409)
    if published and 'options' in payload:
        available = {str(o.get('value') if isinstance(o, dict) else o) for o in payload['options']}
        required = {str(r['value']) for c in published for r in c.source.get('rules', [])}
        if not required <= available:
            fail('Вариант используется опубликованной методикой / Нұсқа жарияланған әдістемеде қолданылады', 409)


def _read_value(db, employee, source, today, *, context=None):
    metadata = {}
    if source['kind'] == 'dossier_field':
        field = context.definition(source['field_id']) if context else db.get(CustomFieldDefinition, source['field_id'])
        if not field or not field.is_active:
            return None, metadata, None
        row = context.value(field.id) if context else db.query(CustomFieldValue).filter_by(definition_id=field.id, entity_type='employee', entity_id=employee.id).first()
        value = (row.value_number if field.field_type == 'number' else row.as_python()) if row else None
        if field.field_type == 'select' and value is not None and value not in {o['value'] for o in options(field)}:
            value = None
        metadata = {'field_id': field.id, 'field_updated_at': str(field.updated_at), 'value_updated_at': str(row.updated_at) if row else None}
        labels = next((o for o in options(field) if type(o['value']) == type(value) and o['value'] == value), None)
        return value, metadata, labels
    fact = source['fact']
    if fact == 'education_level':
        rows = [r for r in employee.educations if r.end_year and r.end_year <= today.year and r.level]
        row = max(rows, key=lambda r: r.level.rank, default=None)
        return (row.level.rank if row else None), {'record_id': row.id if row else None}, ({'name_ru': row.level.name_ru, 'name_kk': row.level.name_kk} if row else None)
    if fact == 'language_level':
        rows = [r for r in employee.languages if r.language_id == source['argument'] and r.scale_id == source['scale_id']
                    and r.is_confirmed and r.level and r.level.scale_id == source['scale_id']
                    and (not r.valid_until or r.valid_until >= today) and (not r.confirmed_at or r.confirmed_at <= today)]
        row = max(rows, key=lambda r: (r.level.rank, r.id or 0), default=None)
        return (row.level.rank if row else None), {'record_id': row.id if row else None, 'valid_until': str(row.valid_until) if row and row.valid_until else None}, ({'name_ru': row.level.name_ru, 'name_kk': row.level.name_kk} if row else None)
    from services.metrics import compute_employee_metrics
    rows = [r for r in employee.work_experience if r.is_internal and r.date_from and r.date_from <= today]
    if not rows:
        return None, {}, None
    return compute_employee_metrics(db, employee, today=today)['company_experience_years'], {'as_of': today.isoformat()}, None


def calculated_sources(db, employee, method, technical, *, today=None):
    today = today or date.today()
    evidence, scores = [], []
    applicable = [c for c in method.criteria if c.enabled and (c.block != 'technical' or technical)]
    context = SourceContext(db, employee, (c.source for c in applicable))
    for criterion in applicable:
        source = criterion.source or {}
        if source.get('kind', 'manual') == 'manual':
            continue
        # Revalidate definitions: an inactive/missing source must not silently award points.
        normalized = normalize_source(db, source, criterion.block, criterion.max_points, context=context)
        if normalized['kind'] == 'tab_field':
            value, metadata, labels, matching, awarded = tab_fields.award(context.tabs, normalized, today)
        else:
            key = tuple(normalized.get(k) for k in ('kind','field_id','fact','argument','scale_id'))
            if key not in context.readings:
                context.readings[key] = _read_value(db, employee, normalized, today, context=context)
            value, metadata, labels = context.readings[key]
            awarded, matching = None, []
            if value is not None:
                for index, rule in enumerate(normalized['rules']):
                    actual, expected = value, rule['value']
                    if rule['operator'] != 'eq' or type(value) not in (bool, str):
                        actual, expected = number(value), number(expected)
                    if (rule['operator'] == 'eq' and actual == expected) or (rule['operator'] == 'gte' and actual >= expected) or (rule['operator'] == 'lte' and actual <= expected):
                        matching.append(index)
                awarded = max((number(normalized['rules'][i]['points']) for i in matching), default=Decimal(0))
        if awarded is not None:
            scores.append({'position': criterion.position, 'points': awarded})
        evidence.append({'position': criterion.position, 'status': 'missing' if value is None else 'matched' if matching else 'no_match',
                         'source_label_ru': normalized['label_ru'], 'source_label_kk': normalized['label_kk'],
                         'value': str(value) if isinstance(value, Decimal) else value, 'value_label_ru': (labels or {}).get('name_ru'), 'value_label_kk': (labels or {}).get('name_kk'),
                         'points': float(awarded) if awarded is not None else None,
                         'confidential': confidential(criterion), 'source': normalized, 'matched_rules': matching, 'evidence': metadata})
    body = {'employee_id': employee.id, 'methodology_id': method.id, 'methodology_revision': method.revision,
            'technical_profile': technical, 'evidence': evidence}
    digest = sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    return scores, evidence, digest


def preview(db, employee_id, payload):
    from services import candidate_methodology as cm
    from models import Employee
    employee = db.get(Employee, employee_id)
    if not employee:
        fail('Сотрудник не найден / Қызметкер табылмады', 404)
    method = cm.get_method(db, payload.methodology_id)
    if method.status not in ('active', 'archived'):
        fail('Выберите опубликованную методику / Жарияланған әдістемені таңдаңыз', 409)
    calculated, evidence, fingerprint = calculated_sources(db, employee, method, payload.technical_profile)
    allowed = {c.position: c for c in cm.applicable(method.criteria, payload.technical_profile, True)}
    manual = [{'position': s.position, 'points': s.points} for s in payload.scores if (allowed.get(s.position).source or {}).get('kind', 'manual') == 'manual'] if all(s.position in allowed for s in payload.scores) else None
    if manual is None or any(s['points'] > allowed[s['position']].max_points for s in manual):
        fail('Баллы вне диапазона или показатель неприменим / Балдар ауқымнан тыс немесе көрсеткіш қолданылмайды')
    scores = manual + calculated
    virtual = SimpleNamespace(id=None, created_at=None, technical_profile=payload.technical_profile,
        scores=[SimpleNamespace(criterion_id=allowed[s['position']].id, points=Decimal(str(s['points']))) for s in scores])
    return {'scores': [{'position': s['position'], 'points': float(s['points'])} for s in scores],
            'source_evidence': evidence, 'source_fingerprint': fingerprint,
            'summary': cm.summarize(method, employee, virtual, include_confidential=True)}


def evaluation_source_state(db, employee, evaluation):
    if not evaluation or not evaluation.source_fingerprint:
        return {'has_sources': False, 'stale': False}
    try:
        _, _, fingerprint = calculated_sources(db, employee, evaluation.methodology, evaluation.technical_profile)
        return {'has_sources': True, 'stale': fingerprint != evaluation.source_fingerprint}
    except HTTPException:
        return {'has_sources': True, 'stale': True}
