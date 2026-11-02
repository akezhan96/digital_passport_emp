"""Record appointments and periods out of post, with atomic audit and undo."""

from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Employee, WorkExperience, Position, OrgUnit, Vacancy,
    MatchingResult, Decision, AuditLog, DisposalPeriod,
)
from services.metrics import persist_employee_metrics
from services.career import (appointment_events, career_metadata, undo_available, protected_period_ids,
                             disposal_undo_available, lock_employee, work_post_snapshot)
from services.staffing import check_vacancy_available
from services.recruitment import appointment_state

router = APIRouter(prefix="/api/v1", tags=["appointments"])

LEGACY_APPOINTMENT_TYPES = ("initial", "transfer", "promotion", "return", "external")

APPOINTMENT_BLOCKERS = {
    'not_selected': 'Сначала сохраните решение «Выбран» / Алдымен «Таңдалды» шешімін сақтаңыз',
    'selection_superseded': 'Есть более новое решение по кандидату; откройте его из вакансии / Үміткер бойынша жаңа шешім бар; оны бос орыннан ашыңыз',
    'already_appointed': 'Назначение по этой вакансии уже оформлено / Бұл бос орынға тағайындау рәсімделген',
    'vacancy_closed': 'Вакансия закрыта / Бос орын жабылған',
    'vacancy_changed': 'Условия вакансии изменились; выполните новый подбор / Бос орын шарттары өзгерді; жаңа іріктеу жүргізіңіз',
    'employee_inactive': 'Назначить можно только работающего сотрудника / Тек жұмыс істейтін қызметкерді тағайындауға болады',
    'forbidden': 'Назначение доступно только администратору / Тағайындау тек әкімшіге қолжетімді',
}


def _selection_for_appointment(db, employee, payload, request):
    """Validate links while the caller holds the employee row lock."""
    result_id, vacancy_id = payload.get('result_id'), payload.get('vacancy_id')
    if not result_id:
        if vacancy_id:
            raise HTTPException(422, 'Для назначения по вакансии выберите результат подбора / Бос орынға тағайындау үшін іріктеу нәтижесін таңдаңыз')
        return None, None
    result = db.get(MatchingResult, result_id)
    if not result or result.employee_id != employee.id:
        raise HTTPException(422, 'Результат подбора не относится к этому сотруднику / Іріктеу нәтижесі бұл қызметкерге қатысты емес')
    vacancy = (db.query(Vacancy).filter_by(id=result.run.vacancy_id).with_for_update().populate_existing().one())
    if vacancy_id is not None and vacancy_id != vacancy.id:
        raise HTTPException(422, 'Результат подбора относится к другой вакансии / Іріктеу нәтижесі басқа бос орынға қатысты')
    if vacancy.org_unit_id is not None and payload.get('org_unit_id') != vacancy.org_unit_id:
        raise HTTPException(422, 'Подразделение назначения должно совпадать с вакансией / Тағайындау бөлімшесі бос орынға сәйкес болуы тиіс')
    state, _ = appointment_state(db, result, is_admin=(getattr(request.state, 'user', {}) or {}).get('role') == 'admin')
    if not state['can_appoint']:
        raise HTTPException(403 if state['reason_code'] == 'forbidden' else 409,
                            APPOINTMENT_BLOCKERS[state['reason_code']])
    if not result.is_qualified and not ((result.decision.reason if result.decision else '') or str(payload.get('reason') or '')).strip():
        raise HTTPException(422, 'Для кандидата, которому требуется проверка, укажите основание назначения / Тексеруді қажет ететін үміткерді тағайындау негізін көрсетіңіз')
    return vacancy, result


def _describe(position: Optional[Position], unit: Optional[OrgUnit]) -> str:
    parts = [p for p in (position.name_ru if position else None,
                         unit.name_ru if unit else None) if p]
    return " · ".join(parts) if parts else "не указано"


def _actor(request):
    user = getattr(request.state, "user", {}) or {}
    if user.get("role") != "admin":
        raise HTTPException(403, APPOINTMENT_BLOCKERS["forbidden"])
    return user.get("sub", "hr")


def _save_transition(db, employee):
    try:
        db.flush()
        db.expire(employee, ["work_experience", "metrics"])
        persist_employee_metrics(db, employee, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _check_restored_post(db, employee, previous, original_end):
    if not previous or not previous.org_unit_id or not previous.position_id or (original_end and original_end < date.today()):
        return
    db.query(OrgUnit).filter_by(id=previous.org_unit_id).with_for_update().one()
    problem = check_vacancy_available(db, previous.org_unit_id, previous.position_id, exclude_employee_id=employee.id)
    if problem and problem["reason"] == "full":
        raise HTTPException(409, problem)


@router.post("/employees/{employee_id}/appointments", status_code=201)
def create_appointment(employee_id: int, payload: Dict[str, Any],
                       request: Request, db: Session = Depends(get_db)):
    actor = _actor(request)
    employee = lock_employee(db, employee_id)
    if not employee:
        raise HTTPException(404, "Сотрудник не найден / Қызметкер табылмады")
    action = payload.get("appointment_type", "appointment")
    if action in LEGACY_APPOINTMENT_TYPES:
        action = "appointment"
    if action not in ("appointment", "disposal"):
        raise HTTPException(422, "Выберите назначение или вывод в распоряжение / Тағайындауды немесе қарамағына шығаруды таңдаңыз")
    vacancy, result = (_selection_for_appointment(db, employee, payload, request)
                       if action == "appointment" else (None, None))
    if employee.employment_status != "active" or employee.profile_status == "archived":
        raise HTTPException(422, APPOINTMENT_BLOCKERS["employee_inactive"])
    try:
        effective = date.fromisoformat(str(payload.get("effective_date", "")))
    except ValueError:
        raise HTTPException(422, "Укажите дату в формате ГГГГ-ММ-ДД / Күнді ЖЖЖЖ-АА-КК форматында көрсетіңіз")
    if effective > date.today() or (employee.hire_date and effective < employee.hire_date):
        raise HTTPException(422, "Дата должна быть между приёмом на работу и сегодняшним днём / Күн жұмысқа қабылданған күннен бүгінге дейін болуы керек")
    if payload.get("end_previous") is False:
        raise HTTPException(422, "Сначала завершите текущее назначение / Алдымен ағымдағы тағайындауды аяқтаңыз")

    disposals = db.query(DisposalPeriod).filter_by(employee_id=employee_id).all()
    if any(p.date_from >= effective or (p.date_to and p.date_to >= effective) for p in disposals):
        raise HTTPException(409, "Дата пересекает оформленный период распоряжения / Күн рәсімделген қарамағында болу кезеңімен қиылысады")
    open_disposal = next((p for p in disposals if p.date_to is None), None)
    internal = [r for r in employee.work_experience if r.is_internal]
    if any(r.date_from >= effective for r in internal):
        raise HTTPException(422, "Дата должна быть позже начала последнего внутреннего периода / Күн соңғы ішкі кезеңнің басталуынан кейін болуы тиіс")
    active_posts = [r for r in internal if r.date_to is None or r.date_to >= effective]
    if len(active_posts) > 1 or (active_posts and open_disposal):
        raise HTTPException(409, "Уточните пересекающиеся внутренние периоды / Қиылысатын ішкі кезеңдерді нақтылаңыз")
    current = active_posts[0] if active_posts else None
    if current and current.date_to and current.date_to < date.today():
        raise HTTPException(422, "Дата пересекает завершённый период работы / Күн аяқталған жұмыс кезеңімен қиылысады")
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise HTTPException(422, "Основание должно быть текстом / Негіздеме мәтін болуы керек")
    previous_label = _describe(current.position if current else employee.current_position,
                               current.org_unit if current else employee.current_org_unit)
    before = {"position": previous_label, "position_id": employee.current_position_id,
              "org_unit_id": employee.current_org_unit_id,
              "closed_work_experience_id": current.id if current else None,
              "closed_work_post": work_post_snapshot(current) if current else None,
              "closed_work_end": str(current.date_to) if current and current.date_to else None,
              "closed_disposal_id": open_disposal.id if open_disposal else None}

    if action == "disposal":
        if any(payload.get(k) is not None for k in ("result_id", "vacancy_id", "position_id", "org_unit_id")):
            raise HTTPException(422, "При выводе в распоряжение вакансия и должность не назначаются / Қарамағына шығарылғанда бос орын мен лауазым тағайындалмайды")
        if open_disposal:
            raise HTTPException(409, "Сотрудник уже находится в распоряжении / Қызметкер қазірдің өзінде қарамағында")
        row = DisposalPeriod(employee_id=employee_id, date_from=effective, reason=reason,
            org_unit_id=current.org_unit_id if current and current.org_unit_id is not None else employee.current_org_unit_id,
            previous_position_id=employee.current_position_id, previous_org_unit_id=employee.current_org_unit_id,
            closed_work_id=current.id if current else None, closed_work_end=current.date_to if current else None,
            closed_work_post=before["closed_work_post"])
        employee.current_position_id = employee.current_org_unit_id = None
        audit_values = {"effective_date": str(effective), "org_unit_id": row.org_unit_id}
        audit_id_key = "disposal_period_id"
    else:
        position = db.get(Position, payload.get("position_id")) if payload.get("position_id") else None
        unit = db.query(OrgUnit).filter_by(id=payload.get("org_unit_id")).with_for_update().first()
        if not position or not unit:
            raise HTTPException(422, "Укажите должность и подразделение / Лауазым мен бөлімшені көрсетіңіз")
        if payload.get("ignore_establishment") and not (reason or "").strip():
            raise HTTPException(422, "Для назначения вне штата укажите основание / Штаттан тыс тағайындау негізін көрсетіңіз")
        problem = check_vacancy_available(db, unit.id, position.id, exclude_employee_id=employee_id)
        if problem and not payload.get("ignore_establishment"):
            raise HTTPException(422, problem)
        row = WorkExperience(employee_id=employee_id, is_internal=True,
            org_unit_id=unit.id, position_id=position.id, job_family_id=position.job_family_id,
            org_unit_type_id=unit.unit_type_id, country_id=unit.country_id,
            management_level=position.management_level or 0, date_from=effective,
            appointment_type="appointment", source_vacancy_id=vacancy.id if vacancy else None,
            source_result_id=result.id if result else None)
        employee.current_position_id, employee.current_org_unit_id = position.id, unit.id
        audit_values = {"position": _describe(position, unit), "effective_date": str(effective),
                        "appointment_type": "appointment", "vacancy": vacancy.title if vacancy else None,
                        "off_establishment": bool(problem) or None}
        audit_id_key = "work_experience_id"
    if current:
        current.date_to = effective - timedelta(days=1)
    if open_disposal:
        open_disposal.date_to = effective - timedelta(days=1)
    db.add(row)
    try:
        db.flush()
        audit_values[audit_id_key] = row.id
        db.add(AuditLog(action=action, entity_type="employee", entity_id=employee_id,
                        old_values=before, new_values=audit_values, reason=reason, changed_by=actor))
        _save_transition(db, employee)
    except Exception:
        db.rollback()
        raise
    response = {"id": row.id, "employee_id": employee_id, "effective_date": str(effective), "appointment_type": action}
    if action == "appointment":
        response.update({"from": previous_label, "to": audit_values["position"],
                         "source_vacancy_id": row.source_vacancy_id, "source_result_id": row.source_result_id})
    return response


@router.get("/employees/{employee_id}/disposals")
def list_disposals(employee_id: int, request: Request, db: Session = Depends(get_db)):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, "Сотрудник не найден / Қызметкер табылмады")
    periods = db.query(DisposalPeriod).filter_by(employee_id=employee_id).order_by(DisposalPeriod.date_from.desc())
    admin = (getattr(request.state, "user", {}) or {}).get("role") == "admin"
    today = date.today()
    return {"data": [{"id": p.id, "date_from": p.date_from, "date_to": p.date_to,
        "org_unit_id": p.org_unit_id, "days": (min(p.date_to or today, today) - p.date_from).days + 1,
        "reason": p.reason if admin else None, "is_current": p.date_to is None,
        "can_undo": admin and disposal_undo_available(db, employee, p)} for p in periods]}


@router.delete("/employees/{employee_id}/disposals/{period_id}", status_code=204)
def undo_disposal(employee_id: int, period_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request)
    employee = lock_employee(db, employee_id)
    period = db.query(DisposalPeriod).filter_by(employee_id=employee_id, id=period_id).one_or_none()
    if not period or not employee:
        raise HTTPException(404, "Период распоряжения не найден / Қарамағында болу кезеңі табылмады")
    if not disposal_undo_available(db, employee, period):
        raise HTTPException(409, "Отмена невозможна после изменения истории или прежней должности / Тарих немесе бұрынғы лауазым өзгерген соң кері қайтару мүмкін емес")
    if period.closed_work_id:
        previous = next(r for r in employee.work_experience if r.id == period.closed_work_id)
        _check_restored_post(db, employee, previous, period.closed_work_end)
        previous.date_to = period.closed_work_end
    employee.current_position_id, employee.current_org_unit_id = period.previous_position_id, period.previous_org_unit_id
    db.add(AuditLog(action="disposal_undone", entity_type="employee", entity_id=employee_id,
                    old_values={"disposal_period_id": period.id, "date_from": str(period.date_from)},
                    new_values={"position_id": employee.current_position_id, "org_unit_id": employee.current_org_unit_id},
                    reason=request.query_params.get("reason"), changed_by=actor))
    db.delete(period)
    _save_transition(db, employee)


@router.get("/employees/{employee_id}/appointments")
def list_appointments(employee_id: int, request: Request, db: Session = Depends(get_db)):
    """The employee's career transitions, newest first."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Сотрудник не найден")

    rows = sorted(employee.work_experience, key=lambda r: (r.date_from, r.id), reverse=True)
    metadata = career_metadata(db, employee, is_admin=request.state.user.get("role") == "admin")
    return {"data": [{
        "id": r.id,
        "position": r.position.name_ru if r.position else r.external_position_title,
        "org_unit": r.org_unit.name_ru if r.org_unit else r.external_employer,
        "job_family": r.job_family.name_ru if r.job_family else None,
        "unit_type": r.org_unit_type.name_ru if r.org_unit_type else None,
        "country": r.country.name_ru if r.country else None,
        "date_from": str(r.date_from),
        "date_to": str(r.date_to) if r.date_to else None,
        "is_current": r.date_from <= date.today() and (r.date_to is None or r.date_to >= date.today()),
        **metadata[r.id],
        "appointment_type": r.appointment_type,  # preserve the legacy list response
    } for r in rows]}


@router.delete("/employees/{employee_id}/appointments/{row_id}",
               status_code=204)
def undo_appointment(employee_id: int, row_id: int, request: Request,
                     db: Session = Depends(get_db)):
    """Roll back the most recent appointment.

    Somebody will record a transfer against the wrong person or the wrong date,
    and until now there was no way back: the career record is what every tenure
    figure is computed from, so a bad row quietly poisons the scoring.

    Only the latest posting can be rolled back. Removing an earlier one would
    leave a hole in the middle of the timeline that nothing else in the system
    is prepared to interpret -- correcting those is an edit, not an undo.

    The posting this one superseded is reopened, so the employee lands back
    exactly where they stood before.
    """
    actor = _actor(request)
    employee = lock_employee(db, employee_id)
    if not employee:
        raise HTTPException(404, "Сотрудник не найден")

    row = next((r for r in employee.work_experience if r.id == row_id), None)
    if not row:
        raise HTTPException(404, "Запись трудовой деятельности не найдена")

    ordered = sorted((r for r in employee.work_experience if r.is_internal), key=lambda r: (r.date_from, r.id))
    if not ordered or not row.is_internal:
        raise HTTPException(409, "Это не внутреннее назначение / Бұл ішкі тағайындау емес")
    if ordered[-1].id != row.id:
        raise HTTPException(422, {
            "message": "Отменить можно только последнее назначение",
            "latest_from": str(ordered[-1].date_from),
            "hint": "Сначала отмените более поздние записи.",
        })

    event = appointment_events(db, employee).get(row.id)
    disposals = db.query(DisposalPeriod).filter_by(employee_id=employee_id).all()
    if not undo_available(row, event, employee, ordered[-1].id, disposals):
        raise HTTPException(409, "Чтобы отменить назначение, нужно точно установить прежнюю должность и период. История сохранена / Тағайындауды кері қайтару үшін алдыңғы лауазым мен кезең нақты белгілі болуы керек")
    if protected_period_ids(db, [row.id]):
        raise HTTPException(409, "Сначала перенесите вложения и дополнительные данные периода / Алдымен кезеңнің тіркемелері мен қосымша деректерін көшіріңіз")
    before = event.old_values
    previous = next((r for r in ordered if r.id == before["closed_work_experience_id"]), None)
    if ((before["position_id"] is not None and db.get(Position, before["position_id"]) is None)
            or (before["org_unit_id"] is not None and db.get(OrgUnit, before["org_unit_id"]) is None)):
        raise HTTPException(409, "Прежняя должность или подразделение удалены. Отмена невозможна / Алдыңғы лауазым немесе бөлімше жойылған")

    old_values = {
        "work_experience_id": row.id,
        "position": row.position.name_ru if row.position else None,
        "org_unit": row.org_unit.name_ru if row.org_unit else None,
        "date_from": str(row.date_from),
        "appointment_type": row.appointment_type,
    }

    prior_end = before.get("closed_work_end")
    original_end = date.fromisoformat(prior_end) if prior_end else None
    _check_restored_post(db, employee, previous, original_end)
    db.delete(row)
    if previous is not None:
        previous.date_to = original_end
    if before.get("closed_disposal_id") is not None:
        prior_disposal = next(p for p in disposals if p.id == before["closed_disposal_id"])
        prior_disposal.date_to = None
    employee.current_position_id = before["position_id"]
    employee.current_org_unit_id = before["org_unit_id"]

    db.add(AuditLog(
        action="appointment_undone", entity_type="employee",
        entity_id=employee_id,
        old_values=old_values,
        new_values={"position_id": before["position_id"], "org_unit_id": before["org_unit_id"]},
        reason=request.query_params.get("reason"),
        changed_by=actor,
    ))
    _save_transition(db, employee)


@router.post("/matching-results/{result_id}/appoint", status_code=201)
def appoint_from_shortlist(result_id: int, payload: Dict[str, Any],
                           request: Request, db: Session = Depends(get_db)):
    """Appoint the candidate behind a short-list row, straight from the result.

    Fills the destination from the vacancy when the caller does not override
    it, so the usual case is one click after the decision is recorded.
    """
    result = db.query(MatchingResult).filter(
        MatchingResult.id == result_id).first()
    if not result:
        raise HTTPException(404, "Результат подбора не найден")

    decision = db.query(Decision).filter(Decision.result_id == result_id).first()
    if not decision or decision.decision != "selected":
        raise HTTPException(422, {
            "message": "Назначение возможно только после решения «выбран»",
            "current_decision": decision.decision if decision else None,
        })

    vacancy = result.run.vacancy if result.run else None
    if not vacancy:
        raise HTTPException(422, "Вакансия не найдена для этого подбора")

    body = dict(payload or {})
    if body.get('vacancy_id') not in (None, vacancy.id) or body.get('result_id') not in (None, result_id):
        raise HTTPException(422, 'Назначение должно соответствовать выбранному результату и вакансии / Тағайындау таңдалған нәтижеге және бос орынға сәйкес болуы тиіс')
    body['vacancy_id'] = vacancy.id
    body['result_id'] = result_id
    body.setdefault("org_unit_id", vacancy.org_unit_id)
    if body.get("appointment_type") == "disposal":
        raise HTTPException(422, "По вакансии можно только назначить / Бос орын бойынша тек тағайындауға болады")
    body.setdefault("appointment_type", "appointment")
    body.setdefault("effective_date", str(date.today()))

    if not body.get("position_id"):
        raise HTTPException(422, {
            "message": "Укажите должность нового назначения",
            "hint": "Вакансия не привязана к конкретной записи справочника "
                    "должностей — выберите её вручную.",
        })

    return create_appointment(result.employee_id, body, request, db)
