from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import date

from database import get_db
from models import (
    Employee, EmployeeEducation, EmployeeLanguage, EmployeeTraining,
    WorkExperience, AssessmentSession, CompetencyScore,
    LanguageLevel, LanguageScale, AuditLog, Competency,
)
from schemas import (
    EmployeeIn, EmployeeUpdate, EmployeeOut, EmployeeDetail,
    EducationIn, EducationOut, LanguageIn, LanguageOut,
    TrainingIn, TrainingOut, WorkExperienceIn, WorkExperienceOut,
    AssessmentSessionIn, AssessmentSessionOut,
)
from services.metrics import persist_employee_metrics, compute_employee_metrics

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


def _next_anonymous_code(db: Session) -> str:
    count = db.query(Employee).count()
    return f"E-{count + 1:05d}"


def _get(db: Session, employee_id: int) -> Employee:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")
    return employee


# ---------------------------------------------------------------------------
# Employee core
# ---------------------------------------------------------------------------

@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(payload: EmployeeIn, db: Session = Depends(get_db)):
    # Duplicate protection, as required by the specification.
    if payload.personnel_number:
        clash = db.query(Employee).filter(
            Employee.personnel_number == payload.personnel_number
        ).first()
        if clash:
            raise HTTPException(409, {
                "message": "An employee with this personnel number already exists",
                "existing_id": clash.id,
                "existing_name": clash.full_name,
            })

    if payload.birth_date:
        probable = db.query(Employee).filter(
            Employee.last_name == payload.last_name,
            Employee.first_name == payload.first_name,
            Employee.birth_date == payload.birth_date,
        ).first()
        if probable:
            raise HTTPException(409, {
                "message": "A person with the same name and date of birth already exists",
                "existing_id": probable.id,
                "existing_name": probable.full_name,
            })

    employee = Employee(**payload.model_dump())
    employee.anonymous_code = _next_anonymous_code(db)
    employee.profile_status = "draft"
    db.add(employee)
    db.commit()
    db.refresh(employee)

    db.add(AuditLog(action="create", entity_type="employee", entity_id=employee.id,
                    new_values={"name": employee.full_name}, changed_by="hr"))
    db.commit()
    return employee


@router.get("")
def list_employees(
    search: Optional[str] = None,
    profile_status: Optional[str] = None,
    org_unit_id: Optional[int] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Employee)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(
            Employee.last_name.ilike(pattern),
            Employee.first_name.ilike(pattern),
            Employee.personnel_number.ilike(pattern),
            Employee.email.ilike(pattern),
        ))
    if profile_status:
        query = query.filter(Employee.profile_status == profile_status)
    if org_unit_id:
        query = query.filter(Employee.current_org_unit_id == org_unit_id)

    total = query.count()
    rows = query.order_by(Employee.last_name).limit(limit).offset(offset).all()

    return {
        "total": total,
        "data": [{
            "id": e.id,
            "anonymous_code": e.anonymous_code,
            "personnel_number": e.personnel_number,
            "full_name": e.full_name,
            "last_name": e.last_name,
            "first_name": e.first_name,
            "middle_name": e.middle_name,
            "profile_status": e.profile_status,
            "employment_status": e.employment_status,
            "current_position_id": e.current_position_id,
            "current_org_unit_id": e.current_org_unit_id,
            "position_name_ru": e.current_position.name_ru if e.current_position else None,
            "org_unit_name_ru": e.current_org_unit.name_ru if e.current_org_unit else None,
            "completeness": profile_completeness(e)["percent"],
        } for e in rows],
    }


def profile_completeness(employee: Employee) -> dict:
    """Percentage of filled sections -- data completeness, not employee quality."""
    sections = {
        "general": bool(employee.last_name and employee.first_name
                        and employee.birth_date and employee.hire_date),
        "education": len(employee.educations) > 0,
        "languages": len(employee.languages) > 0,
        "training": len(employee.trainings) > 0,
        "career": len(employee.work_experience) > 0,
        "assessment": any(s.session_type == "professional"
                          for s in employee.assessment_sessions),
    }
    filled = sum(1 for ok in sections.values() if ok)
    warnings = []

    for lang in employee.languages:
        if not lang.is_confirmed:
            warnings.append(f"Language not confirmed: "
                            f"{lang.language.name_ru if lang.language else '?'}")
        elif lang.valid_until and lang.valid_until < date.today():
            warnings.append(f"Language certificate expired: "
                            f"{lang.language.name_ru if lang.language else '?'}")

    professional = [s for s in employee.assessment_sessions
                    if s.session_type == "professional"]
    if professional:
        newest = max(s.session_date for s in professional)
        if (date.today() - newest).days > 730:
            warnings.append("Professional assessment is older than two years")

    return {
        "percent": round(filled / len(sections) * 100),
        "sections": sections,
        "warnings": warnings,
    }


@router.get("/{employee_id}", response_model=EmployeeDetail)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    return _get(db, employee_id)


@router.get("/{employee_id}/summary")
def employee_summary(employee_id: int, db: Session = Depends(get_db)):
    """Everything the profile card shows, including derived figures."""
    employee = _get(db, employee_id)
    metrics = compute_employee_metrics(db, employee)
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "anonymous_code": employee.anonymous_code,
        "profile_status": employee.profile_status,
        "completeness": profile_completeness(employee),
        "metrics": metrics,
    }


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, payload: EmployeeUpdate,
                    db: Session = Depends(get_db)):
    employee = _get(db, employee_id)
    changes = payload.model_dump(exclude_unset=True)
    before = {k: str(getattr(employee, k, None)) for k in changes}

    for key, value in changes.items():
        setattr(employee, key, value)
    db.commit()
    db.refresh(employee)

    db.add(AuditLog(action="update", entity_type="employee", entity_id=employee.id,
                    old_values=before,
                    new_values={k: str(v) for k, v in changes.items()},
                    changed_by="hr"))
    db.commit()
    persist_employee_metrics(db, employee)
    return employee


@router.post("/{employee_id}/verify", response_model=EmployeeOut)
def verify_employee(employee_id: int, verified_by: str = "hr_admin",
                    db: Session = Depends(get_db)):
    """Only verified profiles take part in matching."""
    employee = _get(db, employee_id)
    completeness = profile_completeness(employee)
    if not completeness["sections"]["career"]:
        raise HTTPException(422, "Cannot verify: career history is empty, "
                                 "so no experience can be calculated")

    employee.profile_status = "verified"
    employee.verified_at = __import__("datetime").datetime.utcnow()
    employee.verified_by = verified_by
    db.commit()
    db.refresh(employee)

    db.add(AuditLog(action="verify", entity_type="employee", entity_id=employee.id,
                    new_values={"profile_status": "verified"}, changed_by=verified_by))
    db.commit()
    persist_employee_metrics(db, employee)
    return employee


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/education", response_model=EducationOut, status_code=201)
def add_education(employee_id: int, payload: EducationIn, db: Session = Depends(get_db)):
    employee = _get(db, employee_id)

    if payload.start_year and payload.end_year and payload.end_year < payload.start_year:
        raise HTTPException(422, "Graduation year cannot precede the start year")
    if employee.birth_date and payload.end_year:
        if payload.end_year < employee.birth_date.year + 15:
            raise HTTPException(422, "Check the graduation year: it is implausibly "
                                     "close to the date of birth")

    row = EmployeeEducation(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/education/{row_id}", status_code=204)
def delete_education(row_id: int, db: Session = Depends(get_db)):
    row = db.query(EmployeeEducation).filter(EmployeeEducation.id == row_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Languages  --  with the CEFR guard from the specification
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/languages", response_model=LanguageOut, status_code=201)
def add_language(employee_id: int, payload: LanguageIn, db: Session = Depends(get_db)):
    _get(db, employee_id)

    scale = db.query(LanguageScale).filter(LanguageScale.id == payload.scale_id).first()
    if not scale:
        raise HTTPException(422, "Unknown language scale")

    level = db.query(LanguageLevel).filter(LanguageLevel.id == payload.level_id).first()
    if not level:
        raise HTTPException(422, "Unknown language level")

    # The level must belong to the chosen scale. This is what rejects "B3"
    # for CEFR: no such row exists for that scale.
    if level.scale_id != scale.id:
        valid = [l.code for l in db.query(LanguageLevel)
                 .filter(LanguageLevel.scale_id == scale.id)
                 .order_by(LanguageLevel.rank).all()]
        raise HTTPException(422, {
            "message": f"Level '{level.code}' does not exist in the {scale.code} scale.",
            "valid_levels": valid,
            "hint": f"Choose one of {', '.join(valid)} or change the scale.",
        })

    if payload.is_confirmed and not payload.confirmed_at:
        raise HTTPException(422, "A confirmed language needs a confirmation date")

    row = EmployeeLanguage(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/languages/{row_id}", status_code=204)
def delete_language(row_id: int, db: Session = Depends(get_db)):
    row = db.query(EmployeeLanguage).filter(EmployeeLanguage.id == row_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/training", response_model=TrainingOut, status_code=201)
def add_training(employee_id: int, payload: TrainingIn, db: Session = Depends(get_db)):
    _get(db, employee_id)
    if payload.date_from and payload.date_to and payload.date_to < payload.date_from:
        raise HTTPException(422, "End date cannot precede the start date")
    row = EmployeeTraining(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/training/{row_id}", status_code=204)
def delete_training(row_id: int, db: Session = Depends(get_db)):
    row = db.query(EmployeeTraining).filter(EmployeeTraining.id == row_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Career history  --  the source of every tenure figure
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/work-experience",
             response_model=WorkExperienceOut, status_code=201)
def add_work_experience(employee_id: int, payload: WorkExperienceIn,
                        db: Session = Depends(get_db)):
    employee = _get(db, employee_id)

    if payload.date_to and payload.date_to < payload.date_from:
        raise HTTPException(422, "End date cannot precede the start date")

    # Overlap warning, as the specification asks (advisory, not blocking).
    overlaps = []
    new_end = payload.date_to or date.today()
    for row in employee.work_experience:
        existing_end = row.date_to or date.today()
        if payload.date_from <= existing_end and row.date_from <= new_end:
            overlaps.append({"from": str(row.date_from), "to": str(row.date_to or "")})

    row = WorkExperience(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)

    persist_employee_metrics(db, employee)

    if overlaps:
        # Saved, but the client is told so it can surface a warning.
        row_out = WorkExperienceOut.model_validate(row).model_dump()
        row_out["_warning"] = {"overlapping_periods": overlaps}
        return row_out
    return row


@router.delete("/work-experience/{row_id}", status_code=204)
def delete_work_experience(row_id: int, db: Session = Depends(get_db)):
    row = db.query(WorkExperience).filter(WorkExperience.id == row_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    employee = row.employee
    db.delete(row)
    db.commit()
    if employee:
        persist_employee_metrics(db, employee)


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

@router.post("/{employee_id}/assessments",
             response_model=AssessmentSessionOut, status_code=201)
def add_assessment(employee_id: int, payload: AssessmentSessionIn,
                   db: Session = Depends(get_db)):
    employee = _get(db, employee_id)

    session = AssessmentSession(
        employee_id=employee_id,
        session_type=payload.session_type,
        scale_id=payload.scale_id,
        session_date=payload.session_date,
        assessor=payload.assessor,
        conclusion_text=payload.conclusion_text,
        valid_until=payload.valid_until,
    )
    db.add(session)
    db.flush()

    for score in payload.scores:
        competency = db.query(Competency).filter(
            Competency.id == score.competency_id
        ).first()
        if not competency:
            raise HTTPException(422, f"Unknown competency id {score.competency_id}")
        db.add(CompetencyScore(session_id=session.id,
                               competency_id=score.competency_id,
                               score=score.score))

    db.commit()
    db.refresh(session)
    persist_employee_metrics(db, employee)
    return session


@router.get("/{employee_id}/assessments", response_model=List[AssessmentSessionOut])
def list_assessments(employee_id: int, db: Session = Depends(get_db)):
    _get(db, employee_id)
    return (db.query(AssessmentSession)
            .filter(AssessmentSession.employee_id == employee_id)
            .order_by(AssessmentSession.session_date.desc()).all())


@router.get("/{employee_id}/competency-history")
def competency_history(employee_id: int, db: Session = Depends(get_db)):
    """Development over time -- 2024 leadership 3.8 -> 2026 4.4."""
    _get(db, employee_id)
    sessions = (db.query(AssessmentSession)
                .filter(AssessmentSession.employee_id == employee_id)
                .order_by(AssessmentSession.session_date).all())
    history: dict = {}
    for session in sessions:
        for score in session.scores:
            code = score.competency.code
            history.setdefault(code, {
                "competency_code": code,
                "name_ru": score.competency.name_ru,
                "name_kk": score.competency.name_kk,
                "name_en": score.competency.name_en,
                "points": [],
            })
            history[code]["points"].append({
                "date": str(session.session_date),
                "score": float(score.score),
                "scale_max": float(session.scale.max_value) if session.scale else None,
            })
    return {"data": list(history.values())}
