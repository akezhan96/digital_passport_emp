from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload, defer
from typing import Optional
from datetime import datetime

from database import get_db
from models import (
    MatchingRun, MatchingResult, Decision, Vacancy, ScoringModel, AuditLog, Employee,
)
from schemas import MatchingRunIn, MatchingRunOut, DecisionIn, DecisionOut
from services.scoring import run_matching
from services.candidate_matching import run_candidate_matching, settings_snapshot
from services.candidate_methodology import get_method

router = APIRouter(prefix="/api/v1", tags=["matching"])

def _actor(request: Request) -> str:
    """Whoever is signed in, for the change history."""
    return (getattr(request.state, "user", {}) or {}).get("sub", "unknown")



def _admin(request):
    return bool(request and (getattr(request.state, 'user', {}) or {}).get('role') == 'admin')


def _allow_run(run, request):
    if run.include_confidential and not _admin(request):
        raise HTTPException(403, 'Подбор содержит закрытые оценки / Іріктеуде жабық бағалар бар')


@router.post("/matching-runs", response_model=MatchingRunOut, status_code=201)
def create_run(payload: MatchingRunIn, request: Request,
               db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == payload.vacancy_id).first()
    if not vacancy:
        raise HTTPException(404, "Vacancy not found")
    if vacancy.status == 'closed':
        raise HTTPException(422, 'Вакансия закрыта / Бос орын жабылған')
    if vacancy.candidate_methodology_id:
        if payload.scoring_model_id is not None:
            raise HTTPException(422, 'Эта вакансия использует методику личного дела / Бұл бос орын жеке іс әдістемесін қолданады')
        method = get_method(db, vacancy.candidate_methodology_id)
        if method.status not in ('active', 'archived'):
            raise HTTPException(422, 'Методика не опубликована / Әдістеме жарияланбаған')
        run = MatchingRun(vacancy_id=vacancy.id, candidate_methodology_id=method.id,
            requirements_version=vacancy.requirements_version or 1, status='processing',
            created_by=_actor(request), include_confidential=_admin(request),
            methodology_snapshot=settings_snapshot(vacancy,method,_admin(request)))
        db.add(run); db.commit(); db.refresh(run)
        run_candidate_matching(db,run.id,payload.employee_ids,payload.verified_only)
        db.add(AuditLog(action='matching_run',entity_type='vacancy',entity_id=vacancy.id,
            new_values={'run_id':run.id,'methodology_id':method.id,'version':method.version},changed_by=_actor(request)))
        db.commit(); db.refresh(run)
        return run
    if not vacancy.requirements:
        raise HTTPException(422, "This vacancy has no requirements defined")

    total_weight = sum(r.weight for r in vacancy.requirements)
    if total_weight != 100:
        raise HTTPException(422, {
            "message": "Requirement weights must total exactly 100 before matching",
            "current_total": total_weight,
        })

    if payload.scoring_model_id:
        model = db.query(ScoringModel).filter(
            ScoringModel.id == payload.scoring_model_id
        ).first()
    else:
        model = db.query(ScoringModel).filter(ScoringModel.is_default.is_(True)).first()
    if not model:
        raise HTTPException(422, "No scoring model available. Approve one first.")

    run = MatchingRun(
        vacancy_id=vacancy.id,
        scoring_model_id=model.id,
        requirements_version=vacancy.requirements_version or 1,
        status="processing",
        created_by=_actor(request),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_matching(db, run.id, payload.employee_ids, payload.verified_only)
    db.refresh(run)

    db.add(AuditLog(action="matching_run", entity_type="vacancy", entity_id=vacancy.id,
                    new_values={"run_id": run.id, "model": model.version},
                    changed_by=_actor(request)))
    db.commit()
    db.refresh(run)
    return run


@router.get("/matching-runs")
def list_runs(q: str = Query("", max_length=200), vacancy_id: Optional[int] = None,
              status: Optional[str] = None, offset: int = Query(0, ge=0),
              limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), request: Request = None):
    query = db.query(MatchingRun).join(Vacancy)
    if not _admin(request): query = query.filter(MatchingRun.include_confidential.is_(False))
    if vacancy_id is not None:
        query = query.filter(MatchingRun.vacancy_id == vacancy_id)
    if status:
        if status not in ("processing", "completed", "error"):
            raise HTTPException(422, "Некорректный статус / Қате мәртебе")
        query = query.filter(MatchingRun.status == status)
    for word in q.strip().split():
        pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(Vacancy.title.ilike(pattern, escape="\\"), Vacancy.title_kk.ilike(pattern, escape="\\")))
    total = query.count()
    rows = (query.options(selectinload(MatchingRun.vacancy), selectinload(MatchingRun.scoring_model))
            .order_by(MatchingRun.created_at.desc(), MatchingRun.id.desc())
            .offset(offset).limit(limit).all())
    return {"total": total, "offset": offset, "limit": limit, "data": [{
        "id": row.id, "vacancy_id": row.vacancy_id,
        "vacancy_title": row.vacancy.title if row.vacancy else "—",
        "vacancy_title_kk": row.vacancy.title_kk if row.vacancy else None,
        "candidate_methodology_id": row.candidate_methodology_id,
        "include_confidential": row.include_confidential,
        "created_at": row.created_at.isoformat(), "status": row.status,
        "total_evaluated": row.total_evaluated, "total_qualified": row.total_qualified,
        "scoring_model": row.scoring_model.version if row.scoring_model else None,
    } for row in rows]}


@router.get("/matching-runs/{run_id}", response_model=MatchingRunOut)
def get_run(run_id: int, db: Session = Depends(get_db), request: Request = None):
    run = db.query(MatchingRun).filter(MatchingRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    _allow_run(run,request)
    return run


@router.get("/vacancies/{vacancy_id}/matching-runs")
def runs_for_vacancy(vacancy_id: int, db: Session = Depends(get_db),
                     offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), request: Request = None):
    query = db.query(MatchingRun).filter(MatchingRun.vacancy_id == vacancy_id)
    if not _admin(request): query = query.filter(MatchingRun.include_confidential.is_(False))
    total = query.count()
    rows = query.order_by(MatchingRun.created_at.desc(), MatchingRun.id.desc()).offset(offset).limit(limit).all()
    return {"data": [MatchingRunOut.model_validate(r) for r in rows], "total": total, "offset": offset, "limit": limit}


def _result_row(row, reveal_names=False, include_details=True, methodology_summary=None):
    employee, decision = row.employee, row.decision
    data = {
        "id": row.id, "system_rank": row.system_rank, "employee_id": row.employee_id,
        "anonymous_code": employee.anonymous_code if employee else None,
        "display_name": (employee.full_name if reveal_names and employee
                         else (employee.anonymous_code if employee else "?")),
        "score": float(row.score), "readiness_code": row.readiness_code,
        "is_qualified": row.is_qualified,
        "decision": ({"decision": decision.decision, "final_rank": decision.final_rank,
                      "decided_at": decision.decided_at.isoformat() if decision.decided_at else None}
                     if decision else None),
    }
    if include_details:
        data["explanation"] = row.explanation or {}
        methodology_summary = data['explanation'].get('methodology_summary')
        if decision:
            data["decision"].update(reason=decision.reason, decided_by=decision.decided_by)
    if methodology_summary is not None:
        data['methodology_summary'] = methodology_summary
    return data


@router.get("/matching-runs/{run_id}/results")
def get_results(run_id: int,
                reveal_names: bool = Query(False,
                    description="Pseudonyms are shown by default; revealing "
                                "identities is a deliberate, audited action."),
                request: Request = None,
                db: Session = Depends(get_db),
                paged: bool = Query(False), offset: int = Query(0, ge=0),
                limit: int = Query(20, ge=1, le=100), q: str = Query("", max_length=200),
                qualified: Optional[bool] = None, decision: Optional[str] = None):
    run = db.query(MatchingRun).filter(MatchingRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    _allow_run(run,request)

    if reveal_names:
        db.add(AuditLog(action="reveal_identities", entity_type="matching_run",
                        entity_id=run_id, changed_by=_actor(request)))
        db.commit()

    query = db.query(MatchingResult).filter(MatchingResult.run_id == run_id)
    if qualified is not None:
        query = query.filter(MatchingResult.is_qualified.is_(qualified))
    if decision:
        if decision not in ("selected", "rejected", "on_hold", "reserve", "none"):
            raise HTTPException(422, "Некорректное решение / Қате шешім")
        query = query.filter(~MatchingResult.decision.has() if decision == "none"
                             else MatchingResult.decision.has(Decision.decision == decision))
    if q.strip():
        query = query.join(Employee)
        columns = [Employee.anonymous_code]
        # A name search would reveal identities even if their labels were hidden.
        if reveal_names:
            columns += [Employee.last_name, Employee.first_name, Employee.middle_name, Employee.personnel_number]
        for word in q.strip().split():
            pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.filter(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    total = query.with_entities(MatchingResult.id).count()
    query = query.options(selectinload(MatchingResult.employee).load_only(
        Employee.id, Employee.anonymous_code, Employee.first_name, Employee.last_name, Employee.middle_name),
        selectinload(MatchingResult.decision))
    if paged:
        query = query.options(defer(MatchingResult.explanation), defer(MatchingResult.candidate_snapshot))
    query = query.order_by(MatchingResult.system_rank, MatchingResult.id)
    if paged:
        query = query.offset(offset).limit(limit)
    if paged and run.candidate_methodology_id:
        # Fetch only the small saved total, not every indicator explanation and
        # dossier snapshot; the paginated list must not add a query per row.
        query = query.add_columns(MatchingResult.explanation['methodology_summary'].label('summary'))
        data = [_result_row(row, reveal_names, False, summary) for row, summary in query.all()]
    else:
        data = [_result_row(row, reveal_names, not paged) for row in query.all()]
    response = {
        "run_id": run_id,
        "status": run.status,
        "scoring_model": run.scoring_model.version if run.scoring_model else None,
        "requirements_version": run.requirements_version,
        "candidate_methodology_id": run.candidate_methodology_id,
        "methodology_snapshot": run.methodology_snapshot,
        "include_confidential": run.include_confidential,
        "total_evaluated": run.total_evaluated,
        "total_qualified": run.total_qualified,
        "names_revealed": reveal_names,
    }
    if paged:
        return {**response, "data": data, "total": total, "offset": offset, "limit": limit}
    return {**response, "shortlist": [d for d in data if d["is_qualified"]],
            "potential_after_development": [d for d in data if not d["is_qualified"]]}


@router.get("/matching-results/{result_id}")
def result_detail(result_id: int, request: Request,
                  reveal_names: bool = Query(False), db: Session = Depends(get_db)):
    row = (db.query(MatchingResult).options(selectinload(MatchingResult.employee),
           selectinload(MatchingResult.decision)).filter(MatchingResult.id == result_id).first())
    if not row:
        raise HTTPException(404, "Результат не найден / Нәтиже табылмады")
    _allow_run(row.run,request)
    if reveal_names:
        db.add(AuditLog(action="reveal_identities", entity_type="matching_result",
                        entity_id=result_id, changed_by=_actor(request)))
        db.commit()
    data = _result_row(row, reveal_names)
    vacancy = row.run.vacancy
    from services.recruitment import appointment_state
    action_state, appointment = appointment_state(db, row, is_admin=_admin(request))
    data.update(run_id=row.run_id, vacancy_id=vacancy.id,
                vacancy_title=vacancy.title, vacancy_title_kk=vacancy.title_kk,
                vacancy_status=vacancy.status, vacancy_org_unit_id=vacancy.org_unit_id,
                action_state=action_state, appointment=appointment)
    if row.run.candidate_methodology_id:
        data['methodology_summary'] = (row.explanation or {}).get('methodology_summary')
        data['methodology_snapshot'] = row.run.methodology_snapshot
        data['candidate_snapshot'] = row.candidate_snapshot or {}
        if _admin(request) and data['candidate_snapshot'].get('evaluation_id'):
            from models import CandidateEvaluation
            from services.candidate_sources import evaluation_source_state
            data['source_state'] = evaluation_source_state(db,row.employee,db.get(CandidateEvaluation,data['candidate_snapshot']['evaluation_id']))
        return data
    from services.candidate_methodology import candidate_summaries
    include_confidential = (getattr(request.state, "user", {}) or {}).get("role") == "admin"
    try:
        data["methodology_summary"] = candidate_summaries(db, [row.employee_id],
            include_confidential=include_confidential).get(row.employee_id)
    except HTTPException as error:
        # A saved vacancy calculation remains readable while a new assessment
        # methodology has not yet been activated.
        if error.status_code != 404:
            raise
        data["methodology_summary"] = None
    return data


@router.post("/matching-results/{result_id}/decision",
             response_model=DecisionOut, status_code=201)
def record_decision(result_id: int, payload: DecisionIn,
                    db: Session = Depends(get_db), request: Request = None):
    """System ranking is immutable. The human decision sits beside it, and a
    divergence demands a written reason."""
    result = db.query(MatchingResult).filter(MatchingResult.id == result_id).first()
    if not result:
        raise HTTPException(404, "Result not found")
    _allow_run(result.run,request)
    # Serialize decisions with appointment creation for this person. This also
    # makes selecting from another calculation and appointing mutually ordered.
    db.query(Employee).filter_by(id=result.employee_id).with_for_update().first()
    if request: payload = payload.model_copy(update={"decided_by":_actor(request)})

    diverges = (payload.final_rank is not None
                and payload.final_rank != result.system_rank)
    if diverges and not (payload.reason or "").strip():
        raise HTTPException(422, {
            "message": "A reason is mandatory when the final rank differs "
                       "from the system rank",
            "system_rank": result.system_rank,
            "requested_rank": payload.final_rank,
        })
    if payload.decision not in ("selected", "rejected", "on_hold", "reserve"):
        raise HTTPException(422, "decision must be selected, rejected, on_hold or reserve")
    if payload.decision == 'selected' and not result.is_qualified and not (payload.reason or '').strip():
        raise HTTPException(422, 'Укажите основание выбора кандидата, которому требуется проверка / Тексеруді қажет ететін үміткерді таңдау негізін көрсетіңіз')

    existing = db.query(Decision).filter(Decision.result_id == result_id).first()
    if existing:
        before = {"decision": existing.decision, "final_rank": existing.final_rank,
                  "reason": existing.reason}
        existing.decision = payload.decision
        existing.final_rank = payload.final_rank
        existing.reason = payload.reason
        existing.decided_by = payload.decided_by
        existing.decided_at = datetime.utcnow()
        db.add(AuditLog(action="update_decision", entity_type="matching_result",
                        entity_id=result_id, old_values=before,
                        new_values=payload.model_dump(), reason=payload.reason,
                        changed_by=payload.decided_by))
        db.commit()
        db.refresh(existing)
        return existing

    decision = Decision(
        result_id=result_id,
        system_rank=result.system_rank,
        final_rank=payload.final_rank,
        decision=payload.decision,
        reason=payload.reason,
        decided_by=payload.decided_by,
    )
    db.add(decision)
    db.add(AuditLog(action="decision", entity_type="matching_result",
                    entity_id=result_id, new_values=payload.model_dump(),
                    reason=payload.reason, changed_by=payload.decided_by))
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/audit-log")
def audit_log(entity_type: Optional[str] = None, limit: int = Query(100, le=500),
              db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    rows = query.order_by(AuditLog.changed_at.desc()).limit(limit).all()
    return {"data": [{
        "id": r.id,
        "action": r.action,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "old_values": r.old_values,
        "new_values": r.new_values,
        "reason": r.reason,
        "changed_by": r.changed_by,
        "changed_at": r.changed_at.isoformat() if r.changed_at else None,
    } for r in rows]}
