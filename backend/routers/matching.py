from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from models import (
    MatchingRun, MatchingResult, Decision, Vacancy, ScoringModel, AuditLog,
)
from schemas import MatchingRunIn, MatchingRunOut, DecisionIn, DecisionOut
from services.scoring import run_matching

router = APIRouter(prefix="/api/v1", tags=["matching"])


@router.post("/matching-runs", response_model=MatchingRunOut, status_code=201)
def create_run(payload: MatchingRunIn, db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == payload.vacancy_id).first()
    if not vacancy:
        raise HTTPException(404, "Vacancy not found")
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
        created_by="hr_analyst",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_matching(db, run.id, payload.employee_ids, payload.verified_only)
    db.refresh(run)

    db.add(AuditLog(action="matching_run", entity_type="vacancy", entity_id=vacancy.id,
                    new_values={"run_id": run.id, "model": model.version},
                    changed_by="hr_analyst"))
    db.commit()
    db.refresh(run)
    return run


@router.get("/matching-runs/{run_id}", response_model=MatchingRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(MatchingRun).filter(MatchingRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/vacancies/{vacancy_id}/matching-runs")
def runs_for_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    rows = (db.query(MatchingRun)
            .filter(MatchingRun.vacancy_id == vacancy_id)
            .order_by(MatchingRun.created_at.desc()).all())
    return {"data": [MatchingRunOut.model_validate(r) for r in rows]}


@router.get("/matching-runs/{run_id}/results")
def get_results(run_id: int,
                reveal_names: bool = Query(False,
                    description="Pseudonyms are shown by default; revealing "
                                "identities is a deliberate, audited action."),
                db: Session = Depends(get_db)):
    run = db.query(MatchingRun).filter(MatchingRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    if reveal_names:
        db.add(AuditLog(action="reveal_identities", entity_type="matching_run",
                        entity_id=run_id, changed_by="hr_analyst"))
        db.commit()

    results = (db.query(MatchingResult)
               .filter(MatchingResult.run_id == run_id)
               .order_by(MatchingResult.system_rank).all())

    data = []
    for row in results:
        employee = row.employee
        decision = row.decision
        data.append({
            "id": row.id,
            "system_rank": row.system_rank,
            "employee_id": row.employee_id,
            "anonymous_code": employee.anonymous_code if employee else None,
            "display_name": (employee.full_name if (reveal_names and employee)
                             else (employee.anonymous_code if employee else "?")),
            "score": float(row.score),
            "readiness_code": row.readiness_code,
            "is_qualified": row.is_qualified,
            "explanation": row.explanation,
            "decision": ({
                "decision": decision.decision,
                "final_rank": decision.final_rank,
                "reason": decision.reason,
                "decided_by": decision.decided_by,
            } if decision else None),
        })

    return {
        "run_id": run_id,
        "status": run.status,
        "scoring_model": run.scoring_model.version if run.scoring_model else None,
        "requirements_version": run.requirements_version,
        "total_evaluated": run.total_evaluated,
        "total_qualified": run.total_qualified,
        "names_revealed": reveal_names,
        "shortlist": [d for d in data if d["is_qualified"]],
        "potential_after_development": [d for d in data if not d["is_qualified"]],
    }


@router.post("/matching-results/{result_id}/decision",
             response_model=DecisionOut, status_code=201)
def record_decision(result_id: int, payload: DecisionIn,
                    db: Session = Depends(get_db)):
    """System ranking is immutable. The human decision sits beside it, and a
    divergence demands a written reason."""
    result = db.query(MatchingResult).filter(MatchingResult.id == result_id).first()
    if not result:
        raise HTTPException(404, "Result not found")

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

    existing = db.query(Decision).filter(Decision.result_id == result_id).first()
    if existing:
        before = {"decision": existing.decision, "final_rank": existing.final_rank,
                  "reason": existing.reason}
        existing.decision = payload.decision
        existing.final_rank = payload.final_rank
        existing.reason = payload.reason
        existing.decided_by = payload.decided_by
        db.commit()
        db.refresh(existing)
        db.add(AuditLog(action="update_decision", entity_type="matching_result",
                        entity_id=result_id, old_values=before,
                        new_values=payload.model_dump(), reason=payload.reason,
                        changed_by=payload.decided_by))
        db.commit()
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
    db.commit()
    db.refresh(decision)

    db.add(AuditLog(action="decision", entity_type="matching_result",
                    entity_id=result_id, new_values=payload.model_dump(),
                    reason=payload.reason, changed_by=payload.decided_by))
    db.commit()
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
