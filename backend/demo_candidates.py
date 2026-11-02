"""Explicit reset of the local synthetic demonstration; never production.

Preview: python demo_candidates.py
Apply after a complete backup: python demo_candidates.py --apply
The CLI accepts only APP_ENV=development and the dedicated emp_profile_test DB.
It preserves accounts, references, vacancies and audit history. It is not a migration.
"""
import argparse
from datetime import date
from decimal import Decimal
import json
import os

from sqlalchemy import delete
from models import (Base, Employee, EmployeeEducation, EmployeeLanguage,
                    EmployeeTraining, WorkExperience, Country, Language,
                    LanguageScale, LanguageLevel, EducationLevel, EducationField,
                    TrainingType, OrgUnit, Position, PositionGrade, JobFamily,
                    StaffingPosition, AssistantRequest, CustomFieldValue,
                    Attachment, AuditLog, ATTACHABLE_ENTITIES)
from candidate_schemas import CandidateEvaluationIn
from services.candidate_methodology import seed_candidate_methodology, save_evaluation
from services.metrics import compute_metrics_bulk, _store_metrics


NAMES = [
    ('Ахметова', 'Айдана', 'Сериковна'), ('Иванов', 'Алексей', 'Андреевич'),
    ('Садыков', 'Нурлан', 'Ерланович'), ('Петрова', 'Мария', 'Викторовна'),
    ('Омарова', 'Динара', 'Муратовна'), ('Ким', 'Данияр', 'Александрович'),
    ('Толеубекова', 'Аружан', 'Болатовна'), ('Смирнов', 'Дмитрий', 'Игоревич'),
    ('Жумабаев', 'Алихан', 'Русланович'), ('Соколова', 'Елена', 'Павловна'),
    ('Исмаилова', 'Мадина', 'Рустемовна'), ('Козлов', 'Артём', 'Сергеевич'),
    ('Серикова', 'Асем', 'Нурлановна'), ('Волков', 'Михаил', 'Олегович'),
    ('Бекенов', 'Темирлан', 'Даниярович'),
]


def inspect_demo(db):
    if os.getenv('APP_ENV') != 'development':
        raise RuntimeError('Сброс разрешён только на демонстрационном стенде')
    employees = db.query(Employee).all()
    numbers = {row.personnel_number for row in employees}
    allowed = ({f'TN-{i:04d}' for i in range(1, 6)},
               {f'DEMO-{i:03d}' for i in range(1, 16)}, set())
    if numbers not in allowed or len(numbers) != len(employees):
        raise RuntimeError('Найдены неизвестные сотрудники. Автоматический сброс остановлен')
    if db.query(AssistantRequest).filter(AssistantRequest.status.in_(['queued', 'running'])).count():
        raise RuntimeError('Дождитесь завершения запросов помощника')
    centre = db.query(OrgUnit).filter_by(code='CENTRE_14').first()
    # Both releases used the same code. Only a stock, childless fixture may be removed.
    if centre and (centre.children or centre.unit_type.code != 'CENTRE'
                   or centre.name_ru not in ('Центр 14', 'Подразделение 14')
                   or centre.name_kk not in (None, '14-орталық', '14-бөлімше')
                   or centre.name_en not in (None, 'Centre 14', 'Unit 14')):
        raise RuntimeError('Подразделение 14 изменено пользователем. Автоматическое удаление остановлено')
    return {'employees': len(employees), 'centre_14_present': centre is not None}


def seed_demo_candidates(db):
    """Fill an empty demonstration with 15 varied, explicitly synthetic profiles."""
    if db.query(Employee).count():
        raise RuntimeError('Новые демонстрационные сотрудники создаются только в пустом списке')
    countries = {r.code: r for r in db.query(Country)}
    units = {r.code: r for r in db.query(OrgUnit)}
    families = {r.code: r for r in db.query(JobFamily)}
    grade = db.query(PositionGrade).filter_by(code='SPECIALIST').one()
    for code, ru, kk, family in [
        ('DEMO_ENGINEER', 'Инженер технических систем', 'Техникалық жүйелер инженері', 'IT'),
        ('DEMO_FINANCE', 'Финансовый специалист', 'Қаржы маманы', 'FINANCE'),
    ]:
        if not db.query(Position).filter_by(code=code).first():
            db.add(Position(code=code, name_ru=ru, name_kk=kk,
                            job_family_id=families[family].id, grade_id=grade.id))
    db.flush()
    positions = {r.code: r for r in db.query(Position)}
    languages = {r.code: r for r in db.query(Language)}
    scale = db.query(LanguageScale).filter_by(code='CEFR').one()
    levels = {r.code: r for r in db.query(LanguageLevel).filter_by(scale_id=scale.id)}
    education_levels = {r.code: r for r in db.query(EducationLevel)}
    fields = {r.code: r for r in db.query(EducationField)}
    training = db.query(TrainingType).filter_by(code='COURSE').one()
    method = seed_candidate_methodology(db)
    created = []
    for i, (last, first, middle) in enumerate(NAMES, 1):
        unit = units[f'CENTRE_{i:02d}'] if i <= 12 else units[['FOREIGN_DE', 'FOREIGN_US', 'FOREIGN_JP'][i - 13]]
        position = positions[['MKT_SPEC', 'ANALYST', 'OPS_SPEC', 'DEMO_ENGINEER', 'DEMO_FINANCE'][(i - 1) % 5]]
        family = position.job_family
        technical = family.code in ('IT', 'ANALYTICS')
        hired = date(2010 + i % 8, 4, 1)
        employee = Employee(personnel_number=f'DEMO-{i:03d}', anonymous_code=f'DEMO-{i:03d}',
            last_name=last, first_name=first, middle_name=middle,
            birth_date=date(1980 + i, 1 + i % 12, 5 + i % 20),
            birth_place='Демонстрационные данные', birth_country_id=countries['KZ'].id,
            email=f'demo{i:03d}@example.invalid', hire_date=hired,
            current_org_unit_id=unit.id, current_position_id=position.id,
            employment_status='active', profile_status='verified',
            verified_by='demo_seed', is_technical_specialist=technical)
        db.add(employee)
        db.flush()
        education_country = ['KZ', 'DE', 'FR', 'US', 'JP', 'CN', 'SG'][(i - 1) % 7]
        field = fields['CS' if technical else 'FINANCE' if family.code == 'FINANCE' else 'MARKETING']
        db.add(EmployeeEducation(employee_id=employee.id,
            level_id=education_levels['MASTER' if i % 3 == 0 else 'BACHELOR'].id,
            institution=f'Демонстрационный университет {education_country}',
            country_id=countries[education_country].id, field_id=field.id,
            start_year=hired.year - 4, end_year=hired.year - 1,
            qualification='Учебный пример квалификации'))
        db.add(WorkExperience(employee_id=employee.id, is_internal=True,
            org_unit_id=unit.id, position_id=position.id, job_family_id=family.id,
            org_unit_type_id=unit.unit_type_id, country_id=unit.country_id,
            date_from=hired, appointment_type='initial'))
        for language, level in [('KK', 'C1'), ('RU', 'C1'), ('EN', ['B1', 'B2', 'C1'][i % 3])]:
            db.add(EmployeeLanguage(employee_id=employee.id, language_id=languages[language].id,
                scale_id=scale.id, level_id=levels[level].id, is_confirmed=True,
                document='Демонстрационный сертификат', confirmed_at=date(2026, 1, 15),
                valid_until=date(2030, 1, 15)))
        if i % 4 == 0:
            db.add(EmployeeLanguage(employee_id=employee.id, language_id=languages['DE'].id,
                scale_id=scale.id, level_id=levels['B2'].id, is_confirmed=True,
                document='Демонстрационный сертификат', valid_until=date(2030, 1, 15)))
        db.add(EmployeeTraining(employee_id=employee.id, name='Международное деловое взаимодействие',
            training_type_id=training.id, job_family_id=family.id, provider='Демонстрационный учебный центр',
            date_from=date(2025, 9, 1), date_to=date(2025, 9, 15), result='Учебный пример'))
        if not db.query(StaffingPosition).filter_by(org_unit_id=unit.id, position_id=position.id).first():
            db.add(StaffingPosition(org_unit_id=unit.id, position_id=position.id,
                                   headcount=1, grade_id=position.grade_id, notes='Демонстрационное штатное место'))
        db.flush()
        ratio = Decimal(55 + (i * 7) % 41) / Decimal(100)
        scores = [{'position': c.position, 'points': (c.max_points * ratio).quantize(Decimal('.01'))}
                  for c in method.criteria if c.enabled and (technical or c.block != 'technical')]
        save_evaluation(db, employee.id, CandidateEvaluationIn(methodology_id=method.id,
            expected_revision=0, technical_profile=technical, scores=scores,
            note='Синтетический пример для проверки интерфейса. Не является оценкой реального человека.'), 'demo_seed')
        created.append(employee)
    db.flush()
    metrics = compute_metrics_bulk(db, created)
    for employee in created:
        _store_metrics(db, employee, metrics[employee.id])
    db.flush()
    return created


def replace_demo(db):
    before = inspect_demo(db)
    # Resolve all descendants by declared foreign keys; no cascade reaches
    # accounts, references, vacancies or the audit trail, which are parents.
    names = {'employees', 'matching_runs', 'assistant_conversations', 'candidate_methodologies'}
    while True:
        dependent = {t.name for t in Base.metadata.tables.values()
                     if any(fk.column.table.name in names for fk in t.foreign_keys)}
        if dependent <= names:
            break
        names |= dependent
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in names:
            db.execute(delete(table))
    db.query(CustomFieldValue).filter(CustomFieldValue.entity_type.in_(ATTACHABLE_ENTITIES)).delete(synchronize_session=False)
    # Binaries remain inside the local uploads volume and its backup. Removing
    # these obsolete links cannot make an old file belong to a new profile.
    db.query(Attachment).filter(Attachment.entity_type.in_(ATTACHABLE_ENTITIES)).delete(synchronize_session=False)
    db.flush()
    db.expunge_all()
    centre = db.query(OrgUnit).filter_by(code='CENTRE_14').first()
    if centre:
        from models import Vacancy
        if db.query(Vacancy).filter_by(org_unit_id=centre.id).count():
            raise RuntimeError('Подразделение 14 связано с вакансией. Сброс отменён')
        db.query(StaffingPosition).filter_by(org_unit_id=centre.id).delete(synchronize_session=False)
        db.delete(centre)
    root = db.query(OrgUnit).filter_by(code='HQ').one()
    root.name_ru, root.name_kk = 'Заграничные представительства', 'Шетелдік өкілдіктер'
    db.flush()
    created = seed_demo_candidates(db)
    after = {'employees': len(created), 'conversations': 0, 'matching_runs': 0, 'centre_14_present': False}
    db.add(AuditLog(action='reset_demo', entity_type='development_fixture',
        old_values=before, new_values=after, changed_by='development-script'))
    db.flush()
    return after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from database import SessionLocal, engine
    if engine.url.database != 'emp_profile_test':
        raise RuntimeError('Разрешена только выделенная база emp_profile_test')
    with SessionLocal() as db:
        result = replace_demo(db) if args.apply else inspect_demo(db)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({'mode': 'apply' if args.apply else 'preview', **result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
