"""Rank saved dossier assessments against one published vacancy methodology.

This is decision support. No source is auto-scored here and no personnel record
is changed. The evaluation revision, criteria and vacancy settings are frozen.
"""
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from models import Employee, CandidateEvaluation, MatchingRun, MatchingResult
from services.candidate_methodology import get_method, applicable, summarize, method_dict


def settings_snapshot(vacancy, method, include_confidential):
    return {'kind': 'candidate_methodology',
            'methodology': jsonable_encoder(method_dict(method, include_confidential=include_confidential)),
            'min_candidate_percent': float(vacancy.min_candidate_percent),
            'requires_technical_profile': vacancy.requires_technical_profile,
            'scope': 'full' if include_confidential else 'public',
            'captured_at': datetime.utcnow().isoformat() + 'Z'}


def run_candidate_matching(db, run_id, employee_ids=None, verified_only=True):
    run = db.get(MatchingRun, run_id)
    if not run or not run.candidate_methodology_id:
        return False
    if run.status == 'completed':
        return True
    try:
        method = get_method(db, run.candidate_methodology_id)
        settings = run.methodology_snapshot
        query = db.query(Employee).filter(Employee.employment_status == 'active')
        if verified_only:
            query = query.filter(Employee.profile_status == 'verified')
        if employee_ids is not None:
            query = query.filter(Employee.id.in_(employee_ids))
        employees = query.order_by(Employee.id).all()
        latest = (db.query(func.max(CandidateEvaluation.id).label('id'))
                  .filter(CandidateEvaluation.employee_id.in_([e.id for e in employees]),
                          CandidateEvaluation.methodology_id == method.id)
                  .group_by(CandidateEvaluation.employee_id).subquery())
        evaluations = (db.query(CandidateEvaluation)
                       .join(latest, CandidateEvaluation.id == latest.c.id)
                       .options(selectinload(CandidateEvaluation.scores)).all())
        indexed = {e.employee_id: e for e in evaluations}
        scored = []
        for employee in employees:
            evaluation = indexed.get(employee.id)
            summary = summarize(method, employee, evaluation,
                                include_confidential=run.include_confidential)
            summary['evaluation_revision'] = evaluation.revision if evaluation else None
            failures = []
            def fail(ru, kk):
                failures.append({'requirement_ru': ru, 'requirement_kk': kk,
                                 'detail': {'ru': ru, 'kk': kk}})
            if summary['earned_points'] is None:
                fail('Нет сохранённой оценки по выбранной версии', 'Таңдалған нұсқа бойынша сақталған баға жоқ')
            elif not summary['complete']:
                fail('Оценка заполнена не полностью', 'Баға толық толтырылмаған')
            if summary['percent'] is not None and summary['percent'] < settings['min_candidate_percent']:
                fail('Коэффициент ниже порога вакансии', 'Коэффициент бос орын шегінен төмен')
            if settings['requires_technical_profile'] and not summary['technical_profile']:
                fail('Требуется подтверждённый технический профиль', 'Расталған техникалық бейін қажет')
            allowed = applicable(method.criteria, summary['technical_profile'], run.include_confidential)
            sections = {s['key']: s.get('position', 0) for s in settings['methodology'].get('sections', [])}
            allowed.sort(key=lambda c: (sections.get(c.section_key or c.block, 0),
                         c.display_order if c.display_order is not None else c.position, c.id))
            points = {s.criterion_id: float(s.points) for s in evaluation.scores} if evaluation else {}
            explanation = {'kind': 'candidate_methodology', 'methodology_summary': summary,
                'requirements': [], 'critical_failures': failures, 'gaps': [],
                'criteria': [{'id': c.id, 'position': c.position, 'block': c.block,
                              'section_key': c.section_key or c.block,
                              'display_order': c.display_order if c.display_order is not None else c.position,
                              'name_ru': c.name_ru, 'name_kk': c.name_kk,
                              'points': points.get(c.id), 'max_points': float(c.max_points)}
                             for c in allowed],
                'min_candidate_percent': settings['min_candidate_percent'],
                'requires_technical_profile': settings['requires_technical_profile'],
                'notice': {'ru': 'Сопоставление сохранённых оценок. Решение принимает специалист; это не автоматическое назначение.',
                           'kk': 'Сақталған бағаларды салыстыру. Шешімді маман қабылдайды; бұл автоматты тағайындау емес.'}}
            scored.append({'employee_id': employee.id, 'summary': summary,
                'qualified': not failures, 'explanation': explanation,
                'snapshot': {'evaluation_id': summary['evaluation_id'],
                             'evaluation_revision': summary['evaluation_revision'],
                             'evaluated_at': summary['evaluated_at'].isoformat() if summary['evaluated_at'] else None,
                             'methodology_id': method.id, 'technical_profile': summary['technical_profile'],
                             'source_fingerprint': getattr(evaluation, 'source_fingerprint', None)
                                 if evaluation and run.include_confidential else None}})
            # JSON columns require a portable timestamp; other summary users
            # still retain the service's datetime representation.
            summary['evaluated_at'] = scored[-1]['snapshot']['evaluated_at']
        scored.sort(key=lambda s: (not s['qualified'], not s['summary']['complete'],
                    -(s['summary']['percent'] if s['summary']['percent'] is not None else -1), s['employee_id']))
        for rank, item in enumerate(scored, 1):
            db.add(MatchingResult(run_id=run.id, employee_id=item['employee_id'], system_rank=rank,
                score=item['summary']['percent'] if item['summary']['percent'] is not None else 0,
                readiness_code=('not_assessed' if item['summary']['percent'] is None else 'review_ready' if item['qualified'] else 'needs_review'),
                is_qualified=item['qualified'], explanation=item['explanation'], candidate_snapshot=item['snapshot']))
        run.status, run.completed_at = 'completed', datetime.utcnow()
        run.total_evaluated = len(scored)
        run.total_qualified = sum(item['qualified'] for item in scored)
        db.commit()
        return True
    except Exception:
        db.rollback()
        run = db.get(MatchingRun, run_id)
        run.status = 'error'
        run.error_message = 'Не удалось сопоставить сохранённые оценки / Сақталған бағаларды салыстыру мүмкін болмады'
        db.commit()
        return False
