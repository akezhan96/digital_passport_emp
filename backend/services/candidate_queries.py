"""Read-only bridge from dossier evaluations to validated analytics queries.

Models receive catalogue labels only. Values are selected and calculated here,
with the same applicability and privacy rules as the dossier and matrix.
"""
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from models import CandidateMethodology, CandidateEvaluation
from services.candidate_methodology import applicable, summarize
from services.candidate_sources import confidential


SUMMARY_FIELDS = {
    'candidate_points': 'earned_points',
    'candidate_max_points': 'max_points',
    'candidate_percent': 'percent',
    'candidate_complete': 'complete',
    'candidate_missing_count': 'missing_count',
    'candidate_version': 'version',
    'candidate_technical_profile': 'technical_profile',
}
CANDIDATE_FIELDS = {*SUMMARY_FIELDS, 'candidate_criterion'}


def active_method(db):
    return (db.query(CandidateMethodology)
            .filter(CandidateMethodology.status == 'active')
            .options(selectinload(CandidateMethodology.criteria)).first())


def query_data(db, employees, *, include_confidential=False):
    method = active_method(db)
    if method is None:
        return {'methodology_id': None, 'summaries': {}, 'values': {}, 'confidential': False}
    ids = [e.id for e in employees]
    evaluations = []
    if ids:
        latest = (db.query(func.max(CandidateEvaluation.id).label('id'))
                  .filter(CandidateEvaluation.methodology_id == method.id,
                          CandidateEvaluation.employee_id.in_(ids))
                  .group_by(CandidateEvaluation.employee_id).subquery())
        evaluations = (db.query(CandidateEvaluation)
                       .join(latest, CandidateEvaluation.id == latest.c.id)
                       .options(selectinload(CandidateEvaluation.scores)).all())
    indexed = {e.employee_id: e for e in evaluations}
    summaries, values = {}, {}
    for employee in employees:
        evaluation = indexed.get(employee.id)
        summary = summarize(method, employee, evaluation,
                            include_confidential=include_confidential)
        summaries[employee.id] = summary
        row = {code: summary[key] for code, key in SUMMARY_FIELDS.items()}
        # Exclude unavailable criteria before filter evaluation as well as
        # summation: even a count must not reveal confidential score thresholds.
        allowed = {c.id for c in applicable(method.criteria,
                    summary['technical_profile'], include_confidential)}
        if evaluation:
            row.update({f'candidate_criterion:{s.criterion_id}': float(s.points)
                        for s in evaluation.scores if s.criterion_id in allowed})
        values[employee.id] = row
    return {'methodology_id': method.id, 'summaries': summaries, 'values': values,
            'confidential': include_confidential and any(
                c.enabled and confidential(c) for c in method.criteria)}


def query_uses_confidential(definition, fields, group_by=None):
    indexed = {f['code']: f for f in fields}
    conditions = (definition or {}).get('conditions', [])
    if group_by:
        conditions = [*conditions, {'field': group_by}]
    for condition in conditions:
        field = indexed.get(condition.get('field'), {})
        if field.get('confidential'):
            return True
        if any(str(o['value']) == str(condition.get('argument')) and o.get('confidential')
               for o in (field.get('argument') or {}).get('options', [])):
            return True
    return False


def uses_candidate(definition):
    return any(c.get('field') in CANDIDATE_FIELDS
               for c in (definition or {}).get('conditions', []))


def plan_visible(plan, include_confidential=False):
    return include_confidential or not (plan or {}).get('confidential', False)
