"""Point assessments read from the personnel dossier, with immutable history.

The active method defines the denominator. Missing scores stay visibly missing;
they never improve a percentage by shrinking its denominator. Confidential
scores are removed before summing, rather than hiding only the UI column.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from copy import deepcopy
from services.candidate_sources import confidential as criterion_is_confidential, normalize_source, SourceContext
from models import (Employee, CandidateMethodology, CandidateCriterion,
                    CandidateEvaluation, CandidateScore, AuditLog)


def block_for(position):
    return 'general' if position <= 34 else 'technical' if position <= 41 else 'psychological'


def method_sections(method):
    if method.sections is not None:
        return method.sections
    return [{'key': kind, 'kind': kind, 'name_ru': ru, 'name_kk': kk, 'position': i}
            for i, (kind, ru, kk) in enumerate((('general', 'Общие показатели', 'Жалпы көрсеткіштер'),
                ('technical', 'Технические показатели', 'Техникалық көрсеткіштер'),
                ('psychological', 'Психологические показатели', 'Психологиялық көрсеткіштер')))]


def method_dict(method, *, include_confidential=True):
    return {'id': method.id, 'version': method.version, 'name_ru': method.name_ru,
            'name_kk': method.name_kk, 'status': method.status, 'revision': method.revision,
            'activated_at': method.activated_at,
            'sections': [s for s in method_sections(method) if include_confidential or s['kind'] != 'psychological'],
            'criteria': [{'id': c.id, 'position': c.position, 'block': c.block,
                          'section_key': c.section_key or c.block, 'display_order': c.display_order if c.display_order is not None else c.position,
                          'name_ru': c.name_ru, 'name_kk': c.name_kk,
                          'max_points': float(c.max_points), 'enabled': c.enabled, 'source': c.source}
                         for c in sorted(method.criteria, key=lambda c: (c.display_order if c.display_order is not None else c.position, c.position))
                         if include_confidential or not criterion_is_confidential(c)]}


def get_method(db, methodology_id=None, *, lock=False):
    query = db.query(CandidateMethodology)
    if methodology_id is None:
        query = query.filter(CandidateMethodology.status == 'active')
    else:
        query = query.filter(CandidateMethodology.id == methodology_id)
    if lock:
        query = query.with_for_update()
    method = query.first()
    if not method:
        raise HTTPException(404, 'Методика не найдена / Әдістеме табылмады')
    return method


def seed_candidate_methodology(db):
    """Reference-only seed, no employee scores and no commit owned by caller."""
    existing = db.query(CandidateMethodology).order_by(CandidateMethodology.version.desc()).all()
    if existing:
        return next((m for m in existing if m.status == 'active'), existing[0])
    method = CandidateMethodology(version=1, status='active', revision=1,
        name_ru='Оценка кандидатов в заграничные представительства',
        name_kk='Шетелдік өкілдіктерге үміткерлерді бағалау',
        created_by='system', activated_by='system', activated_at=datetime.utcnow())
    db.add(method)
    db.flush()
    psychology = [
        ('Работа в команде', 'Командада жұмыс істеу'),
        ('Лидерство', 'Көшбасшылық'),
        ('Адаптация', 'Бейімделу'),
        ('Устойчивость к нагрузке', 'Жүктемеге төзімділік'),
        ('Межкультурное взаимодействие', 'Мәдениетаралық өзара әрекеттесу'),
    ]
    for position in range(3, 47):
        block = block_for(position)
        if block == 'general':
            ru, kk = f'Общий показатель {position - 2:02}', f'Жалпы көрсеткіш {position - 2:02}'
        elif block == 'technical':
            ru, kk = f'Технический показатель {position - 34:02}', f'Техникалық көрсеткіш {position - 34:02}'
        else:
            ru, kk = psychology[position - 42]
        method.criteria.append(CandidateCriterion(position=position, block=block,
            name_ru=ru, name_kk=kk, max_points=Decimal([5, 10, 15, 20][(position - 3) % 4]), enabled=True))
    db.flush()
    return method


def clone_method(db, methodology_id, actor):
    source = get_method(db, methodology_id, lock=True)
    version = (db.query(func.max(CandidateMethodology.version)).scalar() or 0) + 1
    target = CandidateMethodology(version=version, name_ru=source.name_ru, name_kk=source.name_kk,
                                  status='draft', revision=1, previous_id=source.id, created_by=actor,
                                  sections=deepcopy(method_sections(source)))
    target.criteria = [CandidateCriterion(position=c.position, block=c.block,
                          name_ru=c.name_ru, name_kk=c.name_kk,
                          max_points=c.max_points, enabled=c.enabled, source=deepcopy(c.source),
                          section_key=c.section_key or c.block, display_order=c.display_order if c.display_order is not None else c.position) for c in source.criteria]
    db.add(target)
    db.flush()
    db.add(AuditLog(action='create', entity_type='candidate_methodology', entity_id=target.id,
                    new_values={'version': target.version, 'source_id': source.id}, changed_by=actor))
    return target


def create_method(db, payload, actor):
    if payload.template_id:
        target = clone_method(db, payload.template_id, actor)
        target.name_ru, target.name_kk = payload.name_ru, payload.name_kk
    else:
        version = (db.query(func.max(CandidateMethodology.version)).scalar() or 0) + 1
        target = CandidateMethodology(version=version, name_ru=payload.name_ru, name_kk=payload.name_kk,
                                      status='draft', revision=1, created_by=actor, sections=[])
        db.add(target); db.flush()
        db.add(AuditLog(action='create', entity_type='candidate_methodology', entity_id=target.id,
                        new_values={'version': version}, changed_by=actor))
    return target


def delete_method(db, methodology_id, actor):
    method = get_method(db, methodology_id, lock=True)
    from models import Vacancy, MatchingRun
    if (method.status != 'draft' or db.query(CandidateEvaluation).filter_by(methodology_id=method.id).count()
            or db.query(Vacancy).filter_by(candidate_methodology_id=method.id).count()
            or db.query(MatchingRun).filter_by(candidate_methodology_id=method.id).count()
            or db.query(CandidateMethodology).filter_by(previous_id=method.id).count()):
        raise HTTPException(409, 'Используемую или опубликованную методику удалить нельзя / Қолданылатын немесе жарияланған әдістемені жоюға болмайды')
    db.add(AuditLog(action='delete', entity_type='candidate_methodology', entity_id=method.id,
                    old_values={'version': method.version}, changed_by=actor))
    db.delete(method); db.flush()


def update_method(db, methodology_id, payload, actor):
    method = get_method(db, methodology_id, lock=True)
    if method.status != 'draft':
        raise HTTPException(409, 'Создайте новую версию методики / Әдістеменің жаңа нұсқасын жасаңыз')
    if method.revision != payload.expected_revision:
        raise HTTPException(409, 'Методика уже изменена. Обновите страницу / Әдістеме өзгертілді. Бетті жаңартыңыз')
    sections = [s.model_dump() for s in payload.sections] if payload.sections is not None else method_sections(method)
    section_by_key = {s['key']: s for s in sections}
    rows = {c.position: c for c in method.criteria}
    kept = []
    sources = SourceContext(db, field_sources=(v.source.model_dump() for v in payload.criteria if v.source))
    for values in payload.criteria:
        section_key = values.section_key or block_for(values.position)
        if section_key not in section_by_key:
            raise HTTPException(422, 'Выберите раздел показателя / Көрсеткіш бөлімін таңдаңыз')
        row = rows.get(values.position)
        if values.id is not None and (not row or row.id != values.id):
            raise HTTPException(422, 'Ключ показателя нельзя менять / Көрсеткіш кілтін өзгертуге болмайды')
        if row is None:
            row = CandidateCriterion(position=values.position)
        row.block, row.section_key = section_by_key[section_key]['kind'], section_key
        row.display_order = values.display_order if values.display_order is not None else values.position
        row.name_ru, row.name_kk = values.name_ru, values.name_kk
        row.max_points, row.enabled = values.max_points, values.enabled
        row.source = normalize_source(db, values.source.model_dump(mode='json') if values.source else None, row.block, values.max_points, context=sources)
        kept.append(row)
    method.criteria = kept
    method.sections = deepcopy(sections)
    method.name_ru, method.name_kk = payload.name_ru, payload.name_kk
    method.revision += 1
    db.add(AuditLog(action='update', entity_type='candidate_methodology', entity_id=method.id,
                    new_values={'version': method.version, 'revision': method.revision}, changed_by=actor))
    db.flush()
    return method


def activate_method(db, methodology_id, expected_revision, actor):
    # Lock all existing definitions in the same order: two publishers cannot
    # leave multiple active methods or overwrite a newly activated version.
    rows = db.query(CandidateMethodology).order_by(CandidateMethodology.id).with_for_update().all()
    method = next((m for m in rows if m.id == methodology_id), None)
    if not method:
        raise HTTPException(404, 'Методика не найдена / Әдістеме табылмады')
    if method.status != 'draft' or method.revision != expected_revision:
        raise HTTPException(409, 'Версия уже изменена. Обновите страницу / Нұсқа өзгертілді. Бетті жаңартыңыз')
    if not any(c.enabled for c in method.criteria):
        raise HTTPException(422, 'Добавьте и включите хотя бы один показатель / Кемінде бір көрсеткішті қосып іске қосыңыз')
    sources = SourceContext(db, field_sources=(c.source for c in method.criteria))
    for criterion in method.criteria:
        criterion.source = normalize_source(db, criterion.source, criterion.block, criterion.max_points, context=sources)
    for row in rows:
        if row.status == 'active':
            row.status = 'archived'
    method.status, method.activated_by = 'active', actor
    method.activated_at = datetime.utcnow()
    method.revision += 1
    db.add(AuditLog(action='approve', entity_type='candidate_methodology', entity_id=method.id,
                    new_values={'version': method.version}, changed_by=actor))
    db.flush()
    return method


def applicable(criteria, technical, confidential):
    return [c for c in criteria if c.enabled
            and (technical or c.block != 'technical')
            and (confidential or not criterion_is_confidential(c))]


def score_percent(earned, maximum):
    if earned is None or not maximum:
        return None
    return float((earned * 100 / maximum).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def summarize(method, employee, evaluation, *, include_confidential=False):
    technical = evaluation.technical_profile if evaluation else employee.is_technical_specialist
    criteria = applicable(method.criteria, technical, include_confidential)
    score_map = {s.criterion_id: s.points for s in evaluation.scores} if evaluation else {}
    allowed_ids = {c.id for c in criteria}
    # Build allowed values before aggregation; a viewer cannot recover the
    # confidential subtotal by subtracting the visible rows from an overall sum.
    visible = [value for key, value in score_map.items() if key in allowed_ids]
    maximum = sum((c.max_points for c in criteria), Decimal(0))
    earned = sum(visible, Decimal(0)) if evaluation and visible else None
    return {'methodology_id': method.id, 'version': method.version,
            'name_ru': method.name_ru, 'name_kk': method.name_kk,
            'earned_points': float(earned) if earned is not None else None,
            'max_points': float(maximum), 'percent': score_percent(earned, maximum),
            'filled_count': len(visible), 'applicable_count': len(criteria),
            'missing_count': len(criteria) - len(visible),
            'complete': bool(criteria) and len(visible) == len(criteria),
            'partial_visibility': not include_confidential and any(c.enabled and criterion_is_confidential(c) for c in method.criteria),
            'technical_profile': bool(technical), 'evaluation_id': evaluation.id if evaluation else None,
            'evaluated_at': evaluation.created_at if evaluation else None}


def candidate_summaries(db, employee_ids, include_confidential=False, methodology_id=None):
    """Bounded queries for an entire matching/page batch, never N+1 scores."""
    employee_ids = list(set(employee_ids))
    if not employee_ids:
        return {}
    method = get_method(db, methodology_id)
    _ = method.criteria
    employees = db.query(Employee).filter(Employee.id.in_(employee_ids)).all()
    latest_ids = (db.query(func.max(CandidateEvaluation.id).label('id'))
                  .filter(CandidateEvaluation.methodology_id == method.id,
                          CandidateEvaluation.employee_id.in_(employee_ids))
                  .group_by(CandidateEvaluation.employee_id).subquery())
    evaluations = (db.query(CandidateEvaluation).join(latest_ids, CandidateEvaluation.id == latest_ids.c.id)
                   .options(selectinload(CandidateEvaluation.scores)).all())
    indexed = {e.employee_id: e for e in evaluations}
    return {e.id: summarize(method, e, indexed.get(e.id), include_confidential=include_confidential) for e in employees}


def save_evaluation(db, employee_id, payload, actor):
    """Save a new dossier revision; caller commits. Used by UI and demo seed."""
    employee = db.query(Employee).filter(Employee.id == employee_id).with_for_update().first()
    if not employee:
        raise HTTPException(404, 'Сотрудник не найден / Қызметкер табылмады')
    # Lock the definition so activation cannot switch away while an evaluation
    # is validated against the current method.
    method = get_method(db, payload.methodology_id, lock=True)
    if method.status not in ('active', 'archived'):
        raise HTTPException(409, 'Оценка сохраняется только по опубликованной методике / Бағалау тек жарияланған әдістеме бойынша сақталады')
    previous = (db.query(CandidateEvaluation).filter_by(employee_id=employee_id, methodology_id=method.id)
                .order_by(CandidateEvaluation.revision.desc()).first())
    revision = previous.revision if previous else 0
    if payload.expected_revision != revision:
        raise HTTPException(409, 'Оценка уже изменена. Обновите карточку / Бағалау өзгертілді. Карточканы жаңартыңыз')
    from services.candidate_sources import calculated_sources
    calculated, evidence, fingerprint = calculated_sources(db, employee, method, payload.technical_profile)
    if evidence and (not payload.confirm_sources or not payload.source_fingerprint):
        raise HTTPException(409, 'Сначала рассчитайте и подтвердите значения из личного дела / Алдымен жеке іс мәндерін есептеп растаңыз')
    if evidence and payload.source_fingerprint != fingerprint:
        raise HTTPException(409, 'Данные личного дела изменились. Повторите расчёт и подтверждение / Жеке іс деректері өзгерді. Есептеу мен растауды қайталаңыз')
    enabled = {c.position: c for c in applicable(method.criteria, payload.technical_profile, True)}
    for value in payload.scores:
        criterion = enabled.get(value.position)
        if not criterion or value.points > criterion.max_points:
            raise HTTPException(422, 'Баллы вне диапазона или показатель неприменим / Балдар ауқымнан тыс немесе көрсеткіш қолданылмайды')
    manual = [value for value in payload.scores if (enabled[value.position].source or {}).get('kind', 'manual') == 'manual']
    from candidate_schemas import CandidateScoreIn
    scores = manual + [CandidateScoreIn(**value) for value in calculated]
    snapshots = {e['position']: e for e in evidence}
    evaluation = CandidateEvaluation(employee_id=employee_id, methodology_id=method.id,
        revision=revision + 1, technical_profile=payload.technical_profile,
        evaluated_by=actor, note=payload.note.strip(), source_fingerprint=fingerprint if evidence else None,
        source_snapshot=deepcopy(evidence) if evidence else None)
    evaluation.scores = [CandidateScore(criterion_id=enabled[value.position].id, points=value.points,
                         source_snapshot=deepcopy(snapshots.get(value.position))) for value in scores]
    employee.is_technical_specialist = payload.technical_profile
    db.add(evaluation)
    db.flush()
    db.add(AuditLog(action='create', entity_type='candidate_evaluation', entity_id=evaluation.id,
                    new_values={'employee_id': employee_id, 'methodology_id': method.id, 'revision': evaluation.revision},
                    changed_by=actor))
    return evaluation


def evaluation_detail(db, employee_id, *, include_confidential=False, evaluation_id=None, methodology_id=None):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, 'Сотрудник не найден / Қызметкер табылмады')
    if evaluation_id is not None:
        evaluation = db.query(CandidateEvaluation).filter_by(id=evaluation_id, employee_id=employee_id).first()
        if not evaluation:
            raise HTTPException(404, 'Оценка не найдена / Бағалау табылмады')
        method = evaluation.methodology
    else:
        method = get_method(db, methodology_id)
        if method.status not in ('active', 'archived'):
            raise HTTPException(409, 'Методика ещё не опубликована / Әдістеме әлі жарияланбаған')
        evaluation = (db.query(CandidateEvaluation).filter_by(employee_id=employee_id, methodology_id=method.id)
                      .order_by(CandidateEvaluation.revision.desc()).first())
    visible_criteria = {c.id: c for c in method.criteria if include_confidential or not criterion_is_confidential(c)}
    from services.candidate_sources import evaluation_source_state
    source_state = evaluation_source_state(db, employee, evaluation) if include_confidential and evaluation_id is None else {'stale': False}
    return {'employee_id': employee_id, 'methodology': method_dict(method, include_confidential=include_confidential),
            'revision': evaluation.revision if evaluation else 0,
            'technical_profile': evaluation.technical_profile if evaluation else employee.is_technical_specialist,
            'scores': [{'position': visible_criteria[s.criterion_id].position, 'points': float(s.points), 'source_snapshot': s.source_snapshot}
                       for s in evaluation.scores if s.criterion_id in visible_criteria] if evaluation else [],
            'note': evaluation.note if evaluation and include_confidential else '',
            'source_evidence': [e for e in (evaluation.source_snapshot or []) if include_confidential or not e.get('confidential')] if evaluation else [],
            'source_stale': source_state['stale'],
            'evaluated_by': evaluation.evaluated_by if evaluation else None,
            'summary': summarize(method, employee, evaluation, include_confidential=include_confidential),
            'read_only': evaluation_id is not None or method.status not in ('active', 'archived') or not include_confidential}
