"""Explicit replacement of one verified synthetic vacancy with three examples.

Never called by migrations or normal startup. Run only after the dossier demo
has been prepared and a local backup has been verified: python demo_vacancies.py --apply
"""
import argparse
import hashlib
import json
import os
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from models import (Vacancy, Employee, CandidateMethodology, CandidateEvaluation,
                    MatchingRun, WorkExperience, Country, OrgUnit, AuditLog)
from services.candidate_methodology import summarize

LEGACY_ID = 1
LEGACY_FINGERPRINT = '046146264ad87b549906834ed7eda0554fadeb2086f924b5faefc52542a31a37'
AUDIT_ACTION = 'demo_vacancies_26'
DEMO_METHOD_NAME = 'Оценка по данным личного дела'
EXAMPLES = (
    {'country':'DE', 'title':'Представитель — Германия', 'title_kk':'Өкіл — Германия',
     'min_candidate_percent':65, 'requires_technical_profile':False,
     'description':'Пример общей оценки кандидатов в заграничное представительство. Порог — 65%.',
     'description_kk':'Шетелдік өкілдікке үміткерлерді жалпы бағалау мысалы. Шек — 65%.'},
    {'country':'JP', 'title':'Технический специалист — Япония', 'title_kk':'Техникалық маман — Жапония',
     'min_candidate_percent':70, 'requires_technical_profile':True,
     'description':'Пример оценки технического специалиста. Нужны технический профиль, полная оценка и не менее 70%.',
     'description_kk':'Техникалық маманды бағалау мысалы. Техникалық бейін, толық баға және кемінде 70% қажет.'},
    {'country':'AE', 'title':'Координатор представительства — ОАЭ', 'title_kk':'Өкілдік үйлестірушісі — БАӘ',
     'min_candidate_percent':75, 'requires_technical_profile':False,
     'description':'Пример вакансии с повышенным порогом общей оценки — 75%.',
     'description_kk':'Жалпы бағалау шегі жоғары бос орын мысалы — 75%.'},
)


def guard_database(db):
    url = db.get_bind().url
    if (os.getenv('APP_ENV') != 'development' or url.get_backend_name() != 'postgresql'
            or url.database != 'emp_profile_test'):
        raise RuntimeError('Разрешено только для явно выбранного демонстрационного emp_profile_test')


def legacy_fingerprint(vacancy):
    payload = {'id':vacancy.id, 'title':vacancy.title, 'description':vacancy.description,
        'status':vacancy.status, 'profile_id':vacancy.profile_id,
        'profile_code':vacancy.profile.code if vacancy.profile else None,
        'country_id':vacancy.country_id, 'country_code':vacancy.country.code if vacancy.country else None,
        'org_unit_id':vacancy.org_unit_id, 'org_unit_code':vacancy.org_unit.code if vacancy.org_unit else None,
        'requirements_version':vacancy.requirements_version,
        'requirements':[{'kind':r.requirement_type.code, 'label_ru':r.label_ru,
            'label_kk':r.label_kk, 'label_en':r.label_en, 'condition':r.condition,
            'weight':r.weight, 'criticality':r.criticality,
            'function':r.scoring_function.code if r.scoring_function else None,
            'compensation':r.compensation_table.code if r.compensation_table else None,
            'sort_order':r.sort_order} for r in vacancy.requirements]}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def inspect_fixture(db):
    existing = db.query(AuditLog).filter_by(action=AUDIT_ACTION).order_by(AuditLog.id.desc()).first()
    if existing:
        ids = (existing.new_values or {}).get('vacancy_ids', [])
        if len(ids) != 3 or db.query(Vacancy).filter(Vacancy.id.in_(ids)).count() != 3:
            raise RuntimeError('Ранее созданные примеры изменены или удалены; повторная замена запрещена')
        return {'already_applied':True, 'vacancy_ids':ids}
    old = db.query(Vacancy).filter_by(id=LEGACY_ID).with_for_update().first()
    if not old or old.candidate_methodology_id or old.title_kk or old.description_kk or legacy_fingerprint(old) != LEGACY_FINGERPRINT:
        raise RuntimeError('Прежняя вакансия не совпадает с проверенным демонстрационным образцом; изменения отменены')
    if db.query(MatchingRun).filter_by(vacancy_id=old.id).count() or db.query(WorkExperience).filter_by(source_vacancy_id=old.id).count():
        raise RuntimeError('Вакансия уже имеет историю подбора или назначения; удаление запрещено')
    people = db.query(Employee).filter(Employee.personnel_number.in_([f'DEMO-{i:03}' for i in range(1,16)])).all()
    if len(people) != 15:
        raise RuntimeError('Нужны 15 известных синтетических личных дел DEMO-001…DEMO-015')
    method = db.query(CandidateMethodology).filter_by(status='active').first()
    if (not method or method.name_ru != DEMO_METHOD_NAME
            or not any((c.source or {}).get('kind') in ('dossier_field','dossier_fact') for c in method.criteria)):
        raise RuntimeError('Сначала подготовьте демонстрационную методику и оценки из личных дел')
    latest = (db.query(func.max(CandidateEvaluation.id).label('id'))
              .filter(CandidateEvaluation.methodology_id==method.id,
                      CandidateEvaluation.employee_id.in_([e.id for e in people]))
              .group_by(CandidateEvaluation.employee_id).subquery())
    evaluations = db.query(CandidateEvaluation).join(latest,CandidateEvaluation.id==latest.c.id).options(selectinload(CandidateEvaluation.scores)).all()
    index = {e.employee_id:e for e in evaluations}
    if len(index) != 15 or not all(summarize(method,p,index.get(p.id),include_confidential=True)['complete'] for p in people):
        raise RuntimeError('Перед созданием вакансий подтвердите полные оценки всех 15 демонстрационных сотрудников')
    countries = {r.code:r for r in db.query(Country).filter(Country.code.in_([e['country'] for e in EXAMPLES]))}
    units = {r.code:r for r in db.query(OrgUnit).filter(OrgUnit.code.in_(['FOREIGN_'+e['country'] for e in EXAMPLES]))}
    if len(countries) != 3 or len(units) != 3:
        raise RuntimeError('Для примеров нужны страны и представительства Германии, Японии и ОАЭ')
    if any(db.query(Vacancy).filter_by(title=e['title']).count() for e in EXAMPLES):
        raise RuntimeError('Вакансия с названием примера уже существует; автоматическая замена запрещена')
    return {'already_applied':False, 'old':old, 'method':method, 'countries':countries,'units':units}


def replace_examples(db, *, apply=False):
    guard_database(db)
    fixture = inspect_fixture(db)
    if fixture['already_applied']:
        return fixture
    if not apply:
        return {'ready':True, 'remove_vacancy_id':fixture['old'].id,
                'methodology_id':fixture['method'].id, 'examples':[e['title'] for e in EXAMPLES]}
    created = []
    for example in EXAMPLES:
        row = Vacancy(**{k:v for k,v in example.items() if k != 'country'},
            country_id=fixture['countries'][example['country']].id,
            org_unit_id=fixture['units']['FOREIGN_'+example['country']].id,
            candidate_methodology_id=fixture['method'].id, status='active', requirements_version=1)
        db.add(row); created.append(row)
    db.flush()
    removed = fixture['old'].id
    db.delete(fixture['old'])
    result = {'removed_vacancy_id':removed, 'vacancy_ids':[v.id for v in created],
              'methodology_id':fixture['method'].id}
    db.add(AuditLog(action=AUDIT_ACTION, entity_type='vacancy', entity_id=removed,
        old_values={'id':removed,'fingerprint':LEGACY_FINGERPRINT}, new_values=result,
        changed_by='demo-2.6.0'))
    db.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    from database import SessionLocal
    with SessionLocal() as db:
        try:
            print(json.dumps(replace_examples(db,apply=args.apply),ensure_ascii=False,indent=2))
        except Exception:
            db.rollback()
            raise


if __name__ == '__main__':
    main()
