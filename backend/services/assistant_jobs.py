"""A bounded single-worker queue for the two-user local workstation.

Requests survive browser navigation/reload. A backend restart marks unfinished
work as interrupted instead of silently pretending it is still running.
Run one API process; no external queue or service is required.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import threading
from uuid import uuid4

from database import SessionLocal
from models import AssistantRequest, AssistantConversation, AssistantReport, AuditLog, User
from services import assistant
from services.query_engine import build_field_catalogue, describe
from services.candidate_queries import uses_candidate, plan_visible, query_uses_confidential

executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-assistant")
submission_lock = threading.Lock()
ACTIVE = ("queued", "running")


def recover_interrupted():
    with SessionLocal() as db:
        db.query(AssistantRequest).filter(AssistantRequest.status.in_(ACTIVE)).update(
            {"status": "error", "error_code": "interrupted", "finished_at": datetime.utcnow()},
            synchronize_session=False)
        db.commit()


def execute(request_id):
    try:
        with SessionLocal() as db:
            # Compare-and-set prevents a concurrent cancellation from being
            # overwritten between reading queued and committing running.
            claimed = db.query(AssistantRequest).filter_by(id=request_id,status='queued').update(
                {'status':'running'}, synchronize_session=False)
            db.commit()
            if not claimed: return
            row = db.get(AssistantRequest, request_id)
            owner = db.query(User).filter_by(username=row.owner, is_active=True).first()
            if not owner:
                row.status, row.error_code, row.finished_at = "error", "account_unavailable", datetime.utcnow()
                db.commit(); return
            original_role = owner.role
            include_confidential = original_role == "admin"
            prompt, lang, model, kind = row.prompt, row.lang, row.model, row.kind
            context=[]; sources=[]; previous=None
            if kind == 'report':
                from services.assistant_reports import query_sources
                sources=[serialise(r, include_confidential=include_confidential) for r in query_sources(db,row.owner,row.conversation_id,include_confidential=include_confidential)]
            if row.conversation_id:
                prior=db.query(AssistantRequest).filter(
                    AssistantRequest.owner==row.owner, AssistantRequest.conversation_id==row.conversation_id,
                    AssistantRequest.id!=row.id, AssistantRequest.status=='ready',
                    AssistantRequest.created_at<=row.created_at).order_by(AssistantRequest.created_at.desc(),AssistantRequest.id.desc())
                # Formatting turns must not push the latest search out of the
                # context window, nor hide the last report's settings.
                queries=[r for r in prior.filter(AssistantRequest.kind=='query').limit(30).all() if plan_visible(r.plan, include_confidential)][:3]
                context=[{'prompt':r.prompt,**r.plan} for r in reversed(queries) if r.plan and 'definition' in r.plan]
                last_report=prior.filter(AssistantRequest.kind=='report').first()
                previous=last_report.plan.get('spec') if last_report and last_report.plan and plan_visible(last_report.plan, include_confidential) else None
            fields = build_field_catalogue(db, include_confidential=include_confidential) if kind!='report' else []
        if kind=='report':
            from services.assistant_reports import plan_report
            plan=plan_report(prompt,lang,sources,model=model,previous=previous)
        else:
            kwargs={'model':model}
            if context: kwargs['context']=context
            plan = assistant.interpret(prompt, lang, fields, **kwargs)
            plan['kind']='query'
            plan['confidential']=include_confidential and (uses_candidate(plan.get('definition')) or query_uses_confidential(plan.get('definition'), fields, plan.get('group_by')))
        if plan["status"] == "ready" and kind != 'report':
            plan["summaries"] = {language: describe(plan["definition"], fields, language) for language in ("ru", "kk")}
        with SessionLocal() as db:
            # A chat report is prepared by the worker, even after navigation or
            # browser closure. All source questions and personnel rows belong
            # to one consistent snapshot; the UI only downloads the result.
            if kind == 'report' and db.get_bind().dialect.name == 'postgresql':
                db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            row = db.get(AssistantRequest, request_id, with_for_update=True)
            if not row or row.status != "running": return  # a cancelled result stays cancelled
            owner = db.query(User).filter_by(username=row.owner, is_active=True).first()
            if not owner:
                row.status, row.error_code, row.finished_at = "error", "account_unavailable", datetime.utcnow()
                db.commit(); return
            if owner.role != original_role:
                row.status, row.error_code, row.finished_at = 'error', 'account_unavailable', datetime.utcnow()
                db.commit(); return
            if kind == 'report' and plan['status'] == 'ready':
                from services.assistant_reports import ReportSpec, snapshot_report
                try:
                    requested = ReportSpec.model_validate(plan['spec'])
                    spec, snapshot = snapshot_report(db, row.owner, row.conversation_id, requested, False, include_confidential=owner.role == "admin")
                except ValueError as exc:
                    # A valid formatting plan can still exceed the data limit.
                    # Ask for a narrower report rather than returning a broken file.
                    plan = {'status': 'clarify', 'kind': 'report', 'model': model, 'message': str(exc)}
                else:
                    report = AssistantReport(id=str(uuid4()), owner=row.owner,
                        conversation_id=row.conversation_id, request_id=row.id, title=spec.title,
                        spec=spec.model_dump(mode='json'), snapshot=snapshot)
                    db.add(report)
                    plan = {**plan, 'spec': report.spec, 'report_id': report.id,
                            'requested_names': 'name' in requested.columns, 'confidential': snapshot.get('confidential', False)}
                    db.add(AuditLog(action='report_generated', entity_type='analytics', changed_by=row.owner,
                        new_values={'questions': len(spec.source_ids), 'names_revealed': False}))
            row.plan, row.status, row.finished_at = plan, plan["status"], datetime.utcnow()
            db.add(AuditLog(action="assistant_query", entity_type="analytics", changed_by=row.owner,
                            new_values={"status":row.status, "model":row.model, "lang":row.lang}))
            db.commit()
    except Exception as exc:
        # Do not put prompts, stack traces or raw model responses into logs/UI.
        code = str(exc) if isinstance(exc, assistant.AssistantUnavailable) else "failed"
        with SessionLocal() as db:
            row = db.get(AssistantRequest, request_id, with_for_update=True)
            if row and row.status in ACTIVE:
                row.status, row.error_code, row.finished_at = "error", code, datetime.utcnow()
                db.commit()


def serialise(row, *, include_confidential=False):
    result = {key: getattr(row, key) for key in
            ("id", "conversation_id", "kind", "prompt", "lang", "model", "status", "plan", "error_code", "created_at", "finished_at")}

    if not plan_visible(row.plan, include_confidential):
        result['status'] = 'clarify'
        result['plan'] = {'status': 'clarify', 'kind': row.kind,
                          'message': 'Результат содержит закрытые оценки. Создайте новый запрос с текущими правами / Нәтижеде жабық бағалар бар. Ағымдағы құқықтармен жаңа сұрау жасаңыз'}
    return result
