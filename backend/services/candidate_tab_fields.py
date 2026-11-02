"""Sources backed by repeatable records in a configurable dossier tab."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import select

from models import (CandidateCriterion, CandidateMethodology, DossierSubsection,
                    DossierSubsectionEntry, DossierTabField, DossierTabValue)


def catalogue_fields(db, include_confidential):
    query = (db.query(DossierTabField, DossierSubsection)
             .join(DossierSubsection, DossierTabField.subsection_id == DossierSubsection.id)
             .filter(DossierTabField.is_active.is_(True), DossierSubsection.is_active.is_(True)))
    if not include_confidential:
        query = query.filter(DossierSubsection.visibility == 'public', DossierSubsection.tab != 'history')
    return [
        {'id': field.id, 'section_id': section.id, 'name_ru': field.name_ru, 'name_kk': field.name_kk,
         'section_ru': section.name_ru, 'section_kk': section.name_kk,
         'field_type': field.field_type, 'visibility': section.visibility, 'options': []}
        for field, section in query.order_by(DossierSubsection.id, DossierTabField.id)
    ]


class TabReadings:
    def __init__(self, db, field_ids, employee=None):
        ids = set(field_ids)
        query = db.query(DossierTabField).filter(DossierTabField.id.in_(ids))
        parents = db.query(DossierSubsection).filter(DossierSubsection.id.in_(
            select(DossierTabField.subsection_id).where(DossierTabField.id.in_(ids))))
        if employee is None:
            # Publishing and editing a definition must serialize with field archival/visibility changes.
            parents = parents.with_for_update(read=True)
            query = query.with_for_update(read=True)
        self.sections = {s.id: s for s in parents.order_by(DossierSubsection.id).populate_existing()}
        self.fields = {f.id: f for f in query.order_by(DossierTabField.id).populate_existing()}
        self.values = {}
        if employee is not None and self.fields:
            rows = (db.query(DossierTabValue.field_id, DossierSubsectionEntry.id, DossierTabValue.value)
                    .join(DossierTabField, DossierTabField.id == DossierTabValue.field_id)
                    .join(DossierSubsectionEntry, DossierSubsectionEntry.id == DossierTabValue.entry_id)
                    .filter(DossierSubsectionEntry.employee_id == employee.id,
                            DossierSubsectionEntry.subsection_id == DossierTabField.subsection_id,
                            DossierTabValue.field_id.in_(ids))
                    .order_by(DossierSubsectionEntry.id))
            for field_id, entry_id, value in rows:
                if value is not None and value != '':
                    self.values.setdefault(field_id, []).append((entry_id, value))

    def definition(self, field_id):
        field = self.fields.get(field_id)
        section = self.sections.get(field.subsection_id) if field else None
        if not field or not field.is_active or not section or not section.is_active:
            raise HTTPException(422, 'Поле вкладки недоступно / Қойынды өрісі қолжетімсіз')
        return field, section


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError
    return day


def validate_rule(kind, rule, number):
    op, value = rule['operator'], rule['value']
    if op == 'present':
        rule['value'] = ''
        return
    if kind == 'date':
        if value != 'today':
            try:
                iso_date(value)
            except ValueError:
                raise HTTPException(422, 'Укажите дату или «Сегодня» / Күнді немесе «Бүгін» мәнін таңдаңыз')
    elif kind == 'text':
        if op != 'eq' or not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise HTTPException(422, 'Введите текст для сравнения / Салыстыру мәтінін енгізіңіз')
        rule['value'] = value.strip()
    elif kind == 'number':
        rule['value'] = float(number(value))
    elif kind == 'boolean':
        if op != 'eq' or type(value) is not bool:
            raise HTTPException(422, 'Выберите Да или Нет / Иә немесе Жоқ таңдаңыз')
    else:
        raise HTTPException(422, 'Тип поля не поддерживается / Өріс түрі қолдау таппайды')


def matches(kind, actual, rule, today):
    op, expected = rule['operator'], rule['value']
    if op == 'present':
        return True
    if kind == 'date':
        actual = iso_date(actual)
        expected = today if expected == 'today' else iso_date(expected)
    elif kind == 'number':
        actual, expected = Decimal(str(actual)), Decimal(str(expected))
    elif kind == 'text':
        actual, expected = actual.strip().casefold(), expected.casefold()
    return actual == expected if op == 'eq' else actual >= expected if op == 'gte' else actual <= expected


def award(readings, source, today):
    field, _ = readings.definition(source['field_id'])
    rows = readings.values.get(field.id, [])
    metadata = {'field_id': field.id, 'record_count': len(rows)}
    if not rows:
        return None, metadata, None, [], None
    # Changes to other entries must invalidate a preview, even when the current best stays the same.
    metadata['values_hash'] = sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    best = None
    for entry_id, value in rows:
        matching = [i for i, rule in enumerate(source['rules']) if matches(field.field_type, value, rule, today)]
        points = max((Decimal(str(source['rules'][i]['points'])) for i in matching), default=Decimal(0))
        # Prefer a matching zero over a nonmatch. Entry ID is the stable tiebreaker.
        key = (points, bool(matching))
        if best is None or key > best[0]:
            best = (key, entry_id, value, matching)
    (points, _), metadata['entry_id'], value, matching = best
    return value, metadata, None, matching, points


def tab_usage(db, field_ids, published_only=False):
    ids = set(field_ids)
    if not ids:
        return False
    query = db.query(CandidateCriterion.source).join(CandidateMethodology)
    if published_only:
        query = query.filter(CandidateMethodology.status.in_(('active', 'archived')))
    return any(s and s.get('kind') == 'tab_field' and s.get('field_id') in ids for (s,) in query)


def guard_tab_field_change(db, field, changes):
    if changes.get('field_type', field.field_type) != field.field_type and tab_usage(db, [field.id]):
        raise HTTPException(409, 'Тип поля используется в методике. Создайте новое поле / Өріс түрі әдістемеде қолданылады. Жаңа өріс жасаңыз')
    if changes.get('is_active') is False and tab_usage(db, [field.id], published_only=True):
        raise HTTPException(409, 'Поле используется опубликованной методикой / Өріс жарияланған әдістемеде қолданылады')


def guard_tab_change(db, section, changes):
    if changes.get('is_active') is not False and changes.get('visibility', section.visibility) == section.visibility:
        return
    ids = db.scalars(select(DossierTabField.id).where(DossierTabField.subsection_id == section.id))
    visibility_changes = changes.get('visibility', section.visibility) != section.visibility
    # Drafts also contain copied public labels. A visibility change must not expose them.
    if tab_usage(db, ids, published_only=not visibility_changes):
        raise HTTPException(409, 'Вкладка используется в методике. Архивирование и смена доступа ограничены для сохранения оценок / Қойынды әдістемеде қолданылады. Бағаларды сақтау үшін мұрағаттау мен қолжетімділікті өзгерту шектелген')
