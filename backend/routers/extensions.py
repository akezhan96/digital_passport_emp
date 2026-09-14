"""User-defined fields and file attachments.

Both features exist so an HR administrator can extend a profile without a
developer: extra fields are defined through the UI, and supporting documents
(passport photo, diploma scan, language certificate) are attached to the
section they belong to.
"""

import os
import re
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from models import (
    CustomFieldDefinition, CustomFieldValue, Attachment, AuditLog,
    ATTACHABLE_ENTITIES, CUSTOM_FIELD_TYPES,
    Employee, EmployeeEducation, EmployeeLanguage, EmployeeTraining,
    WorkExperience, AssessmentSession,
)

router = APIRouter(prefix="/api/v1", tags=["extensions"])

UPLOAD_ROOT = os.getenv("UPLOAD_DIR", "/app/uploads")

# Only these types may be stored. Kept deliberately narrow.
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
MAX_BYTES = 15 * 1024 * 1024          # 15 MB

# Magic bytes, so a renamed executable cannot masquerade as a PDF.
SIGNATURES = {
    "application/pdf": [b"%PDF-"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}

OWNER_MODELS = {
    "employee": Employee,
    "education": EmployeeEducation,
    "language": EmployeeLanguage,
    "training": EmployeeTraining,
    "work_experience": WorkExperience,
    "assessment": AssessmentSession,
}


def _check_entity(entity_type: str):
    if entity_type not in ATTACHABLE_ENTITIES:
        raise HTTPException(422, f"entity_type must be one of "
                                 f"{', '.join(ATTACHABLE_ENTITIES)}")


def _assert_exists(db: Session, entity_type: str, entity_id: int):
    """Refuse to hang data off a record that does not exist."""
    model = OWNER_MODELS.get(entity_type)
    if model is None:
        raise HTTPException(422, f"Unknown entity_type '{entity_type}'")
    if not db.query(model).filter(model.id == entity_id).first():
        raise HTTPException(404, f"No {entity_type} with id {entity_id}")


# ===========================================================================
# Custom field definitions
# ===========================================================================

@router.get("/custom-fields")
def list_definitions(entity_type: Optional[str] = None,
                     include_inactive: bool = False,
                     db: Session = Depends(get_db)):
    query = db.query(CustomFieldDefinition)
    if entity_type:
        _check_entity(entity_type)
        query = query.filter(CustomFieldDefinition.entity_type == entity_type)
    if not include_inactive:
        query = query.filter(CustomFieldDefinition.is_active.is_(True))

    rows = query.order_by(CustomFieldDefinition.entity_type,
                          CustomFieldDefinition.sort_order,
                          CustomFieldDefinition.id).all()
    return {
        "data": [{
            "id": r.id,
            "entity_type": r.entity_type,
            "code": r.code,
            "name_ru": r.name_ru,
            "name_kk": r.name_kk,
            "name_en": r.name_en,
            "field_type": r.field_type,
            "options": r.options or [],
            "help_text": r.help_text,
            "is_required": r.is_required,
            "is_active": r.is_active,
            "sort_order": r.sort_order,
        } for r in rows],
        "entity_types": list(ATTACHABLE_ENTITIES),
        "field_types": list(CUSTOM_FIELD_TYPES),
    }


@router.post("/custom-fields", status_code=201)
def create_definition(payload: Dict[str, Any], db: Session = Depends(get_db)):
    entity_type = payload.get("entity_type")
    _check_entity(entity_type)

    field_type = payload.get("field_type", "text")
    if field_type not in CUSTOM_FIELD_TYPES:
        raise HTTPException(422, f"field_type must be one of "
                                 f"{', '.join(CUSTOM_FIELD_TYPES)}")

    name_ru = (payload.get("name_ru") or "").strip()
    if not name_ru:
        raise HTTPException(422, "name_ru is required")

    # Derive a stable code from the label when the user did not supply one.
    code = (payload.get("code") or "").strip()
    if not code:
        source = payload.get("name_en") or name_ru
        code = re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_")
        code = code or f"field_{uuid.uuid4().hex[:6]}"

    if db.query(CustomFieldDefinition).filter(
        CustomFieldDefinition.entity_type == entity_type,
        CustomFieldDefinition.code == code,
    ).first():
        raise HTTPException(409, f"Field '{code}' already exists for {entity_type}")

    if field_type == "select" and not payload.get("options"):
        raise HTTPException(422, "A 'select' field needs at least one option")

    row = CustomFieldDefinition(
        entity_type=entity_type, code=code, name_ru=name_ru,
        name_kk=payload.get("name_kk"), name_en=payload.get("name_en"),
        field_type=field_type, options=payload.get("options") or [],
        help_text=payload.get("help_text"),
        is_required=bool(payload.get("is_required")),
        sort_order=int(payload.get("sort_order") or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="create", entity_type="custom_field", entity_id=row.id,
                    new_values={"entity_type": entity_type, "code": code},
                    changed_by="hr_admin"))
    db.commit()
    return {"id": row.id, "code": row.code, "entity_type": row.entity_type}


@router.put("/custom-fields/{definition_id}")
def update_definition(definition_id: int, payload: Dict[str, Any],
                      db: Session = Depends(get_db)):
    row = db.query(CustomFieldDefinition).filter(
        CustomFieldDefinition.id == definition_id).first()
    if not row:
        raise HTTPException(404, "Field not found")

    for key in ("name_ru", "name_kk", "name_en", "help_text",
                "is_required", "is_active", "sort_order", "options"):
        if key in payload:
            setattr(row, key, payload[key])
    db.commit()
    return {"id": row.id, "code": row.code}


@router.delete("/custom-fields/{definition_id}", status_code=204)
def delete_definition(definition_id: int, db: Session = Depends(get_db)):
    """Deleting a definition removes its stored values too, so the UI warns."""
    row = db.query(CustomFieldDefinition).filter(
        CustomFieldDefinition.id == definition_id).first()
    if not row:
        raise HTTPException(404, "Field not found")

    db.add(AuditLog(action="delete", entity_type="custom_field",
                    entity_id=definition_id,
                    old_values={"code": row.code, "entity_type": row.entity_type},
                    changed_by="hr_admin"))
    db.delete(row)
    db.commit()


# ===========================================================================
# Custom field values
# ===========================================================================

def _coerce(definition: CustomFieldDefinition, raw) -> Dict[str, Any]:
    """Put a submitted value in the correct typed column."""
    columns = {"value_text": None, "value_number": None,
               "value_date": None, "value_bool": None}

    if raw is None or raw == "":
        return columns

    kind = definition.field_type
    try:
        if kind == "number":
            columns["value_number"] = float(raw)
        elif kind == "date":
            columns["value_date"] = (raw if isinstance(raw, date)
                                     else datetime.strptime(str(raw), "%Y-%m-%d").date())
        elif kind == "boolean":
            columns["value_bool"] = (raw if isinstance(raw, bool)
                                     else str(raw).lower() in ("true", "1", "yes"))
        elif kind == "select":
            allowed = [o.get("value") if isinstance(o, dict) else o
                       for o in (definition.options or [])]
            if allowed and str(raw) not in [str(a) for a in allowed]:
                raise HTTPException(422, {
                    "message": f"'{raw}' is not an allowed value for "
                               f"'{definition.name_ru}'",
                    "allowed": allowed,
                })
            columns["value_text"] = str(raw)
        else:
            columns["value_text"] = str(raw)
    except HTTPException:
        raise
    except (ValueError, TypeError):
        raise HTTPException(422, f"'{raw}' is not a valid {kind} "
                                 f"for '{definition.name_ru}'")
    return columns


@router.get("/custom-values/{entity_type}/{entity_id}")
def get_values(entity_type: str, entity_id: int, db: Session = Depends(get_db)):
    """Definitions for this section, each with its current value."""
    _check_entity(entity_type)

    definitions = (db.query(CustomFieldDefinition)
                   .filter(CustomFieldDefinition.entity_type == entity_type,
                           CustomFieldDefinition.is_active.is_(True))
                   .order_by(CustomFieldDefinition.sort_order,
                             CustomFieldDefinition.id).all())

    stored = {v.definition_id: v for v in db.query(CustomFieldValue).filter(
        CustomFieldValue.entity_type == entity_type,
        CustomFieldValue.entity_id == entity_id).all()}

    return {"data": [{
        "definition_id": d.id,
        "code": d.code,
        "name_ru": d.name_ru,
        "name_kk": d.name_kk,
        "name_en": d.name_en,
        "field_type": d.field_type,
        "options": d.options or [],
        "help_text": d.help_text,
        "is_required": d.is_required,
        "value": stored[d.id].as_python() if d.id in stored else None,
    } for d in definitions]}


@router.put("/custom-values/{entity_type}/{entity_id}")
def set_values(entity_type: str, entity_id: int, payload: Dict[str, Any],
               db: Session = Depends(get_db)):
    """Upsert values. Body: {"values": {"<definition_id>": <value>, ...}}"""
    _check_entity(entity_type)
    _assert_exists(db, entity_type, entity_id)

    submitted = payload.get("values") or {}
    for key, raw in submitted.items():
        definition = db.query(CustomFieldDefinition).filter(
            CustomFieldDefinition.id == int(key)).first()
        if not definition or definition.entity_type != entity_type:
            continue

        if definition.is_required and (raw is None or raw == ""):
            raise HTTPException(422, f"'{definition.name_ru}' is required")

        columns = _coerce(definition, raw)
        existing = db.query(CustomFieldValue).filter(
            CustomFieldValue.definition_id == definition.id,
            CustomFieldValue.entity_type == entity_type,
            CustomFieldValue.entity_id == entity_id).first()

        if existing:
            for col, value in columns.items():
                setattr(existing, col, value)
        else:
            db.add(CustomFieldValue(definition_id=definition.id,
                                    entity_type=entity_type,
                                    entity_id=entity_id, **columns))
    db.commit()
    return get_values(entity_type, entity_id, db)


# ===========================================================================
# Attachments
# ===========================================================================

def _safe_original_name(name: str) -> str:
    """Keep a readable label but strip anything path-like."""
    cleaned = os.path.basename(name or "file")
    cleaned = re.sub(r"[\r\n\t]", "", cleaned)
    return cleaned[:300] or "file"


def _serialise_attachment(row: Attachment) -> Dict[str, Any]:
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "original_name": row.original_name,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "description": row.description,
        "uploaded_by": row.uploaded_by,
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "is_image": row.content_type.startswith("image/"),
        "download_url": f"/api/v1/attachments/{row.id}/download",
    }


@router.post("/attachments/{entity_type}/{entity_id}", status_code=201)
async def upload(entity_type: str, entity_id: int,
                 file: UploadFile = File(...),
                 description: Optional[str] = Form(None),
                 db: Session = Depends(get_db)):
    _check_entity(entity_type)
    _assert_exists(db, entity_type, entity_id)

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(422, "The file is empty")
    if len(content) > MAX_BYTES:
        raise HTTPException(413, {
            "message": f"File is too large ({len(content) // 1024 // 1024} MB). "
                       f"Maximum is {MAX_BYTES // 1024 // 1024} MB.",
        })

    # Trust the bytes, not the declared content type.
    detected = None
    for mime, signatures in SIGNATURES.items():
        if any(content.startswith(sig) for sig in signatures):
            detected = mime
            break
    if detected is None:
        raise HTTPException(422, {
            "message": "Only PDF, JPG and PNG files are accepted",
            "detected": file.content_type,
        })

    extension = ALLOWED_TYPES[detected]
    stored_name = f"{uuid.uuid4().hex}{extension}"

    folder = os.path.join(UPLOAD_ROOT, entity_type)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, stored_name), "wb") as handle:
        handle.write(content)

    row = Attachment(
        entity_type=entity_type, entity_id=entity_id,
        stored_name=stored_name,
        original_name=_safe_original_name(file.filename),
        content_type=detected, size_bytes=len(content),
        description=description, uploaded_by="hr",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    db.add(AuditLog(action="upload", entity_type=f"attachment:{entity_type}",
                    entity_id=entity_id,
                    new_values={"file": row.original_name,
                                "size": row.size_bytes}, changed_by="hr"))
    db.commit()

    return _serialise_attachment(row)


# NOTE: this route must stay ABOVE the two-parameter listing route below.
# Starlette matches in declaration order, and "/attachments/5/download" also
# fits "/attachments/{entity_type}/{entity_id}" -- which would then fail
# converting "download" to an int and return 422 instead of falling through.
@router.get("/attachments/{attachment_id}/download")
def download(attachment_id: int, db: Session = Depends(get_db)):
    row = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not row:
        raise HTTPException(404, "Attachment not found")

    path = os.path.join(UPLOAD_ROOT, row.entity_type, row.stored_name)
    if not os.path.exists(path):
        raise HTTPException(404, "The stored file is missing from disk")

    return FileResponse(path, media_type=row.content_type,
                        filename=row.original_name)


@router.get("/attachments/{entity_type}/{entity_id}")
def list_attachments(entity_type: str, entity_id: int,
                     db: Session = Depends(get_db)):
    _check_entity(entity_type)
    rows = (db.query(Attachment)
            .filter(Attachment.entity_type == entity_type,
                    Attachment.entity_id == entity_id)
            .order_by(Attachment.uploaded_at.desc()).all())
    return {"data": [_serialise_attachment(r) for r in rows]}


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    row = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not row:
        raise HTTPException(404, "Attachment not found")

    path = os.path.join(UPLOAD_ROOT, row.entity_type, row.stored_name)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass          # metadata still goes; an orphaned file is harmless

    db.add(AuditLog(action="delete", entity_type=f"attachment:{row.entity_type}",
                    entity_id=row.entity_id,
                    old_values={"file": row.original_name}, changed_by="hr"))
    db.delete(row)
    db.commit()
