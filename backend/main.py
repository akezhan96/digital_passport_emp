from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import os
from datetime import datetime
from version import RELEASE
from runtime import PRODUCTION

from database import engine, get_db
from models import (
    Base, MatchingRun, ScoringModel, Competency, AuditLog,
    CandidateMethodology,
)
from routers import (reference, employees, vacancies, methodology, matching,
                     extensions, auth_router, analytics, appointments, personnel,
                     documents, org, staffing, assistant, dossier_subsections)
from auth import auth_middleware, seed_users
from services.metrics import recompute_all, reconcile_all_current_posts
from services.dashboard import status_summary

# Additive schema reconciliation: creates missing tables AND adds columns that
# were introduced since this database was first created. create_all() alone
# would skip the columns and leave the code querying fields that do not exist.
from schema_sync import sync_schema   # noqa: E402

_changes = sync_schema(engine, Base.metadata)
if _changes:
    print(f"Schema updated: {', '.join(_changes)}")

# Ensure the demo accounts exist on start-up.
from database import SessionLocal as _SessionLocal   # noqa: E402
from migrations import run_migrations               # noqa: E402

_bootstrap = _SessionLocal()
try:
    _created = seed_users(_bootstrap)
    if _created:
        print(f"Created accounts: {', '.join(_created)}")

    # Contents, not shape: changes that an existing database needs applied and
    # a freshly seeded one gets right on its own.
    _migrated = run_migrations(_bootstrap)
    for _note in _migrated:
        print(f"Migration: {_note}")
finally:
    _bootstrap.close()

from services.assistant_jobs import recover_interrupted
recover_interrupted()

app = FastAPI(
    title="Цифровой профиль сотрудника",
    description="Digital employee profile and deterministic internal-candidate "
                "matching for international assignments.",
    version=RELEASE,
    docs_url=None if PRODUCTION else "/docs",
    redoc_url=None,
)
from localization import http_error, validation_error
from starlette.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
app.add_exception_handler(HTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)

# Auth runs INSIDE CORS: middleware is applied bottom-up, so registering the
# auth check first and CORS second means a 401/403 still carries CORS headers
# and the browser can read the message instead of reporting a network error.
app.middleware("http")(auth_middleware)

# In production the interface is served from the same origin as the API, so
# no cross-origin request is ever made and no origin needs to be allowed.
# ALLOWED_ORIGINS exists for the development split (Vite on 5173, API on 8000)
# and for any deployment that genuinely serves them from different hosts.
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _origins_env:
    _allowed = [o.strip() for o in _origins_env.split(",") if o.strip()]
elif os.getenv("AUTH_SECRET"):
    # A configured deployment: assume same-origin and allow nothing.
    _allowed = []
else:
    # No secret set means this is the development compose file.
    _allowed = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(reference.router)
app.include_router(employees.router)
app.include_router(dossier_subsections.router)
app.include_router(vacancies.router)
app.include_router(methodology.router)
app.include_router(matching.router)
app.include_router(extensions.router)
app.include_router(analytics.router)
app.include_router(personnel.router)
app.include_router(appointments.router)
app.include_router(documents.router)
app.include_router(org.router)
app.include_router(staffing.router)
app.include_router(assistant.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """What this instance is running, and whether its database agrees.

    The first question of any support conversation is which version is
    deployed. Answering it from the running service, rather than from files on
    the server, is the difference between a diagnosis and a guess.
    """
    from version import RELEASE, SCHEMA_REVISION, RELEASE_NOTE
    from migrations import migration_history

    history = migration_history(db)
    failed = [h["step"] for h in history if h["outcome"] == "failed"]

    return {
        "status": "degraded" if failed else "ok",
        "release": RELEASE,
        "environment": "production" if PRODUCTION else "development",
        "schema_revision": SCHEMA_REVISION,
        "release_note": RELEASE_NOTE,
        "migrations_applied": sum(1 for h in history
                                  if h["outcome"] == "applied"),
        "migrations_failed": failed,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/v1/admin/deployment")
def deployment_state(db: Session = Depends(get_db)):
    """The full migration ledger. Admin-only, for upgrades and support."""
    from version import RELEASE, SCHEMA_REVISION
    from migrations import migration_history
    return {
        "release": RELEASE,
        "schema_revision": SCHEMA_REVISION,
        "migrations": migration_history(db),
    }


@app.get("/api/v1/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    statuses = status_summary(db)

    default_model = db.query(ScoringModel).filter(
        ScoringModel.is_default.is_(True)
    ).first()
    candidate_method = db.query(CandidateMethodology).filter_by(status="active").first()

    return {
        **statuses,
        "matching_runs": (db.query(MatchingRun).count() if request.state.user.get("role") == "admin"
                          else db.query(MatchingRun).filter(MatchingRun.include_confidential.is_(False)).count()),
        "competencies": db.query(Competency).filter(Competency.is_active.is_(True)).count(),
        "scoring_model": {
            "version": default_model.version if default_model else None,
            "name": default_model.name if default_model else None,
            "status": default_model.status if default_model else None,
        },
        "candidate_methodology": {
            "version": candidate_method.version if candidate_method else None,
            "name_ru": candidate_method.name_ru if candidate_method else None,
            "name_kk": candidate_method.name_kk if candidate_method else None,
            "status": candidate_method.status if candidate_method else None,
        },
        "recent_activity": [{
            "action": r.action,
            "entity_type": r.entity_type,
            "changed_by": r.changed_by,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        } for r in db.query(AuditLog).order_by(AuditLog.changed_at.desc()).limit(8).all()]
        if request.state.user.get("role") == "admin" else [],
    }


@app.post("/api/v1/admin/recompute-metrics")
def recompute_metrics(db: Session = Depends(get_db)):
    """Recalculate every derived tenure figure across the whole base."""
    count = recompute_all(db)
    return {"recomputed_for_employees": count}


@app.post("/api/v1/admin/reconcile-posts")
def reconcile_posts(db: Session = Depends(get_db)):
    """Realign the denormalised current position / unit with the career
    timeline, which is the authoritative record."""
    fixed = reconcile_all_current_posts(db)
    return {"employees_realigned": fixed}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
