from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, object_session
from sqlalchemy import or_, and_, select
from typing import Annotated, List, Literal, Optional
from datetime import date, datetime

from database import get_db
from models import (
    Employee, EmployeeEducation, EmployeeLanguage, EmployeeTraining,
    WorkExperience, AssessmentSession, CompetencyScore,
    LanguageLevel, LanguageScale, AuditLog, Competency, OrgUnit, Position,
    CandidateEvaluation, CandidateScore, CandidateCriterion, DisposalPeriod,
)
from schemas import (
    EmployeeIn, EmployeeUpdate, EmployeeOut, EmployeeDetail, EmployeeCareerDetail,
    EducationIn, EducationOut, LanguageIn, LanguageOut,
    TrainingIn, TrainingOut, WorkExperienceIn, WorkExperienceOut,
    AssessmentSessionIn, AssessmentSessionOut,
)
from services.career import (career_metadata, appointment_events, official_period, protected_period_ids,
                             lock_employee, overlaps_disposal, close_disposal_on_exit)
from services.metrics import (persist_employee_metrics, compute_employee_metrics,
                             reconcile_current_post)

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])

def _actor(request: Request) -> str:
    """Whoever is signed in, for the change history."""
    return (getattr(request.state, "user", {}) or {}).get("sub", "unknown")



def _next_anonymous_code(db: Session) -> str:
    from uuid import uuid4
    return f"E-{uuid4().hex[:16].upper()}"


def _get(db: Session, employee_id: int) -> Employee:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")
    return employee


def _locked_employee(db, employee_id):
    employee = lock_employee(db, employee_id)
    if not employee:
        raise HTTPException(404, "Сотрудник не найден / Қызметкер табылмады")
    return employee


# ---------------------------------------------------------------------------
# Employee core
# ---------------------------------------------------------------------------

@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(payload: EmployeeIn, request: Request,
                    db: Session = Depends(get_db)):
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
                    new_values={"name": employee.full_name}, changed_by=_actor(request)))
    db.commit()
    return employee


def _candidate_assessment_present():
    # Shared profile completeness must never disclose psychological scores or
    # even become dependent on whether a private-only score was entered.
    return Employee.candidate_evaluations.any(CandidateEvaluation.scores.any(
        CandidateScore.criterion.has(CandidateCriterion.block == "general")))


@router.get("")
def list_employees(
    search: Annotated[Optional[str], Query(max_length=200)] = None,
    profile_status: Optional[Literal["draft", "in_review", "verified", "archived"]] = None,
    org_unit_id: Optional[int] = None,
    position_id: Optional[int] = None,
    birth_year: Annotated[Optional[int], Query(ge=1900, le=9998)] = None,
    language_id: Optional[int] = None,
    language_min_rank: Annotated[Optional[int], Query(ge=1, le=100)] = None,
    education_country_id: Optional[int] = None,
    include_subunits: bool = False,
    sort_by: Literal["name", "personnel_number", "org_unit", "position", "birth_date"] = "name",
    sort_direction: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
):
    """A bounded directory page, never a population of complete personal files.

    EXISTS filters avoid duplicates when someone has several qualifications.
    Completeness uses the same six section-presence rules as the profile card,
    without loading education documents, career records or assessment contents.
    """
    if language_min_rank is not None and language_id is None:
        raise HTTPException(422, "Выберите язык для фильтра уровня / Деңгейді сүзу үшін тілді таңдаңыз")
    query = (db.query(Employee)
             .outerjoin(Position, Employee.current_position_id == Position.id)
             .outerjoin(OrgUnit, Employee.current_org_unit_id == OrgUnit.id))
    for token in (search or "").split():
        # Treat %, _ and backslash as user text, not SQL wildcards.
        escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        matches = [column.ilike(pattern, escape="\\") for column in (
            Employee.last_name, Employee.first_name, Employee.middle_name,
            Employee.personnel_number, Employee.anonymous_code, Employee.email,
            OrgUnit.name_ru, OrgUnit.name_kk, Position.name_ru, Position.name_kk,
        )]
        if token.isascii() and token.isdigit() and len(token) <= 10:
            matches.append(Employee.id == int(token))
        query = query.filter(or_(*matches))
    if profile_status:
        query = query.filter(Employee.profile_status == profile_status)
    if org_unit_id is not None:
        if include_subunits:
            subtree = select(OrgUnit.id).where(OrgUnit.id == org_unit_id).cte("directory_subtree", recursive=True)
            # UNION deduplicates IDs and terminates even if legacy data has a cycle.
            subtree = subtree.union(select(OrgUnit.id).join(subtree, OrgUnit.parent_id == subtree.c.id))
            query = query.filter(Employee.current_org_unit_id.in_(select(subtree.c.id)))
        else:
            query = query.filter(Employee.current_org_unit_id == org_unit_id)
    if position_id is not None:
        query = query.filter(Employee.current_position_id == position_id)
    if birth_year is not None:
        query = query.filter(Employee.birth_date >= date(birth_year, 1, 1),
                             Employee.birth_date < date(birth_year + 1, 1, 1))
    if language_id is not None:
        language_condition = EmployeeLanguage.language_id == language_id
        if language_min_rank is not None:
            language_condition = and_(language_condition,
                EmployeeLanguage.level.has(LanguageLevel.rank >= language_min_rank))
        query = query.filter(Employee.languages.any(language_condition))
    if education_country_id is not None:
        query = query.filter(Employee.educations.any(EmployeeEducation.country_id == education_country_id))

    total = query.count()
    fields = (
        Employee.id, Employee.anonymous_code, Employee.personnel_number,
        Employee.last_name, Employee.first_name, Employee.middle_name,
        Employee.birth_date, Employee.profile_status, Employee.employment_status,
        Employee.current_position_id, Employee.current_org_unit_id,
        Position.name_ru.label("position_name_ru"), Position.name_kk.label("position_name_kk"),
        OrgUnit.name_ru.label("org_unit_name_ru"), OrgUnit.name_kk.label("org_unit_name_kk"),
        and_(Employee.last_name != "", Employee.first_name != "", Employee.birth_date.is_not(None),
             Employee.hire_date.is_not(None)).label("has_general"),
        Employee.educations.any().label("has_education"),
        Employee.languages.any().label("has_languages"),
        Employee.trainings.any().label("has_training"),
        Employee.work_experience.any().label("has_career"),
        or_(Employee.assessment_sessions.any(and_(AssessmentSession.session_type == "professional",
                                                  AssessmentSession.status == "confirmed")),
            _candidate_assessment_present()).label("has_assessment"),
    )
    sort_column = {"name": Employee.last_name, "personnel_number": Employee.personnel_number,
                   "org_unit": OrgUnit.name_ru, "position": Position.name_ru,
                   "birth_date": Employee.birth_date}[sort_by]
    order = sort_column.desc() if sort_direction == "desc" else sort_column.asc()
    rows = (query.with_entities(*fields).order_by(order.nullslast(), Employee.last_name,
                Employee.first_name, Employee.middle_name, Employee.id)
            .limit(limit).offset(offset).all())

    return {
        "total": total, "limit": limit, "offset": offset,
        "data": [{
            "id": e.id,
            "anonymous_code": e.anonymous_code,
            "personnel_number": e.personnel_number,
            "full_name": " ".join(part for part in (e.last_name, e.first_name, e.middle_name) if part),
            "last_name": e.last_name,
            "first_name": e.first_name,
            "middle_name": e.middle_name,
            "birth_year": e.birth_date.year if e.birth_date else None,
            "profile_status": e.profile_status,
            "employment_status": e.employment_status,
            "current_position_id": e.current_position_id,
            "current_org_unit_id": e.current_org_unit_id,
            "position_name_ru": e.position_name_ru,
            "position_name_kk": e.position_name_kk,
            "org_unit_name_ru": e.org_unit_name_ru,
            "org_unit_name_kk": e.org_unit_name_kk,
            "completeness": round(sum(bool(value) for value in (e.has_general, e.has_education,
                e.has_languages, e.has_training, e.has_career, e.has_assessment)) / 6 * 100),
        } for e in rows],
    }


def profile_completeness(employee: Employee) -> dict:
    """Percentage of filled sections -- data completeness, not employee quality."""
    professional = [session for session in employee.assessment_sessions
                    if session.session_type == "professional" and session.status == "confirmed"]
    assessment_present = bool(professional)
    session = object_session(employee)
    if not assessment_present and session is not None and employee.id is not None:
        assessment_present = bool(session.scalar(select(_candidate_assessment_present())
                                                  .where(Employee.id == employee.id)))
    sections = {
        "general": bool(employee.last_name and employee.first_name
                        and employee.birth_date and employee.hire_date),
        "education": len(employee.educations) > 0,
        "languages": len(employee.languages) > 0,
        "training": len(employee.trainings) > 0,
        "career": len(employee.work_experience) > 0,
        "assessment": assessment_present,
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

    if professional:
        newest = max(s.session_date for s in professional)
        if (date.today() - newest).days > 730:
            warnings.append("Professional assessment is older than two years")

    return {
        "percent": round(filled / len(sections) * 100),
        "sections": sections,
        "warnings": warnings,
    }


@router.get("/{employee_id}", response_model=EmployeeCareerDetail)
def get_employee(employee_id: int, request: Request, db: Session = Depends(get_db)):
    employee = _get(db, employee_id)
    body = EmployeeDetail.model_validate(employee)
    career = career_metadata(db, employee, is_admin=request.state.user.get("role") == "admin")
    if request.state.user.get("role") != "admin":
        body.assessment_sessions = [s for s in body.assessment_sessions if s.session_type == "professional"]
        for session in body.assessment_sessions:
            session.scores = [s for s in session.scores if s.competency_id not in {c.id for c in db.query(Competency).filter(Competency.is_confidential.is_(True)).all()}]
    data = body.model_dump(exclude={'work_experience'})
    data['active_disposal_since'] = (db.query(DisposalPeriod.date_from)
        .filter_by(employee_id=employee_id, date_to=None).scalar())
    data['work_experience'] = [{**row.model_dump(), **career[row.id]} for row in body.work_experience]
    return EmployeeCareerDetail.model_validate(data)


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
                    request: Request, db: Session = Depends(get_db)):
    employee = _locked_employee(db, employee_id)
    changes = payload.model_dump(exclude_unset=True)
    if (any(changes.get(key) is not None for key in ("current_position_id", "current_org_unit_id"))
            and overlaps_disposal(db, employee_id, date.today(), date.today())):
        raise HTTPException(409, "Для выхода из распоряжения оформите назначение / Қарамағынан шығу үшін тағайындауды рәсімдеңіз")
    before = {k: str(getattr(employee, k, None)) for k in changes}

    for key, value in changes.items():
        setattr(employee, key, value)
    if employee.employment_status != "active" or employee.profile_status == "archived":
        close_disposal_on_exit(db, employee)

    db.add(AuditLog(action="update", entity_type="employee", entity_id=employee.id,
                    old_values=before,
                    new_values={k: str(v) for k, v in changes.items()},
                    reason=request.query_params.get("reason"),
                    changed_by=(getattr(request.state, "user", {}) or {})
                    .get("sub", "hr")))
    persist_employee_metrics(db, employee, commit=False)
    db.commit()
    db.refresh(employee)
    return employee


@router.get("/{employee_id}/usage")
def employee_usage(employee_id: int, db: Session = Depends(get_db)):
    """What a deletion would take with it, and what stands in its way."""
    employee = _get(db, employee_id)

    from models import (MatchingResult, Decision, Attachment, CustomFieldValue, DossierSubsectionEntry,
                        EmployeePersonnelRecord, DisposalPeriod)

    results = db.query(MatchingResult).filter(
        MatchingResult.employee_id == employee_id).count()
    decisions = (db.query(Decision)
                 .join(MatchingResult, Decision.result_id == MatchingResult.id)
                 .filter(MatchingResult.employee_id == employee_id)
                 .count())
    attachments = db.query(Attachment).filter(
        Attachment.entity_type == "employee",
        Attachment.entity_id == employee_id).count()
    custom_values = db.query(CustomFieldValue).filter(
        CustomFieldValue.entity_type == "employee",
        CustomFieldValue.entity_id == employee_id).count()

    return {
        "id": employee_id,
        "full_name": employee.full_name,
        "profile_status": employee.profile_status,
        # Carried with the profile when it goes.
        "education": len(employee.educations),
        "languages": len(employee.languages),
        "training": len(employee.trainings),
        "career": len(employee.work_experience),
        "assessments": len(employee.assessment_sessions),
        "attachments": attachments,
        "custom_values": custom_values,
        "dossier_entries": db.query(DossierSubsectionEntry).filter_by(employee_id=employee_id).count(),
        "personnel_records": db.query(EmployeePersonnelRecord).filter_by(employee_id=employee_id).count(),
        "disposal_periods": db.query(DisposalPeriod).filter_by(employee_id=employee_id).count(),
        # What blocks removal.
        "matching_results": results,
        "decisions": decisions,
        "can_delete": results == 0 and decisions == 0,
    }


@router.delete("/{employee_id}", status_code=204)
def delete_employee(employee_id: int, request: Request,
                    db: Session = Depends(get_db)):
    """Remove a profile entered in error, with everything belonging to it.

    Refused once the person has been scored against a vacancy: that ranking is
    part of how a decision was justified, and a short-list pointing at a
    deleted candidate is worse than no short-list. Archive them instead.
    """
    employee = _get(db, employee_id)
    usage = employee_usage(employee_id, db)

    if not usage["can_delete"]:
        raise HTTPException(422, {
            "message": "Сотрудник участвовал в подборе и не может быть удалён",
            "matching_results": usage["matching_results"],
            "decisions": usage["decisions"],
            "hint": "Переведите профиль в архив — он перестанет участвовать "
                    "в подборе, но история решений останется целой.",
        })

    from models import Attachment, CustomFieldValue
    import os

    # Attachments and custom values are keyed generically, so no foreign key
    # removes them. Left behind they become orphans pointing at an id that a
    # later employee will eventually be given.
    files = db.query(Attachment).filter(
        Attachment.entity_type == "employee",
        Attachment.entity_id == employee_id).all()
    from routers.extensions import UPLOAD_ROOT
    files_to_remove = []
    for row in files:
        files_to_remove.append(os.path.join(UPLOAD_ROOT, row.entity_type, row.stored_name))
        db.delete(row)

    db.query(CustomFieldValue).filter(
        CustomFieldValue.entity_type == "employee",
        CustomFieldValue.entity_id == employee_id).delete(
            synchronize_session=False)

    snapshot = {
        "full_name": employee.full_name,
        "personnel_number": employee.personnel_number,
        "profile_status": employee.profile_status,
        "career_rows": usage["career"],
        "education_rows": usage["education"],
        "personnel_records": usage["personnel_records"],
        "disposal_periods": usage["disposal_periods"],
    }

    user = getattr(request.state, "user", {}) or {}
    db.add(AuditLog(action="delete", entity_type="employee",
                    entity_id=employee_id, old_values=snapshot,
                    reason=request.query_params.get("reason"),
                    changed_by=user.get("sub", "hr")))

    db.delete(employee)               # profile tables cascade
    db.commit()
    for path in files_to_remove:
        try:
            os.remove(path)
        except OSError:
            pass


@router.post("/{employee_id}/archive", response_model=EmployeeOut)
def archive_employee(employee_id: int, request: Request,
                     db: Session = Depends(get_db)):
    """Retire a profile without destroying it.

    The person stops appearing in the active workforce, in segments and in
    matching, but every ranking and decision that mentions them still resolves.
    """
    employee = _locked_employee(db, employee_id)
    before = {"profile_status": employee.profile_status,
              "employment_status": employee.employment_status}

    employee.profile_status = "archived"
    employee.employment_status = "terminated"
    close_disposal_on_exit(db, employee)

    user = getattr(request.state, "user", {}) or {}
    db.add(AuditLog(action="archive", entity_type="employee",
                    entity_id=employee_id, old_values=before,
                    new_values={"profile_status": "archived",
                                "employment_status": "terminated"},
                    reason=request.query_params.get("reason"),
                    changed_by=user.get("sub", "hr")))
    persist_employee_metrics(db, employee, commit=False)
    db.commit()
    return employee


@router.post("/{employee_id}/restore", response_model=EmployeeOut)
def restore_employee(employee_id: int, request: Request,
                     db: Session = Depends(get_db)):
    """Bring an archived profile back, as a draft pending re-verification."""
    employee = _get(db, employee_id)
    if employee.profile_status != "archived":
        raise HTTPException(422, "Профиль не находится в архиве")

    before = {"profile_status": employee.profile_status,
              "employment_status": employee.employment_status}

    # Deliberately not straight back to "verified": the facts may have moved on
    # while the profile was out of circulation, so it is checked again.
    employee.profile_status = "draft"
    employee.employment_status = "active"
    db.commit()
    db.refresh(employee)

    user = getattr(request.state, "user", {}) or {}
    db.add(AuditLog(action="restore", entity_type="employee",
                    entity_id=employee_id, old_values=before,
                    new_values={"profile_status": "draft",
                                "employment_status": "active"},
                    changed_by=user.get("sub", "hr")))
    db.commit()
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
    employee = _locked_employee(db, employee_id)

    if payload.date_to and payload.date_to < payload.date_from:
        raise HTTPException(422, "End date cannot precede the start date")
    if payload.is_internal and overlaps_disposal(db, employee_id, payload.date_from, payload.date_to):
        raise HTTPException(409, "Период работы пересекает распоряжение / Жұмыс кезеңі қарамағында болу кезеңімен қиылысады")

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


def _editable_period(db, row_id):
    owner = db.query(WorkExperience.employee_id).filter(WorkExperience.id == row_id).scalar()
    if owner is None:
        raise HTTPException(404, "Запись не найдена / Жазба табылмады")
    employee = (db.query(Employee).filter_by(id=owner).with_for_update().populate_existing().first())
    row = db.query(WorkExperience).filter_by(id=row_id, employee_id=owner).with_for_update().populate_existing().first()
    if not employee or not row:
        raise HTTPException(404, "Запись не найдена / Жазба табылмады")
    events = appointment_events(db, employee)
    if row.id in events and events[row.id] is None:
        raise HTTPException(409, "Исторические записи совпадают по дате и виду. Ручное изменение небезопасно / Тарихи жазбалардың күні мен түрі сәйкес келеді. Қолмен өзгерту қауіпті")
    if official_period(row, events.get(row.id)):
        raise HTTPException(409, "Эта запись оформлена как назначение. Для последнего назначения используйте отмену в карточке / Бұл жазба тағайындау ретінде рәсімделген. Соңғы тағайындауды карточкадан кері қайтарыңыз")
    return row, employee


@router.delete("/work-experience/{row_id}", status_code=204)
def delete_work_experience(row_id: int, db: Session = Depends(get_db)):
    row, employee = _editable_period(db, row_id)
    if protected_period_ids(db, [row_id]):
        raise HTTPException(409, "Сначала перенесите вложения и дополнительные данные периода / Алдымен кезеңнің тіркемелері мен қосымша деректерін көшіріңіз")
    db.delete(row)
    db.commit()
    if employee:
        # The timeline changed, so the denormalised "current post" may now be
        # pointing at a posting that no longer exists.
        reconcile_current_post(db, employee)
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
def list_assessments(employee_id: int, request: Request, db: Session = Depends(get_db)):
    _get(db, employee_id)
    sessions = (db.query(AssessmentSession)
            .filter(AssessmentSession.employee_id == employee_id)
            .order_by(AssessmentSession.session_date.desc()).all())
    result = [AssessmentSessionOut.model_validate(s) for s in sessions
              if request.state.user.get("role") == "admin" or s.session_type == "professional"]
    if request.state.user.get("role") != "admin":
        for session in result:
            session.scores = [s for s in session.scores if s.competency_id not in {c.id for c in db.query(Competency).filter(Competency.is_confidential.is_(True)).all()}]
    return result


@router.get("/{employee_id}/competency-history")
def competency_history(employee_id: int, request: Request, db: Session = Depends(get_db)):
    """Development over time -- 2024 leadership 3.8 -> 2026 4.4."""
    _get(db, employee_id)
    sessions = (db.query(AssessmentSession)
                .filter(AssessmentSession.employee_id == employee_id)
                .order_by(AssessmentSession.session_date).all())
    history: dict = {}
    for session in sessions:
        if request.state.user.get("role") != "admin" and session.session_type != "professional":
            continue
        for score in session.scores:
            if request.state.user.get("role") != "admin" and score.competency.is_confidential:
                continue
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


# ---------------------------------------------------------------------------
# Editing existing records
#
# Corrections are expected -- a typo in a date silently changes every derived
# tenure figure. Each edit records the old and new value of exactly the fields
# that moved, so the audit trail shows what was corrected rather than that
# "something was updated".
# ---------------------------------------------------------------------------

EDITABLE = {
    "education": (EmployeeEducation, [
        "level_id", "institution", "country_id", "field_id",
        "start_year", "end_year", "qualification", "document_ref"]),
    "language": (EmployeeLanguage, [
        "language_id", "scale_id", "level_id", "is_confirmed",
        "document", "confirmed_at", "valid_until"]),
    "training": (EmployeeTraining, [
        "name", "training_type_id", "job_family_id", "provider",
        "date_from", "date_to", "result", "certificate_ref", "valid_until"]),
    "work-experience": (WorkExperience, [
        "is_internal", "org_unit_id", "external_employer", "position_id",
        "external_position_title", "job_family_id", "org_unit_type_id",
        "country_id", "management_level", "date_from", "date_to"]),
}

# Changing any of these re-derives the employee's tenure figures.
METRIC_AFFECTING = {"work-experience"}


def _coerce_field(model, field: str, value):
    """Turn an incoming JSON value into what the column expects."""
    column = getattr(model, field, None)
    if value is None or value == "":
        return None
    kind = str(getattr(getattr(column, "type", None), "__class__", "").__name__)
    if kind == "Date" and isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, f"{field}: дата должна быть в формате ГГГГ-ММ-ДД")
    if kind == "Boolean":
        return value if isinstance(value, bool) else str(value).lower() in (
            "true", "1", "yes")
    return value


@router.put("/{section}/{row_id}")
def update_child_record(section: str, row_id: int, payload: dict,
                        request: Request, db: Session = Depends(get_db)):
    """Correct one row of education / languages / training / career."""
    if section not in EDITABLE:
        raise HTTPException(404, f"Раздел '{section}' нельзя редактировать. "
                                 f"Доступны: {', '.join(EDITABLE)}")

    model, allowed = EDITABLE[section]
    if section == "work-experience":
        row, employee = _editable_period(db, row_id)
    else:
        row = db.query(model).filter(model.id == row_id).first()
        if not row:
            raise HTTPException(404, "Запись не найдена")
        employee = db.query(Employee).filter(Employee.id == row.employee_id).first()

    before, after = {}, {}
    for field, raw in (payload or {}).items():
        if field not in allowed:
            continue
        new_value = _coerce_field(model, field, raw)
        old_value = getattr(row, field)
        if old_value == new_value:
            continue                      # only record what actually moved
        before[field] = str(old_value) if old_value is not None else None
        after[field] = str(new_value) if new_value is not None else None
        setattr(row, field, new_value)

    if not after:
        return {"id": row.id, "changed": []}

    # A language level must still belong to the declared scale.
    if section == "language" and ("level_id" in after or "scale_id" in after):
        level = db.query(LanguageLevel).filter(
            LanguageLevel.id == row.level_id).first()
        if not level or level.scale_id != row.scale_id:
            db.rollback()
            valid = [l.code for l in db.query(LanguageLevel)
                     .filter(LanguageLevel.scale_id == row.scale_id)
                     .order_by(LanguageLevel.rank).all()]
            raise HTTPException(422, {
                "message": "Уровень не принадлежит выбранной шкале",
                "valid_levels": valid,
            })

    if section == "work-experience" and row.date_to and row.date_from \
            and row.date_to < row.date_from:
        db.rollback()
        raise HTTPException(422, "Дата окончания не может быть раньше даты начала")

    if section == "work-experience" and row.is_internal and {"date_from", "date_to", "is_internal"} & after.keys():
        with db.no_autoflush:
            conflict = overlaps_disposal(db, row.employee_id, row.date_from, row.date_to)
        if conflict:
            db.rollback()
            raise HTTPException(409, "Период работы пересекает распоряжение / Жұмыс кезеңі қарамағында болу кезеңімен қиылысады")

    db.commit()
    db.refresh(row)

    user = getattr(request.state, "user", {}) or {}
    db.add(AuditLog(
        action="update", entity_type=f"employee_{section.replace('-', '_')}",
        entity_id=row.id, old_values=before, new_values=after,
        reason=(payload or {}).get("reason"),
        changed_by=user.get("sub", "hr"),
    ))
    db.commit()

    if section in METRIC_AFFECTING and employee:
        reconcile_current_post(db, employee)
        persist_employee_metrics(db, employee)

    return {"id": row.id, "changed": list(after)}


@router.get("/{employee_id}/history")
def employee_history(employee_id: int, db: Session = Depends(get_db)):
    """Every recorded change to this employee and their child records."""
    _get(db, employee_id)

    child_ids = {
        "employee_education": [r.id for r in db.query(EmployeeEducation).filter(
            EmployeeEducation.employee_id == employee_id).all()],
        "employee_language": [r.id for r in db.query(EmployeeLanguage).filter(
            EmployeeLanguage.employee_id == employee_id).all()],
        "employee_training": [r.id for r in db.query(EmployeeTraining).filter(
            EmployeeTraining.employee_id == employee_id).all()],
        "employee_work_experience": [r.id for r in db.query(WorkExperience).filter(
            WorkExperience.employee_id == employee_id).all()],
    }

    rows = db.query(AuditLog).filter(
        or_(
            and_(AuditLog.entity_type == "employee",
                 AuditLog.entity_id == employee_id),
            *[and_(AuditLog.entity_type == entity, AuditLog.entity_id.in_(ids))
              for entity, ids in child_ids.items() if ids],
        )
    ).order_by(AuditLog.changed_at.desc()).limit(200).all()

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
