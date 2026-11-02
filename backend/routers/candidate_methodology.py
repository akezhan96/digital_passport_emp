"""Candidate methodology and dossier assessments, with server-side privacy."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_db
from auth import current_user
from models import Employee, CandidateMethodology, CandidateEvaluation
from candidate_schemas import CandidateMethodologyIn, CandidateActivateIn, CandidateEvaluationIn, CandidateCreateIn
from services import candidate_methodology as service
from services import candidate_sources

router = APIRouter()


@router.get('/candidate-sources')
def sources(request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    return candidate_sources.catalogue(db, include_confidential=user['role'] == 'admin')


@router.post('/employees/{employee_id}/evaluation-preview')
def preview(employee_id: int, payload: CandidateEvaluationIn, request: Request, db: Session = Depends(get_db)):
    admin(request)
    return candidate_sources.preview(db, employee_id, payload)


def admin(request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Нужны права администратора / Әкімші құқықтары қажет')
    return user['sub']


@router.get('/candidate-models')
def methods(request: Request, db: Session = Depends(get_db)):
    current_user(request)
    return [{'id': m.id, 'version': m.version, 'name_ru': m.name_ru, 'name_kk': m.name_kk,
             'status': m.status, 'revision': m.revision} for m in
            db.query(CandidateMethodology).order_by(CandidateMethodology.version.desc()).all()]


@router.get('/candidate-models/{methodology_id}')
def method(methodology_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    return service.method_dict(service.get_method(db, methodology_id), include_confidential=user['role'] == 'admin')


@router.post('/candidate-models', status_code=201)
def create(payload: CandidateCreateIn, request: Request, db: Session = Depends(get_db)):
    try:
        result = service.create_method(db, payload, admin(request))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Версия уже создана. Повторите запрос / Нұсқа жасалды. Сұрауды қайталаңыз')
    return service.method_dict(result)


@router.delete('/candidate-models/{methodology_id}', status_code=204)
def delete(methodology_id: int, request: Request, db: Session = Depends(get_db)):
    service.delete_method(db, methodology_id, admin(request))
    db.commit()


@router.post('/candidate-models/{methodology_id}/clone', status_code=201)
def clone(methodology_id: int, request: Request, db: Session = Depends(get_db)):
    actor = admin(request)
    try:
        result = service.clone_method(db, methodology_id, actor)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Другая версия уже создана. Обновите список / Басқа нұсқа жасалды. Тізімді жаңартыңыз')
    return service.method_dict(result)


@router.put('/candidate-models/{methodology_id}')
def update(methodology_id: int, payload: CandidateMethodologyIn, request: Request, db: Session = Depends(get_db)):
    result = service.update_method(db, methodology_id, payload, admin(request))
    db.commit()
    return service.method_dict(result)


@router.post('/candidate-models/{methodology_id}/activate')
def activate(methodology_id: int, payload: CandidateActivateIn, request: Request, db: Session = Depends(get_db)):
    result = service.activate_method(db, methodology_id, payload.expected_revision, admin(request))
    db.commit()
    return service.method_dict(result)


@router.get('/employees/{employee_id}/evaluation')
def evaluation(employee_id: int, request: Request, evaluation_id: int | None = None, db: Session = Depends(get_db), methodology_id: int | None = None):
    user = current_user(request)
    return service.evaluation_detail(db, employee_id, include_confidential=user['role'] == 'admin', evaluation_id=evaluation_id, methodology_id=methodology_id)


@router.put('/employees/{employee_id}/evaluation')
def save(employee_id: int, payload: CandidateEvaluationIn, request: Request, db: Session = Depends(get_db)):
    service.save_evaluation(db, employee_id, payload, admin(request))
    db.commit()
    return service.evaluation_detail(db, employee_id, include_confidential=True, methodology_id=payload.methodology_id)


@router.get('/employees/{employee_id}/evaluation-history')
def history(employee_id: int, request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    user = current_user(request)
    employee = db.query(Employee).filter_by(id=employee_id).first()
    if not employee:
        raise HTTPException(404, 'Сотрудник не найден / Қызметкер табылмады')
    query = db.query(CandidateEvaluation).filter_by(employee_id=employee_id)
    total = query.count()
    rows = query.options(selectinload(CandidateEvaluation.scores),
                         selectinload(CandidateEvaluation.methodology).selectinload(CandidateMethodology.criteria))
    rows = rows.order_by(CandidateEvaluation.id.desc()).offset(offset).limit(limit).all()
    return {'total': total, 'items': [{'id': e.id, 'revision': e.revision, 'created_at': e.created_at,
            'evaluated_by': e.evaluated_by, 'summary': service.summarize(e.methodology, employee, e,
                include_confidential=user['role'] == 'admin')} for e in rows]}


@router.get('/candidate-matrix')
def matrix(request: Request, methodology_id: int | None = None, search: str = Query('', max_length=200),
           org_unit_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
           db: Session = Depends(get_db)):
    user = current_user(request)
    confidential = user['role'] == 'admin'
    method = service.get_method(db, methodology_id)
    query = db.query(Employee).filter(Employee.employment_status == 'active')
    if search.strip():
        token = '%' + search.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        name = func.coalesce(Employee.last_name, '') + ' ' + func.coalesce(Employee.first_name, '') + ' ' + func.coalesce(Employee.middle_name, '')
        query = query.filter(or_(name.ilike(token, escape='\\'), Employee.anonymous_code.ilike(token, escape='\\'), Employee.personnel_number.ilike(token, escape='\\')))
    if org_unit_id is not None:
        query = query.filter(Employee.current_org_unit_id == org_unit_id)
    total = query.count()
    employees = query.options(selectinload(Employee.current_org_unit)).order_by(Employee.last_name, Employee.first_name, Employee.id).offset(offset).limit(limit).all()
    ids = [e.id for e in employees]
    summaries = service.candidate_summaries(db, ids, confidential, method.id)
    latest_ids = db.query(func.max(CandidateEvaluation.id).label('id')).filter(
        CandidateEvaluation.methodology_id == method.id, CandidateEvaluation.employee_id.in_(ids)).group_by(CandidateEvaluation.employee_id).subquery()
    evaluations = db.query(CandidateEvaluation).join(latest_ids, CandidateEvaluation.id == latest_ids.c.id).options(selectinload(CandidateEvaluation.scores)).all()
    criteria = {c.id: c for c in method.criteria if confidential or not candidate_sources.confidential(c)}
    score_maps = {e.employee_id: {criteria[s.criterion_id].position: float(s.points) for s in e.scores if s.criterion_id in criteria} for e in evaluations}
    return {'total': total, 'methodology': service.method_dict(method, include_confidential=confidential),
            'items': [{'id': e.id, 'full_name': e.full_name, 'personal_number': e.personnel_number,
                       'anonymous_code': e.anonymous_code,
                       'org_unit': {'name_ru': e.current_org_unit.name_ru, 'name_kk': e.current_org_unit.name_kk} if e.current_org_unit else None,
                       'scores': score_maps.get(e.id, {}), 'summary': summaries[e.id]} for e in employees]}
