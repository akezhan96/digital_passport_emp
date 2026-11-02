"""Generated employee documents (CV) in PDF and DOCX."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from models import Employee, AuditLog
from services.documents import (
    build_cv_data, render_pdf, render_docx, safe_filename,
)
from services import resume
from typing import Literal

router = APIRouter(prefix="/api/v1", tags=["documents"])

MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document",
}


@router.get("/employees/{employee_id}/document")
def employee_document(employee_id: int, request: Request,
                      format: str = "pdf", lang: str = "ru",
                      include_confidential: bool = False,
                      template: Literal["profile", "resume"] = "profile",
                      sections: str = "career,education,languages,training,metrics",
                      contacts: bool = False,
                      db: Session = Depends(get_db)):
    """Render the employee CV.

    Psychological assessments stay out unless explicitly requested, and that
    request is recorded.
    """
    fmt = (format or "pdf").lower()
    if fmt not in MEDIA:
        raise HTTPException(422, "format: pdf или docx")
    if lang not in ("ru", "kk"):
        lang = "ru"
    if include_confidential and getattr(request.state, "user", {}).get("role") != "admin":
        raise HTTPException(403, "Недостаточно прав / Құқықтар жеткіліксіз")

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Сотрудник не найден")

    selected_sections = [s for s in sections.split(',') if s]
    if template == "resume" and (not selected_sections or any(s not in resume.SECTIONS for s in selected_sections)):
        raise HTTPException(422, "Выберите разделы резюме / Түйіндеме бөлімдерін таңдаңыз")
    data = (resume.build_resume(db, employee, lang, selected_sections, contacts) if template == "resume"
            else build_cv_data(db, employee, lang=lang, include_confidential=include_confidential))

    try:
        renderer = resume if template == "resume" else None
        blob = (renderer.render_pdf(data) if fmt == "pdf" else renderer.render_docx(data)) if renderer else (render_pdf(data) if fmt == "pdf" else render_docx(data))
    except ImportError as e:                                     # noqa: BLE001
        raise HTTPException(
            500, f"Библиотека генерации документов недоступна: {e}")

    user = getattr(request.state, "user", {}) or {}
    db.add(AuditLog(
        action="export_document", entity_type="employee", entity_id=employee_id,
        new_values={"format": fmt, "lang": lang, "template": template,
                    "confidential": include_confidential},
        changed_by=user.get("sub", "unknown"),
    ))
    db.commit()

    name = safe_filename(employee, fmt)
    # Both forms: ASCII for old clients, UTF-8 for the readable one.
    readable = quote(f"{employee.full_name}.{fmt}")
    disposition = (f'attachment; filename="{name}"; '
                   f"filename*=UTF-8''{readable}")

    return Response(content=blob, media_type=MEDIA[fmt],
                    headers={"Content-Disposition": disposition})
