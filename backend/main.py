from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from database import engine, get_db
from models import (
    Base, Employee, Vacancy, MatchingRun, ScoringModel, Competency, AuditLog,
)
from routers import (reference, employees, vacancies, methodology, matching,
                     extensions, auth_router)
from auth import auth_middleware, seed_users
from services.metrics import recompute_all

Base.metadata.create_all(bind=engine)

# Ensure the demo accounts exist on start-up.
from database import SessionLocal as _SessionLocal   # noqa: E402
_bootstrap = _SessionLocal()
try:
    _created = seed_users(_bootstrap)
    if _created:
        print(f"Created accounts: {', '.join(_created)}")
finally:
    _bootstrap.close()

app = FastAPI(
    title="HR Talent System",
    description="Digital employee profile and deterministic internal-candidate "
                "matching for international assignments.",
    version="2.0.0",
)

# Auth runs INSIDE CORS: middleware is applied bottom-up, so registering the
# auth check first and CORS second means a 401/403 still carries CORS headers
# and the browser can read the message instead of reporting a network error.
app.middleware("http")(auth_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(reference.router)
app.include_router(employees.router)
app.include_router(vacancies.router)
app.include_router(methodology.router)
app.include_router(matching.router)
app.include_router(extensions.router)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/v1/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total_employees = db.query(Employee).count()
    verified = db.query(Employee).filter(Employee.profile_status == "verified").count()
    drafts = db.query(Employee).filter(Employee.profile_status == "draft").count()
    in_review = db.query(Employee).filter(Employee.profile_status == "in_review").count()

    active_vacancies = db.query(Vacancy).filter(
        Vacancy.status.in_(["active", "requirements_approved"])
    ).count()

    default_model = db.query(ScoringModel).filter(
        ScoringModel.is_default.is_(True)
    ).first()

    return {
        "employees": {
            "total": total_employees,
            "verified": verified,
            "draft": drafts,
            "in_review": in_review,
            "verified_percent": round(verified / total_employees * 100)
                                if total_employees else 0,
        },
        "vacancies": {
            "total": db.query(Vacancy).count(),
            "active": active_vacancies,
        },
        "matching_runs": db.query(MatchingRun).count(),
        "competencies": db.query(Competency).filter(Competency.is_active.is_(True)).count(),
        "scoring_model": {
            "version": default_model.version if default_model else None,
            "name": default_model.name if default_model else None,
            "status": default_model.status if default_model else None,
        },
        "recent_activity": [{
            "action": r.action,
            "entity_type": r.entity_type,
            "changed_by": r.changed_by,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        } for r in db.query(AuditLog).order_by(AuditLog.changed_at.desc()).limit(8).all()],
    }


@app.post("/api/v1/admin/recompute-metrics")
def recompute_metrics(db: Session = Depends(get_db)):
    """Recalculate every derived tenure figure across the whole base."""
    count = recompute_all(db)
    return {"recomputed_for_employees": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
