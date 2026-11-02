from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response
from uuid import uuid4
from copy import deepcopy
import re
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from database import get_db
from models import AuditLog, AssistantRequest, AssistantConversation, AssistantReport
from services import assistant_jobs as jobs
from services.query_engine import build_field_catalogue, run_query, describe
from services import assistant
from services.candidate_queries import uses_candidate, plan_visible, query_uses_confidential
from services.assistant_reports import ReportSpec, snapshot_report, wants_report

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


def _include_confidential(request):
    return request.state.user.get('role') == 'admin'



class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=2000)
    lang: Literal["ru", "kk"] = "ru"


class QueuedPrompt(Prompt):
    request_id: UUID
    model: Literal["qwen3:1.7b-q4_K_M", "qwen3:4b-instruct-2507-q4_K_M", "qwen3:14b-q4_K_M"] | None = None
    conversation_id: UUID | None = None
    mode: Literal['auto','query','report'] = 'auto'


class NewConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: UUID
    title: str = Field(default='Новый диалог / Жаңа диалог',min_length=1,max_length=160)


def own_conversation(db, owner, identity):
    row=db.get(AssistantConversation,str(identity))
    if not row or row.owner!=owner: raise HTTPException(404,'Диалог не найден / Диалог табылмады')
    return row


def conversation_data(row):
    return {key:getattr(row,key) for key in ('id','title','created_at','updated_at')}


@router.get('/conversations')
def conversations(request: Request, db: Session = Depends(get_db),
                  limit: Annotated[int, Query(ge=1,le=100)] = 100, offset: Annotated[int, Query(ge=0)] = 0):
    query=db.query(AssistantConversation).filter_by(owner=request.state.user['sub'])
    rows=query.order_by(AssistantConversation.updated_at.desc(),AssistantConversation.id).offset(offset).limit(limit).all()
    return {'data':[conversation_data(r) for r in rows],'total':query.count()}


@router.post('/conversations', status_code=201)
def create_conversation(payload: NewConversation, request: Request, db: Session = Depends(get_db)):
    owner=request.state.user['sub']; identity=str(payload.conversation_id)
    with jobs.submission_lock:
        existing=db.get(AssistantConversation,identity)
        if existing:
            if existing.owner!=owner: raise HTTPException(404,'Диалог не найден / Диалог табылмады')
            return conversation_data(existing)
        row=AssistantConversation(id=identity,owner=owner,title=payload.title.strip() or 'Диалог / Диалог')
        db.add(row); db.commit(); db.refresh(row)
        return conversation_data(row)


@router.get("/requests")
def history(request: Request, limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0), db: Session = Depends(get_db), conversation_id: UUID | None = None):
    query = db.query(AssistantRequest).filter_by(owner=request.state.user["sub"])
    active_count=query.filter(AssistantRequest.status.in_(jobs.ACTIVE)).count()
    if conversation_id:
        own_conversation(db,request.state.user['sub'],conversation_id)
        query=query.filter_by(conversation_id=str(conversation_id))
    rows = query.order_by(AssistantRequest.created_at.desc(), AssistantRequest.id).offset(offset).limit(limit).all()
    return {"data": [jobs.serialise(row, include_confidential=_include_confidential(request)) for row in rows], "total": query.count(), 'active_count':active_count}


@router.post("/requests", status_code=202)
def submit(payload: QueuedPrompt, request: Request, db: Session = Depends(get_db)):
    owner, identity = request.state.user["sub"], str(payload.request_id)
    prompt = payload.text.strip()
    if len(prompt) < 3:
        raise HTTPException(422, "Уточните запрос / Сұрауды нақтылаңыз")
    with jobs.submission_lock:
        existing = db.get(AssistantRequest, identity)
        if existing:
            if existing.owner != owner: raise HTTPException(404, "Запрос не найден / Сұрау табылмады")
            return jobs.serialise(existing, include_confidential=_include_confidential(request))  # retry after a lost HTTP response is safe
        if db.query(AssistantRequest).filter(AssistantRequest.owner == owner, AssistantRequest.status.in_(jobs.ACTIVE)).count() >= 3:
            raise HTTPException(429, "У вас уже три активных запроса / Үш белсенді сұрауыңыз бар")
        conversation=None
        if payload.conversation_id:
            conversation=own_conversation(db,owner,payload.conversation_id)
            if db.query(AssistantRequest).filter(AssistantRequest.conversation_id==conversation.id,AssistantRequest.status.in_(jobs.ACTIVE)).count():
                raise HTTPException(409,'Дождитесь ответа в этом диалоге или создайте новый / Осы диалогта жауапты күтіңіз немесе жаңасын жасаңыз')
            conversation.updated_at=datetime.utcnow()
            if not db.query(AssistantRequest).filter_by(conversation_id=conversation.id).count(): conversation.title=prompt[:160]
        kind='report' if payload.mode=='report' or (payload.mode=='auto' and wants_report(prompt)) else 'query'
        if payload.mode=='auto' and conversation and kind=='query':
            last=db.query(AssistantRequest).filter_by(conversation_id=conversation.id,status='ready').order_by(AssistantRequest.created_at.desc()).first()
            explicit_query = re.search(r'\b(сколько|қанша|неше|найди(?:те)?|подбери(?:те)?|отбери(?:те)?|перечисли(?:те)?|тап|ізде)\b', prompt, re.I)
            if last and last.kind=='report' and not explicit_query and re.search(r'альбом|книжн|столб|колон|сводк|заголов|оформ|цвет|зел[её]н|син(?:ий|им|его)|ч[её]рно.бел|көк|жасыл|баған|тақырып|пішім|альбомдық|кітаптық|ақ.қара',prompt,re.I): kind='report'
        row = AssistantRequest(id=identity, owner=owner, prompt=prompt, lang=payload.lang,
                               model=payload.model or assistant.MODEL, status="queued",kind=kind,
                               conversation_id=conversation.id if conversation else None)
        db.add(row); db.commit(); db.refresh(row)
        result = jobs.serialise(row, include_confidential=_include_confidential(request))
        jobs.executor.submit(jobs.execute, identity)
        return result


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: UUID, request: Request, db: Session = Depends(get_db)):
    row = db.get(AssistantRequest, str(request_id), with_for_update=True)
    if not row or row.owner != request.state.user["sub"]:
        raise HTTPException(404, "Запрос не найден / Сұрау табылмады")
    if row.status in jobs.ACTIVE:
        row.status, row.finished_at = "cancelled", datetime.utcnow()
        db.commit()
    return jobs.serialise(row, include_confidential=_include_confidential(request))


class CorrectConditions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    definition: dict
    group_by: str | None = None


@router.post('/requests/{request_id}/conditions')
def correct_conditions(request_id: UUID, payload: CorrectConditions, request: Request, db: Session = Depends(get_db)):
    with jobs.submission_lock:
        return _correct_conditions(request_id,payload,request,db)


def _correct_conditions(request_id, payload, request, db):
    owner=request.state.user['sub']
    row=db.get(AssistantRequest,str(request_id),with_for_update=True)
    if not row or row.owner!=owner: raise HTTPException(404,'Запрос не найден / Сұрау табылмады')
    if not plan_visible(row.plan, _include_confidential(request)):
        raise HTTPException(403, 'Запрос содержит закрытые оценки / Сұрауда жабық бағалар бар')
    if row.kind!='query' or row.status!='ready':
        raise HTTPException(409,'Исправлять можно готовые условия поиска / Дайын іздеу шарттарын ғана түзетуге болады')
    if row.conversation_id and db.query(AssistantRequest).filter(
        AssistantRequest.conversation_id==row.conversation_id,AssistantRequest.status.in_(jobs.ACTIVE)).count():
        raise HTTPException(409,'Дождитесь ответа в этом диалоге / Осы диалогта жауапты күтіңіз')
    fields=build_field_catalogue(db, include_confidential=_include_confidential(request))
    try:
        # Validate with the same engine as analytics, without loading people.
        run_query(db,payload.definition,fields,payload.group_by,population={'employees':[],'metrics':{},'custom':{},'include_confidential':_include_confidential(request)},include_confidential=_include_confidential(request))
    except ValueError as exc: raise HTTPException(422,str(exc))
    definition={'match':payload.definition.get('match','all'),
                'conditions':[{key:value for key,value in condition.items() if key in ('field','operator','argument','value')}
                              for condition in payload.definition.get('conditions',[]) or []]}
    summaries={language:describe(definition,fields,language) for language in ('ru','kk')}
    row.plan={**row.plan,'definition':definition,'group_by':payload.group_by,
              'summaries':summaries,'summary':summaries[row.lang],'reviewed':True,
              'confidential':_include_confidential(request) and (uses_candidate(definition) or query_uses_confidential(definition, fields, payload.group_by))}
    db.add(AuditLog(action='assistant_conditions',entity_type='analytics',changed_by=owner,
                    new_values={'conditions':len(definition['conditions'])}))
    db.commit(); db.refresh(row)
    return jobs.serialise(row, include_confidential=_include_confidential(request))


@router.get("/status")
def status():
    return assistant.status()


class ReportPreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    spec: ReportSpec
    reveal_names: bool = False


def own_report(db, owner, identity, *, include_confidential=False):
    row=db.get(AssistantReport,str(identity))
    if not row or row.owner!=owner: raise HTTPException(404,'Отчёт не найден / Есеп табылмады')
    if not plan_visible(row.snapshot, include_confidential):
        raise HTTPException(403, 'Отчёт содержит закрытые оценки / Есепте жабық бағалар бар')
    return row


def report_data(row):
    snapshot=deepcopy(row.snapshot)
    for section in snapshot['sections']: section['rows']=section['rows'][:8]
    return {'id':row.id,'created_at':row.created_at,'spec':row.spec,'snapshot':snapshot,'request_id':row.request_id}


@router.post('/reports/preview')
def preview_report(payload: ReportPreview, request: Request, db: Session = Depends(get_db)):
    # All source filters, rows and eager-loaded relations belong to one database
    # snapshot even if the second operator edits a profile during preparation.
    if db.get_bind().dialect.name=='postgresql':
        db.connection(execution_options={'isolation_level':'REPEATABLE READ'})
    owner=request.state.user['sub']; source=db.get(AssistantRequest,str(payload.request_id))
    if not source or source.owner!=owner: raise HTTPException(404,'Запрос не найден / Сұрау табылмады')
    if source.kind!='report' or source.status!='ready': raise HTTPException(409,'Сначала подготовьте план отчёта / Алдымен есеп жоспарын дайындаңыз')
    try: spec,snapshot=snapshot_report(db,owner,source.conversation_id,payload.spec,payload.reveal_names,include_confidential=_include_confidential(request))
    except ValueError as exc: raise HTTPException(422,str(exc))
    row=AssistantReport(id=str(uuid4()),owner=owner,conversation_id=source.conversation_id,
                        request_id=source.id,title=spec.title,spec=spec.model_dump(mode='json'),snapshot=snapshot)
    db.add(row)
    db.add(AuditLog(action='report_preview',entity_type='analytics',changed_by=owner,
                    new_values={'questions':len(spec.source_ids),'names_revealed':snapshot['reveal_names']}))
    db.commit(); db.refresh(row)
    return report_data(row)


@router.get('/reports')
def report_history(request: Request, db: Session = Depends(get_db), conversation_id: UUID | None = None,
                   request_id: UUID | None = None, limit: Annotated[int, Query(ge=1,le=100)] = 50,
                   offset: Annotated[int, Query(ge=0)] = 0):
    owner=request.state.user['sub']; query=db.query(AssistantReport).filter_by(owner=owner)
    if conversation_id:
        own_conversation(db,owner,conversation_id); query=query.filter_by(conversation_id=str(conversation_id))
    if request_id: query=query.filter_by(request_id=str(request_id))
    if not _include_confidential(request):
        # Filter before counting/pagination: even a report title or an empty
        # page could disclose the existence of a closed assessment snapshot.
        query=query.filter(AssistantReport.snapshot['confidential'].as_boolean().is_not(True))
    return {'data':[{key:getattr(row,key) for key in ('id','title','created_at','request_id')}
                    for row in query.order_by(AssistantReport.created_at.desc(),AssistantReport.id).offset(offset).limit(limit)],'total':query.count()}


@router.get('/reports/{report_id}')
def get_report(report_id: UUID, request: Request, db: Session = Depends(get_db)):
    return report_data(own_report(db,request.state.user['sub'],report_id,include_confidential=_include_confidential(request)))


@router.post('/reports/{report_id}/document')
def report_document(report_id: UUID, request: Request, db: Session = Depends(get_db)):
    owner=request.state.user['sub']; row=own_report(db,owner,report_id,include_confidential=_include_confidential(request))
    from services.report_documents import render_report_docx
    blob=render_report_docx(row.snapshot,row.spec)
    db.add(AuditLog(action='export_report',entity_type='analytics',changed_by=owner,
                   new_values={'report_id':row.id,'names_revealed':row.snapshot['reveal_names'],'format':'docx'}))
    db.commit()
    return Response(blob,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition':f'attachment; filename="Report_{row.id[:8]}.docx"','Cache-Control':'no-store'})


@router.post("/interpret")
def interpret(payload: Prompt, request: Request, db: Session = Depends(get_db)):
    try:
        fields = build_field_catalogue(db,include_confidential=_include_confidential(request))
        plan = assistant.interpret(payload.text.strip(), payload.lang, fields)
    except assistant.AssistantUnavailable as exc:
        messages = {
            "busy": ("Помощник занят другим запросом. Повторите чуть позже.", "Көмекші басқа сұрауды өңдеуде. Кейінірек қайталаңыз."),
            "invalid_plan": ("Не удалось однозначно распознать условия. Уточните запрос или используйте конструктор.", "Шарттарды анықтау мүмкін болмады. Сұрауды нақтылаңыз немесе құрастырғышты пайдаланыңыз."),
        }
        pair = messages.get(str(exc), ("Локальная модель недоступна. Обычный поиск продолжает работать.", "Жергілікті модель қолжетімсіз. Қалыпты іздеу жұмыс істейді."))
        raise HTTPException(503, pair[1 if payload.lang == "kk" else 0])
    plan["confidential"] = _include_confidential(request) and (uses_candidate(plan.get("definition")) or query_uses_confidential(plan.get("definition"), fields, plan.get("group_by")))
    db.add(AuditLog(action="assistant_query", entity_type="analytics",
                    changed_by=request.state.user["sub"],
                    new_values={"status": plan["status"], "model": assistant.MODEL,
                                "lang": payload.lang}))
    db.commit()
    return plan
