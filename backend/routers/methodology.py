"""Methodology administration.

Everything here belongs to the HR methodologist. Changing a weight, a step
function, a compensation value or a readiness band is a data edit with a new
version -- never a code release.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from database import get_db
from models import (
    ScoringModel, ScoringFunction, CompensationTable, ReadinessBand, AuditLog,
    MatchingRun,
)
from schemas import (
    ScoringModelIn, ScoringModelOut, ScoringModelDetail,
    ScoringFunctionIn, ScoringFunctionOut,
    CompensationTableIn, CompensationTableOut,
    ReadinessBandIn, ReadinessBandOut,
)

router = APIRouter(prefix="/api/v1/methodology", tags=["methodology"])

VALID_KINDS = ("linear", "step_absolute", "step_ratio", "boolean", "level_scale")


def _get_model(db: Session, model_id: int) -> ScoringModel:
    model = db.query(ScoringModel).filter(ScoringModel.id == model_id).first()
    if not model:
        raise HTTPException(404, "Scoring model not found")
    return model


@router.get("/scoring-models", response_model=List[ScoringModelOut])
def list_models(db: Session = Depends(get_db)):
    return db.query(ScoringModel).order_by(ScoringModel.version).all()


@router.get("/scoring-models/{model_id}", response_model=ScoringModelDetail)
def get_model(model_id: int, db: Session = Depends(get_db)):
    return _get_model(db, model_id)


@router.post("/scoring-models", response_model=ScoringModelOut, status_code=201)
def create_model(payload: ScoringModelIn, db: Session = Depends(get_db)):
    if db.query(ScoringModel).filter(ScoringModel.version == payload.version).first():
        raise HTTPException(409, "This version already exists")
    model = ScoringModel(**payload.model_dump())
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


@router.post("/scoring-models/{model_id}/clone", response_model=ScoringModelOut,
             status_code=201)
def clone_model(model_id: int, new_version: str, db: Session = Depends(get_db)):
    """Never edit an approved model in place -- clone it, adjust, re-approve.

    Historical matching runs stay bound to the version that produced them.
    """
    source = _get_model(db, model_id)
    if db.query(ScoringModel).filter(ScoringModel.version == new_version).first():
        raise HTTPException(409, "Target version already exists")

    clone = ScoringModel(
        version=new_version,
        name=f"{source.name} (from {source.version})",
        description=source.description,
        status="draft",
    )
    db.add(clone)
    db.flush()

    for fn in source.functions:
        db.add(ScoringFunction(model_id=clone.id, code=fn.code, name_ru=fn.name_ru,
                               name_kk=fn.name_kk, name_en=fn.name_en,
                               kind=fn.kind, breakpoints=fn.breakpoints))
    for table in source.compensations:
        db.add(CompensationTable(model_id=clone.id, code=table.code,
                                 name_ru=table.name_ru, name_kk=table.name_kk,
                                 name_en=table.name_en, entries=table.entries))
    for band in source.readiness_bands:
        db.add(ReadinessBand(model_id=clone.id, code=band.code, name_ru=band.name_ru,
                             name_kk=band.name_kk, name_en=band.name_en,
                             min_score=band.min_score, color=band.color))
    db.commit()
    db.refresh(clone)
    return clone


@router.post("/scoring-models/{model_id}/approve", response_model=ScoringModelOut)
def approve_model(model_id: int, approved_by: str = "hr_methodologist",
                  make_default: bool = False, db: Session = Depends(get_db)):
    model = _get_model(db, model_id)

    if not model.readiness_bands:
        raise HTTPException(422, "Cannot approve a model with no readiness bands")

    model.status = "approved"
    model.approved_by = approved_by
    model.approved_at = datetime.utcnow()

    if make_default:
        db.query(ScoringModel).update({ScoringModel.is_default: False})
        model.is_default = True

    db.commit()
    db.refresh(model)

    db.add(AuditLog(action="approve", entity_type="scoring_model", entity_id=model.id,
                    new_values={"version": model.version, "status": "approved"},
                    changed_by=approved_by))
    db.commit()
    return model


@router.delete("/scoring-models/{model_id}", status_code=204)
def delete_model(model_id: int, db: Session = Depends(get_db)):
    """Discard a draft. Approved models are permanent: matching runs are bound
    to the version that produced them, so deleting one would destroy the
    reproducibility of every shortlist scored under it."""
    model = _get_model(db, model_id)

    if model.status == "approved":
        raise HTTPException(422, "Утверждённую модель удалить нельзя — "
                                 "к ней привязаны прошлые запуски подбора")
    if model.is_default:
        raise HTTPException(422, "Нельзя удалить модель, назначенную по умолчанию")

    used_by = db.query(MatchingRun).filter(
        MatchingRun.scoring_model_id == model_id).count()
    if used_by:
        raise HTTPException(422, f"Модель использована в {used_by} запуск(ах) подбора")

    db.add(AuditLog(action="delete", entity_type="scoring_model", entity_id=model_id,
                    old_values={"version": model.version}, changed_by="hr_methodologist"))
    db.delete(model)
    db.commit()


# ---------------------------------------------------------------------------
# Match functions  (M_i)
# ---------------------------------------------------------------------------

@router.get("/scoring-models/{model_id}/functions",
            response_model=List[ScoringFunctionOut])
def list_functions(model_id: int, db: Session = Depends(get_db)):
    _get_model(db, model_id)
    return db.query(ScoringFunction).filter(
        ScoringFunction.model_id == model_id
    ).order_by(ScoringFunction.code).all()


@router.post("/scoring-models/{model_id}/functions",
             response_model=ScoringFunctionOut, status_code=201)
def create_function(model_id: int, payload: ScoringFunctionIn,
                    db: Session = Depends(get_db)):
    model = _get_model(db, model_id)
    if model.status == "approved":
        raise HTTPException(422, "An approved model is immutable. Clone it first.")
    if payload.kind not in VALID_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(VALID_KINDS)}")

    row = ScoringFunction(model_id=model_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/functions/{function_id}", response_model=ScoringFunctionOut)
def update_function(function_id: int, payload: ScoringFunctionIn,
                    db: Session = Depends(get_db)):
    row = db.query(ScoringFunction).filter(ScoringFunction.id == function_id).first()
    if not row:
        raise HTTPException(404, "Function not found")
    if row.model and row.model.status == "approved":
        raise HTTPException(422, "An approved model is immutable. Clone it first.")
    if payload.kind not in VALID_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(VALID_KINDS)}")

    before = {"kind": row.kind, "breakpoints": row.breakpoints}
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="update", entity_type="scoring_function", entity_id=row.id,
                    old_values=before,
                    new_values={"kind": row.kind, "breakpoints": row.breakpoints},
                    changed_by="hr_methodologist"))
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Compensation tables
# ---------------------------------------------------------------------------

@router.get("/scoring-models/{model_id}/compensations",
            response_model=List[CompensationTableOut])
def list_compensations(model_id: int, db: Session = Depends(get_db)):
    _get_model(db, model_id)
    return db.query(CompensationTable).filter(
        CompensationTable.model_id == model_id
    ).all()


@router.post("/scoring-models/{model_id}/compensations",
             response_model=CompensationTableOut, status_code=201)
def create_compensation(model_id: int, payload: CompensationTableIn,
                        db: Session = Depends(get_db)):
    model = _get_model(db, model_id)
    if model.status == "approved":
        raise HTTPException(422, "An approved model is immutable. Clone it first.")
    row = CompensationTable(model_id=model_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/compensations/{table_id}", response_model=CompensationTableOut)
def update_compensation(table_id: int, payload: CompensationTableIn,
                        db: Session = Depends(get_db)):
    row = db.query(CompensationTable).filter(CompensationTable.id == table_id).first()
    if not row:
        raise HTTPException(404, "Compensation table not found")
    if row.model and row.model.status == "approved":
        raise HTTPException(422, "An approved model is immutable. Clone it first.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Readiness bands
# ---------------------------------------------------------------------------

@router.get("/scoring-models/{model_id}/readiness-bands",
            response_model=List[ReadinessBandOut])
def list_bands(model_id: int, db: Session = Depends(get_db)):
    _get_model(db, model_id)
    return (db.query(ReadinessBand)
            .filter(ReadinessBand.model_id == model_id)
            .order_by(ReadinessBand.min_score.desc()).all())


@router.post("/scoring-models/{model_id}/readiness-bands",
             response_model=ReadinessBandOut, status_code=201)
def create_band(model_id: int, payload: ReadinessBandIn,
                db: Session = Depends(get_db)):
    model = _get_model(db, model_id)
    if model.status == "approved":
        raise HTTPException(422, "An approved model is immutable. Clone it first.")
    row = ReadinessBand(model_id=model_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/readiness-bands/{band_id}", response_model=ReadinessBandOut)
def update_band(band_id: int, payload: ReadinessBandIn,
                db: Session = Depends(get_db)):
    row = db.query(ReadinessBand).filter(ReadinessBand.id == band_id).first()
    if not row:
        raise HTTPException(404, "Band not found")
    if row.model and row.model.status == "approved":
        raise HTTPException(422, "An approved model is immutable. Clone it first.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row
