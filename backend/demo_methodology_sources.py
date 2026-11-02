"""Add opt-in dossier/methodology examples to the exact 15-person synthetic demo.

Preview: python demo_methodology_sources.py
Apply after backup: python demo_methodology_sources.py --apply
No profiles, user drafts or historical assessments are deleted. Not a migration.
"""
import argparse
import json
import os
from copy import deepcopy
from decimal import Decimal
from sqlalchemy.engine import make_url
from models import (Employee, CandidateMethodology, CandidateEvaluation, CustomFieldDefinition,
                    CustomFieldValue, EducationLevel, Language, LanguageScale, LanguageLevel, AuditLog)
from candidate_schemas import CandidateMethodologyIn, CandidateEvaluationIn
from services import candidate_methodology as cm, candidate_sources as sources
from demo_candidates import NAMES

ACTOR='demo_sources_26'
TITLE_RU='Оценка по данным личного дела'
TITLE_KK='Жеке іс деректері бойынша бағалау'
FIELD_CODES=('demo26_project_role','demo26_certificate','demo26_project_count','demo26_sport')


def inspect_demo_sources(db):
    if os.getenv('APP_ENV')!='development':
        raise RuntimeError('Примеры разрешены только на демонстрационном стенде')
    people=db.query(Employee).order_by(Employee.personnel_number).all()
    if len(people)!=15 or [p.personnel_number for p in people]!=[f'DEMO-{i:03d}' for i in range(1,16)]:
        raise RuntimeError('Нужны ровно 15 известных демонстрационных профилей; данные не изменены')
    if any((p.last_name,p.first_name,p.middle_name)!=name for p,name in zip(people,NAMES)):
        raise RuntimeError('Демонстрационные профили изменены; автоматическое заполнение остановлено')
    previous=db.query(CandidateMethodology).filter_by(created_by=ACTOR).all()
    if previous:
        if len(previous)!=1:
            raise RuntimeError('Неоднозначные примеры методики; требуется ручная проверка')
        return {'already_prepared':True,'methodology_id':previous[0].id,'version':previous[0].version,
                'employees':15,'criteria':len(previous[0].criteria)}
    if db.query(CustomFieldDefinition).filter(CustomFieldDefinition.code.in_(FIELD_CODES)).count():
        raise RuntimeError('Коды полей примера уже используются; существующие поля сохранены')
    method=cm.get_method(db)
    if {c.position for c in method.criteria}!=set(range(3,47)) or any(c.source for c in method.criteria):
        raise RuntimeError('Начальная методика изменена. Новые примеры не применены автоматически')
    for person in people:
        evaluation=db.query(CandidateEvaluation).filter_by(employee_id=person.id,methodology_id=method.id).order_by(CandidateEvaluation.revision.desc()).first()
        if not evaluation or not cm.summarize(method,person,evaluation,include_confidential=True)['complete']:
            raise RuntimeError('Демонстрационная оценка заполнена не полностью; автоматическое продолжение остановлено')
    return {'already_prepared':False,'employees':15,'source_methodology_id':method.id,
            'source_version':method.version,'additional_fields':4,'criteria_after':45}


def prepare_demo_sources(db):
    before=inspect_demo_sources(db)
    if before['already_prepared']:
        return before
    original=cm.get_method(db,before['source_methodology_id'])
    definitions=[]
    specs=[
        ('Роль в проекте','Жобадағы рөлі','select',[
            {'value':'member','name_ru':'Участник','name_kk':'Қатысушы'},
            {'value':'coordinator','name_ru':'Координатор','name_kk':'Үйлестіруші'},
            {'value':'lead','name_ru':'Руководитель','name_kk':'Басшы'}]),
        ('Профильный сертификат','Бейіндік сертификат','boolean',[]),
        ('Завершённые проекты','Аяқталған жобалар','number',[]),
        ('Участие в спортивных мероприятиях','Спорттық іс-шараларға қатысу','boolean',[]),
    ]
    for index,(ru,kk,kind,options) in enumerate(specs):
        definition=CustomFieldDefinition(entity_type='employee',code=FIELD_CODES[index],name_ru=ru,name_kk=kk,
            field_type=kind,options=options,visibility='public',sort_order=100+index,
            help_text='Синтетический пример / Синтетикалық мысал')
        db.add(definition);definitions.append(definition)
    db.flush()
    draft=cm.clone_method(db,original.id,ACTOR)
    data=cm.method_dict(draft)
    criteria=[{k:row[k] for k in ('id','position','section_key','display_order','name_ru','name_kk','max_points','enabled','source')} for row in data['criteria']]
    by_position={row['position']:row for row in criteria}
    education={r.code:r.rank for r in db.query(EducationLevel)}
    language=db.query(Language).filter_by(code='EN').one()
    scale=db.query(LanguageScale).filter_by(code='CEFR').one()
    levels={r.code:r.rank for r in db.query(LanguageLevel).filter_by(scale_id=scale.id)}
    def rule(value,points,operator='eq'):
        return {'operator':operator,'value':value,'points':points}
    mappings=[
        (3,'Уровень образования','Білім деңгейі',15,{'kind':'dossier_fact','fact':'education_level','rules':[rule(education['BACHELOR'],10,'gte'),rule(education['MASTER'],15,'gte')]}),
        (4,'Подтверждённый английский язык','Расталған ағылшын тілі',20,{'kind':'dossier_fact','fact':'language_level','argument':language.id,'scale_id':scale.id,
            'rules':[rule(levels[key],points,'gte') for key,points in [('B1',5),('B2',10),('C1',15),('C2',20)]]}),
        (5,'Стаж в организации','Ұйымдағы еңбек өтілі',15,{'kind':'dossier_fact','fact':'company_experience_years','rules':[rule(3,5,'gte'),rule(5,10,'gte'),rule(10,15,'gte')]}),
        (6,specs[0][0],specs[0][1],20,{'kind':'dossier_field','field_id':definitions[0].id,'rules':[rule('member',5),rule('coordinator',10),rule('lead',20)]}),
        (7,specs[1][0],specs[1][1],10,{'kind':'dossier_field','field_id':definitions[1].id,'rules':[rule(True,10)]}),
        (8,specs[2][0],specs[2][1],10,{'kind':'dossier_field','field_id':definitions[2].id,'rules':[rule(1,5,'gte'),rule(3,10,'gte')]}),
    ]
    for position,ru,kk,maximum,source in mappings:
        by_position[position].update(name_ru=ru,name_kk=kk,max_points=maximum,source=source)
    data['sections'].append({'key':'sport','name_ru':'Спорт','name_kk':'Спорт','kind':'general','position':3})
    criteria.append({'position':47,'section_key':'sport','display_order':44,
        'name_ru':specs[3][0],'name_kk':specs[3][1],'max_points':5,'enabled':True,
        'source':{'kind':'dossier_field','field_id':definitions[3].id,'rules':[rule(True,5)]}})
    cm.update_method(db,draft.id,CandidateMethodologyIn(name_ru=TITLE_RU,name_kk=TITLE_KK,
        expected_revision=draft.revision,sections=data['sections'],criteria=criteria),ACTOR)
    cm.activate_method(db,draft.id,draft.revision,ACTOR)
    for index,person in enumerate(db.query(Employee).order_by(Employee.personnel_number).all(),1):
        values=[('value_text',['member','coordinator','lead'][index%3]),('value_bool',index%4!=0),
                ('value_number',index%6),('value_bool',index%2==0)]
        for definition,(column,value) in zip(definitions,values):
            db.add(CustomFieldValue(definition_id=definition.id,entity_type='employee',entity_id=person.id,**{column:value}))
        db.flush()
        previous=db.query(CandidateEvaluation).filter_by(employee_id=person.id,methodology_id=original.id).order_by(CandidateEvaluation.revision.desc()).first()
        old_points={s.criterion.position:s.points for s in previous.scores}
        body=CandidateEvaluationIn(methodology_id=draft.id,expected_revision=0,technical_profile=previous.technical_profile,
            scores=[{'position':c.position,'points':old_points[c.position]} for c in cm.applicable(draft.criteria,previous.technical_profile,True) if not c.source],
            note='Синтетический пример расчёта по данным личного дела; прежние оценки сохранены.')
        calculated=sources.preview(db,person.id,body)
        if not calculated['summary']['complete']:
            raise RuntimeError('Для примера не хватает исходных фактов; изменения отменены')
        body.source_fingerprint=calculated['source_fingerprint'];body.confirm_sources=True
        cm.save_evaluation(db,person.id,body,ACTOR)
    after={'already_prepared':False,'methodology_id':draft.id,'version':draft.version,'employees':15,
           'criteria':len(draft.criteria),'additional_fields':4,'new_evaluations':15}
    db.add(AuditLog(action='prepare_demo',entity_type='candidate_sources',entity_id=draft.id,
        old_values=before,new_values=after,changed_by=ACTOR))
    db.flush()
    return after


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    from database import SessionLocal, DATABASE_URL
    if os.getenv('APP_ENV')!='development' or make_url(DATABASE_URL).database!='emp_profile_test':
        raise RuntimeError('Нужен локальный синтетический стенд emp_profile_test; рабочая база не изменена')
    with SessionLocal() as db:
        try:
            result=prepare_demo_sources(db) if args.apply else inspect_demo_sources(db)
            if args.apply:db.commit()
            print(json.dumps(result,ensure_ascii=False,indent=2))
        except Exception:
            db.rollback();raise


if __name__=='__main__':main()
