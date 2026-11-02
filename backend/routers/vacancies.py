from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional

from database import get_db
from models import (
    Vacancy, Requirement, PositionProfile, RequirementType, AuditLog, CandidateMethodology, Country, OrgUnit,
)
from schemas import (
    VacancyIn, VacancyUpdate, VacancyOut, VacancyDetail,
    RequirementIn, RequirementUpdate, RequirementOut,
    PositionProfileIn, PositionProfileOut,
)

router = APIRouter(prefix="/api/v1", tags=["vacancies"])

def _actor(request: Request) -> str:
    """Whoever is signed in, for the change history."""
    return (getattr(request.state, "user", {}) or {}).get("sub", "unknown")



# ---------------------------------------------------------------------------
# Position profiles (reusable requirement templates)
# ---------------------------------------------------------------------------

@router.post("/position-profiles", response_model=PositionProfileOut, status_code=201)
def create_profile(payload: PositionProfileIn, db: Session = Depends(get_db)):
    if db.query(PositionProfile).filter(PositionProfile.code == payload.code).first():
        raise HTTPException(409, "A profile with this code already exists")
    row = PositionProfile(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/position-profiles", response_model=List[PositionProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(PositionProfile).order_by(PositionProfile.name_ru).all()


@router.get("/position-profiles/{profile_id}/requirements",
            response_model=List[RequirementOut])
def profile_requirements(profile_id: int, db: Session = Depends(get_db)):
    return (db.query(Requirement)
            .filter(Requirement.profile_id == profile_id,
                    Requirement.vacancy_id.is_(None))
            .order_by(Requirement.sort_order).all())


@router.post("/position-profiles/{profile_id}/requirements",
             response_model=RequirementOut, status_code=201)
def add_profile_requirement(profile_id: int, payload: RequirementIn,
                            db: Session = Depends(get_db)):
    if not db.query(PositionProfile).filter(PositionProfile.id == profile_id).first():
        raise HTTPException(404, "Profile not found")
    row = Requirement(profile_id=profile_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Vacancies
# ---------------------------------------------------------------------------

def _published_method(db, identity=None):
    query = db.query(CandidateMethodology)
    method = (query.filter_by(id=identity).first() if identity is not None
              else query.filter_by(status='active').first())
    if not method or method.status not in ('active', 'archived'):
        raise HTTPException(422, 'Выберите опубликованную версию методики / Жарияланған әдістеме нұсқасын таңдаңыз')
    return method


def _validate_references(db, values):
    if 'status' in values and values['status'] not in ('draft','active','requirements_approved','closed'):
        raise HTTPException(422, 'Недопустимый статус вакансии / Бос орын мәртебесі жарамсыз')
    for key, model, required in [('country_id', Country, True), ('org_unit_id', OrgUnit, False)]:
        if key in values and ((required and not values[key]) or (values[key] and not db.get(model, values[key]))):
            raise HTTPException(422, 'Страна или подразделение не найдены / Ел немесе бөлімше табылмады')
    if 'title' in values and not (values['title'] or '').strip():
        raise HTTPException(422, 'Укажите название вакансии / Бос орын атауын көрсетіңіз')



@router.post("/vacancies", response_model=VacancyOut, status_code=201)
def create_vacancy(payload: VacancyIn, request: Request,
                   copy_from_profile: bool = True,
                   db: Session = Depends(get_db)):
    values = payload.model_dump(exclude={'assessment_mode'})
    if payload.assessment_mode not in ('candidate', 'legacy'):
        raise HTTPException(422, 'Неизвестный способ оценки / Бағалау тәсілі белгісіз')
    if payload.assessment_mode == 'candidate':
        method = _published_method(db, payload.candidate_methodology_id)
        values['candidate_methodology_id'] = method.id
        values['profile_id'] = None
    elif payload.candidate_methodology_id is not None:
        raise HTTPException(422, 'Выберите один способ оценки / Бір бағалау тәсілін таңдаңыз')
    _validate_references(db, values)
    vacancy = Vacancy(**values)
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)

    # A vacancy is an instance of a profile plus a delta: seed it with the
    # template's requirements so the analyst edits rather than starts blank.
    if copy_from_profile and vacancy.profile_id:
        template = (db.query(Requirement)
                    .filter(Requirement.profile_id == vacancy.profile_id,
                            Requirement.vacancy_id.is_(None))
                    .order_by(Requirement.sort_order).all())
        for source in template:
            db.add(Requirement(
                vacancy_id=vacancy.id,
                requirement_type_id=source.requirement_type_id,
                label_ru=source.label_ru,
                label_kk=source.label_kk,
                label_en=source.label_en,
                condition=source.condition,
                weight=source.weight,
                criticality=source.criticality,
                scoring_function_id=source.scoring_function_id,
                compensation_table_id=source.compensation_table_id,
                sort_order=source.sort_order,
            ))
        db.commit()

    db.add(AuditLog(action="create", entity_type="vacancy", entity_id=vacancy.id,
                    new_values={"title": vacancy.title}, changed_by=_actor(request)))
    db.commit()
    db.refresh(vacancy)
    return vacancy


@router.get("/vacancies")
def list_vacancies(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Vacancy)
    if status:
        query = query.filter(Vacancy.status == status)
    rows = query.options(selectinload(Vacancy.country), selectinload(Vacancy.requirements),
                         selectinload(Vacancy.candidate_methodology)).order_by(Vacancy.created_at.desc(), Vacancy.id.desc()).all()
    return {
        "total": len(rows),
        "data": [{
            "id": v.id,
            "title": v.title, "title_kk": v.title_kk,
            "assessment_mode": v.assessment_mode,
            "candidate_methodology_id": v.candidate_methodology_id,
            "methodology_version": v.candidate_methodology.version if v.candidate_methodology else None,
            "min_candidate_percent": float(v.min_candidate_percent),
            "requires_technical_profile": v.requires_technical_profile,
            "status": v.status,
            "country_id": v.country_id,
            "country_name_ru": v.country.name_ru if v.country else None,
            "country_name_kk": v.country.name_kk if v.country else None,
            "country_name_en": v.country.name_en if v.country else None,
            "org_unit_id": v.org_unit_id,
            "profile_id": v.profile_id,
            "requirements_count": len(v.requirements),
            "total_weight": sum(r.weight for r in v.requirements),
            "requirements_version": v.requirements_version,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        } for v in rows],
    }


@router.get("/vacancies/{vacancy_id}", response_model=VacancyDetail)
def get_vacancy(vacancy_id: int, db: Session = Depends(get_db), request: Request = None):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not vacancy:
        raise HTTPException(404, "Vacancy not found")
    detail = VacancyDetail.model_validate(vacancy)
    detail.total_weight = sum(r.weight for r in vacancy.requirements)
    if vacancy.candidate_methodology:
        from services.candidate_methodology import method_dict
        detail.methodology = method_dict(vacancy.candidate_methodology,
            include_confidential=bool(request and request.state.user.get('role') == 'admin'))
    return detail


@router.get('/vacancies/{vacancy_id}/recruitment')
def recruitment(vacancy_id: int, request: Request, db: Session = Depends(get_db),
                reveal_names: bool = Query(False), status: Optional[str] = None,
                offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    vacancy = db.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise HTTPException(404, 'Вакансия не найдена / Бос орын табылмады')
    if status not in (None, 'selected', 'on_hold', 'reserve', 'rejected', 'appointed'):
        raise HTTPException(422, 'Некорректный этап работы / Жұмыс кезеңі қате')
    if reveal_names:
        db.add(AuditLog(action='reveal_identities', entity_type='vacancy',
                        entity_id=vacancy_id, changed_by=_actor(request)))
        db.commit()
    from services.recruitment import vacancy_recruitment
    return vacancy_recruitment(db, vacancy, is_admin=(getattr(request.state, 'user', {}) or {}).get('role') == 'admin',
        reveal_names=reveal_names, status=status, offset=offset, limit=limit)


@router.put("/vacancies/{vacancy_id}", response_model=VacancyOut)
def update_vacancy(vacancy_id: int, payload: VacancyUpdate,
                   db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not vacancy:
        raise HTTPException(404, "Vacancy not found")

    changes = payload.model_dump(exclude_unset=True)

    _validate_references(db, changes)
    for key in ('candidate_methodology_id','min_candidate_percent','requires_technical_profile'):
        if key in changes and changes[key] is None:
            raise HTTPException(422, 'Настройки методики не могут быть пустыми / Әдістеме баптаулары бос болмауы тиіс')
    if 'candidate_methodology_id' in changes:
        _published_method(db, changes['candidate_methodology_id'])
    methodology_id = changes.get('candidate_methodology_id', vacancy.candidate_methodology_id)
    # Historical vacancies keep their original weight-based approval rule.
    if not methodology_id and changes.get("status") in ("requirements_approved", "active"):
        total = sum(r.weight for r in vacancy.requirements)
        if total != 100:
            raise HTTPException(422, {
                "message": "Requirement weights must total exactly 100 before approval",
                "current_total": total,
            })

    if any(key in changes and changes[key] != getattr(vacancy,key)
           for key in ('candidate_methodology_id','min_candidate_percent','requires_technical_profile', 'country_id', 'org_unit_id')):
        vacancy.requirements_version = (vacancy.requirements_version or 1) + 1
    for key, value in changes.items():
        setattr(vacancy, key, value)
    db.commit()
    db.refresh(vacancy)
    return vacancy


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

@router.get("/vacancies/{vacancy_id}/requirements")
def list_requirements(vacancy_id: int, db: Session = Depends(get_db)):
    rows = (db.query(Requirement)
            .filter(Requirement.vacancy_id == vacancy_id)
            .order_by(Requirement.sort_order).all())
    total = sum(r.weight for r in rows)
    return {
        "data": [RequirementOut.model_validate(r) for r in rows],
        "total_weight": total,
        "is_balanced": total == 100,
    }


@router.post("/vacancies/{vacancy_id}/requirements",
             response_model=RequirementOut, status_code=201)
def add_requirement(vacancy_id: int, payload: RequirementIn,
                    db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not vacancy:
        raise HTTPException(404, "Vacancy not found")

    req_type = db.query(RequirementType).filter(
        RequirementType.id == payload.requirement_type_id
    ).first()
    if not req_type:
        raise HTTPException(422, "Unknown requirement type")

    if payload.criticality not in ("critical", "must", "nice"):
        raise HTTPException(422, "criticality must be critical, must or nice")

    if vacancy.candidate_methodology_id:
        raise HTTPException(422, 'Для этой вакансии настройте версию и порог методики / Бұл бос орын үшін әдістеме нұсқасын және шегін баптаңыз')
    row = Requirement(vacancy_id=vacancy_id, **payload.model_dump())
    db.add(row)

    # Changing requirements after a run invalidates it -> new version.
    vacancy.requirements_version = (vacancy.requirements_version or 1) + 1
    db.commit()
    db.refresh(row)
    return row


@router.put("/requirements/{requirement_id}", response_model=RequirementOut)
def update_requirement(requirement_id: int, payload: RequirementUpdate,
                       request: Request,
                       db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not row:
        raise HTTPException(404, "Requirement not found")

    changes = payload.model_dump(exclude_unset=True)
    before = {k: getattr(row, k) for k in changes}
    for key, value in changes.items():
        setattr(row, key, value)

    if row.vacancy_id:
        vacancy = db.query(Vacancy).filter(Vacancy.id == row.vacancy_id).first()
        if vacancy:
            vacancy.requirements_version = (vacancy.requirements_version or 1) + 1

    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="update", entity_type="requirement", entity_id=row.id,
                    old_values={k: str(v) for k, v in before.items()},
                    new_values={k: str(v) for k, v in changes.items()},
                    changed_by=_actor(request)))
    db.commit()
    return row


@router.delete("/requirements/{requirement_id}", status_code=204)
def delete_requirement(requirement_id: int, db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not row:
        raise HTTPException(404, "Requirement not found")
    db.delete(row)
    db.commit()
