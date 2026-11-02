"""Small aggregate summaries without loading personal files or vacancies."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Employee, Vacancy


def status_summary(db: Session) -> dict:
    employee_counts = dict(db.query(Employee.profile_status, func.count(Employee.id))
                           .group_by(Employee.profile_status).all())
    vacancy_counts = dict(db.query(Vacancy.status, func.count(Vacancy.id))
                          .group_by(Vacancy.status).all())

    employees = {status: employee_counts.get(status, 0)
                 for status in ("verified", "draft", "in_review", "archived")}
    employee_total = sum(employee_counts.values())
    employees["other"] = employee_total - sum(employees.values())
    employees["total"] = employee_total
    employees["verified_percent"] = (round(employees["verified"] / employee_total * 100)
                                     if employee_total else 0)

    vacancies = {
        "active": vacancy_counts.get("active", 0) + vacancy_counts.get("requirements_approved", 0),
        "draft": vacancy_counts.get("draft", 0),
        "closed": vacancy_counts.get("closed", 0),
    }
    vacancy_total = sum(vacancy_counts.values())
    vacancies["other"] = vacancy_total - sum(vacancies.values())
    vacancies["total"] = vacancy_total
    return {"employees": employees, "vacancies": vacancies}
