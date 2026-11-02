"""Rank the latest saved dossier assessments within one published methodology."""
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Numeric, and_, case, func, or_, select, true, type_coerce

from models import CandidateEvaluation, CandidateScore, Employee, OrgUnit
from services.candidate_methodology import applicable, get_method, score_percent


class RankingFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    methodology_id: int | None = Field(default=None, gt=0)
    org_unit_id: int | None = Field(default=None, gt=0)
    include_subunits: bool = True
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    reveal_names: bool = False


def workforce(db, filters):
    scope = select(Employee.id).where(
        Employee.employment_status == 'active', Employee.profile_status != 'archived')
    if filters.org_unit_id is not None:
        if not db.get(OrgUnit, filters.org_unit_id):
            raise HTTPException(404, 'Подразделение не найдено / Бөлімше табылмады')
        if filters.include_subunits:
            tree = select(OrgUnit.id).where(OrgUnit.id == filters.org_unit_id).cte(recursive=True)
            tree = tree.union(select(OrgUnit.id).join(tree, OrgUnit.parent_id == tree.c.id))
            scope = scope.where(Employee.current_org_unit_id.in_(select(tree.c.id)))
        else:
            scope = scope.where(Employee.current_org_unit_id == filters.org_unit_id)
    return scope.cte('workforce')


def complete_totals(scope, method, general, technical):
    evaluation, score = CandidateEvaluation, CandidateScore
    latest = (select(evaluation.employee_id, func.max(evaluation.revision).label('revision'))
              .join(scope, scope.c.id == evaluation.employee_id)
              .where(evaluation.methodology_id == method.id)
              .group_by(evaluation.employee_id).subquery())
    # Inapplicable and confidential scores never participate in a sum, a
    # completeness check or a place. Zero is a valid saved score.
    general_ids = [c.id for c in general]
    technical_ids = [c.id for c in technical if c.block == 'technical']
    expected = case((evaluation.technical_profile, len(technical)), else_=len(general))
    points = type_coerce(func.round(func.sum(score.points), 2), Numeric(14, 2))
    return (select(evaluation.employee_id, evaluation.id.label('evaluation_id'),
                   evaluation.technical_profile, points.label('earned_points'))
            .join(latest, and_(evaluation.employee_id == latest.c.employee_id,
                               evaluation.revision == latest.c.revision))
            .join(score, score.evaluation_id == evaluation.id)
            .where(evaluation.methodology_id == method.id,
                   or_(score.criterion_id.in_(general_ids),
                       and_(evaluation.technical_profile, score.criterion_id.in_(technical_ids))))
            .group_by(evaluation.id, evaluation.employee_id, evaluation.technical_profile)
            .having(func.count(score.criterion_id) == expected)
            .cte('complete_totals'))


def employee_ranking(db, filters, *, include_confidential):
    method = get_method(db, filters.methodology_id)
    if method.status not in ('active', 'archived'):
        raise HTTPException(409, 'Выберите опубликованную методику / Жарияланған әдістемені таңдаңыз')
    general = applicable(method.criteria, False, include_confidential)
    technical = applicable(method.criteria, True, include_confidential)
    maxima = {profile: sum((c.max_points for c in criteria), Decimal(0))
              for profile, criteria in ((False, general), (True, technical))}
    scope = workforce(db, filters)
    totals = complete_totals(scope, method, general, technical)
    ranked = select(totals, func.rank().over(order_by=totals.c.earned_points.desc()).label('rank')).subquery()
    page = (select(ranked).order_by(ranked.c.rank, ranked.c.employee_id)
            .offset(filters.offset).limit(filters.limit).subquery())
    # Read counts and the ranked page in one snapshot, including a row of
    # counts when the selected scope or page is empty.
    counts = select(select(func.count()).select_from(scope).scalar_subquery().label('scope_total'),
                    select(func.count()).select_from(totals).scalar_subquery().label('total')).subquery()
    fields = [counts, page, Employee.anonymous_code, OrgUnit.id.label('unit_id'),
              OrgUnit.name_ru, OrgUnit.name_kk]
    if filters.reveal_names:
        fields.extend([Employee.last_name, Employee.first_name, Employee.middle_name])
    query = (select(*fields).select_from(counts.outerjoin(page, true()))
             .outerjoin(Employee, Employee.id == page.c.employee_id)
             .outerjoin(OrgUnit, Employee.current_org_unit_id == OrgUnit.id)
             .order_by(page.c.rank, page.c.employee_id))
    rows = db.execute(query).all()
    items = []
    for row in rows:
        if row.employee_id is None:
            continue
        display_name = row.anonymous_code or f'#{row.employee_id}'
        if filters.reveal_names:
            display_name = ' '.join(part for part in (row.last_name, row.first_name, row.middle_name) if part)
        maximum = maxima[row.technical_profile]
        items.append({'rank': row.rank, 'employee_id': row.employee_id, 'display_name': display_name,
                      'org_unit': {'id': row.unit_id, 'name_ru': row.name_ru, 'name_kk': row.name_kk}
                                  if row.unit_id is not None else None,
                      'earned_points': float(row.earned_points), 'max_points': float(maximum),
                      'percent': score_percent(row.earned_points, maximum), 'technical_profile': row.technical_profile,
                      'evaluation_id': row.evaluation_id})
    scope_total, total = rows[0].scope_total, rows[0].total
    return {'methodology': {'id': method.id, 'version': method.version, 'status': method.status,
                            'name_ru': method.name_ru, 'name_kk': method.name_kk},
            'scope_total': scope_total, 'total': total, 'excluded_count': scope_total - total,
            'partial_visibility': len(technical) < sum(c.enabled for c in method.criteria),
            'names_revealed': filters.reveal_names, 'items': items}
