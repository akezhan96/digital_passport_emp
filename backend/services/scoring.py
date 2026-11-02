"""Deterministic matching engine.

Division of responsibility, exactly as the specification demands:

  * This module knows HOW TO READ A FACT (what "3 years of marketing" means
    for a given employee).
  * It does NOT know what a good value is. Every threshold, step, weight,
    compensation value and readiness band is loaded from database rows owned
    by the HR methodologist and versioned in `scoring_models`.

Score = SUM(W_i * M_i), with M_i in [0, 1].
A `critical` requirement that is not met removes the candidate from the main
short list; they are still returned, flagged, as "potential after development".
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session

from models import (
    Employee, Requirement, ScoringModel, ScoringFunction, CompensationTable,
    ReadinessBand, MatchingRun, MatchingResult, Vacancy,
    EmployeeLanguage, LanguageLevel, EmployeeEducation, EmployeeTraining,
    JobFamily, Competency, EducationLevel,
)
from services.metrics import compute_employee_metrics, compute_metrics_bulk


# ---------------------------------------------------------------------------
# M_i  --  the match function, driven entirely by stored breakpoints
# ---------------------------------------------------------------------------

def apply_scoring_function(fn: Optional[ScoringFunction],
                           value: Optional[float],
                           required: Optional[float]) -> float:
    """Map a raw fact onto M_i in [0, 1] using the stored function."""
    if value is None:
        return 0.0

    # No function configured: fall back to a plain proportional match.
    if fn is None:
        if not required:
            return 1.0 if value > 0 else 0.0
        return max(0.0, min(1.0, value / required))

    kind = (fn.kind or "linear").lower()
    points = fn.breakpoints or []

    if kind == "boolean":
        return 1.0 if value and value > 0 else 0.0

    if kind == "step_absolute":
        # [{"min_value": 3, "m": 1.0}, {"min_value": 2, "m": 0.75}, ...]
        for point in sorted(points, key=lambda p: float(p.get("min_value", 0)), reverse=True):
            if value >= float(point.get("min_value", 0)):
                return max(0.0, min(1.0, float(point.get("m", 0))))
        return 0.0

    if kind == "step_ratio":
        # [{"min_ratio": 1.0, "m": 1.0}, {"min_ratio": 0.67, "m": 0.75}, ...]
        if not required:
            return 1.0 if value > 0 else 0.0
        ratio = value / required
        for point in sorted(points, key=lambda p: float(p.get("min_ratio", 0)), reverse=True):
            if ratio >= float(point.get("min_ratio", 0)):
                return max(0.0, min(1.0, float(point.get("m", 0))))
        return 0.0

    if kind == "level_scale":
        # value and required are ordinal ranks (CEFR A1=1 .. C2=6)
        if not required:
            return 1.0
        if value >= required:
            return 1.0
        for point in sorted(points, key=lambda p: float(p.get("min_gap", 0))):
            gap = required - value
            if gap <= float(point.get("min_gap", 0)):
                return max(0.0, min(1.0, float(point.get("m", 0))))
        return 0.0

    # linear
    if not required:
        return 1.0 if value > 0 else 0.0
    return max(0.0, min(1.0, value / required))


def compensation_value(table: Optional[CompensationTable], code: str) -> Optional[float]:
    """Look up a compensating factor, e.g. relevant education = 0.75."""
    if not table:
        return None
    for entry in (table.entries or []):
        if entry.get("code") == code:
            return max(0.0, min(1.0, float(entry.get("m", 0))))
    return None


# ---------------------------------------------------------------------------
# Fact readers -- one per requirement type handler
# ---------------------------------------------------------------------------

def _metric(metrics: Dict[str, float], key: str) -> Optional[float]:
    return metrics.get(key)


def _handle_company_tenure(db, employee, cond, metrics, req, table=None):
    required = float(cond.get("min_years") or 0)
    actual = _metric(metrics, "company_experience_years") or 0.0
    return actual, required, f"{actual:.1f} y in company (need {required:g})", None


def _handle_total_experience(db, employee, cond, metrics, req, table=None):
    required = float(cond.get("min_years") or 0)
    actual = _metric(metrics, "total_experience_years") or 0.0
    return actual, required, f"{actual:.1f} y total (need {required:g})", None


def _handle_function_experience(db, employee, cond, metrics, req, table=None):
    family_code = cond.get("job_family_code")
    required = float(cond.get("min_years") or 0)
    actual = _metric(metrics, f"function_experience_years:{family_code}") or 0.0
    note = f"{actual:.1f} y in {family_code} (need {required:g})"

    compensation = None
    if actual < required and table is not None:
        code, label = _find_compensation(db, employee, cond, metrics)
        m = compensation_value(table, code)
        if m is not None:
            compensation = {"code": code, "label": label, "m": m}
    return actual, required, note, compensation


def _family_by_code(db: Session, code):
    """A job family by its code, read once per request (see _level_by_code)."""
    if not code:
        return None
    cache = getattr(db, "_family_by_code_cache", None)
    if cache is None:
        cache = {f.code: f for f in db.query(JobFamily).all()}
        try:
            db._family_by_code_cache = cache
        except AttributeError:
            return cache.get(code)
    return cache.get(code)


def _find_compensation(db, employee, cond, metrics) -> Tuple[str, str]:
    """Decide which compensating factor applies. The VALUE of each factor is
    methodology data; only the detection lives here."""
    family_code = cond.get("job_family_code")
    family = _family_by_code(db, family_code)
    if not family:
        return "none", "no compensating factor"

    has_education = any(
        e.field and e.field.job_family_id == family.id for e in employee.educations
    )
    today = date.today()
    relevant_training = [t for t in employee.trainings
                         if t.job_family_id == family.id and t.date_to
                         and t.date_to <= today
                         and (not t.date_from or t.date_from <= today)
                         and (not t.valid_until or t.valid_until >= today)]
    has_recent_training = any(
        t.date_to and (date.today() - t.date_to).days <= 365 * 3 for t in relevant_training
    )

    if has_education and relevant_training:
        return "education_and_training", "relevant degree + course"
    if has_education:
        return "relevant_education", "relevant degree"
    if has_recent_training:
        return "training_only", "recent relevant course"
    if relevant_training:
        return "training_only", "relevant course"
    return "none", "no compensating factor"


def _level_by_code(db: Session, code: Optional[str]):
    """A language level by its code, read once per request.

    The cache hangs off the session, which FastAPI creates and disposes of per
    request -- so it lives exactly as long as the data it describes can be
    assumed unchanged, and a later edit to the scale is picked up by the next
    caller rather than being served stale from a process-wide dictionary.
    """
    if not code:
        return None
    cache = getattr(db, "_level_by_code_cache", None)
    if cache is None:
        cache = {}
        # Ordered by rank so that, where a code appears on more than one
        # scale, the same row wins as the original per-call query did.
        for level in db.query(LanguageLevel).order_by(LanguageLevel.rank).all():
            cache.setdefault(level.code, level)
        try:
            db._level_by_code_cache = cache
        except AttributeError:              # a session that forbids it
            return cache.get(code)
    return cache.get(code)


def _handle_language(db, employee, cond, metrics, req, table=None):
    """condition: {"any_of":[{"language_code":"EN","min_level":"B2"}, ...]}"""
    options = cond.get("any_of") or []
    best_value, best_required, best_note = 0.0, 1.0, "no qualifying language"

    for option in options:
        lang_code = option.get("language_code")
        min_level = option.get("min_level")
        require_confirmed = option.get("confirmed", True)

        target = _level_by_code(db, min_level)
        required_rank = float(target.rank) if target else 0.0

        for row in employee.languages:
            if not row.language or row.language.code != lang_code:
                continue
            if require_confirmed and not row.is_confirmed:
                continue
            if row.valid_until and row.valid_until < date.today():
                continue          # expired certificate does not count
            actual_rank = float(row.level.rank) if row.level else 0.0
            if actual_rank >= required_rank or actual_rank > best_value:
                note = f"{lang_code} {row.level.code if row.level else '?'} (need {min_level})"
                if actual_rank >= required_rank:
                    return actual_rank, required_rank, note, None
                if actual_rank > best_value:
                    best_value, best_required, best_note = actual_rank, required_rank, note

    return best_value, best_required, best_note, None


def _handle_org_unit_experience(db, employee, cond, metrics, req, table=None):
    type_code = cond.get("org_unit_type_code")
    required = float(cond.get("min_years") or 0)
    actual = _metric(metrics, f"org_unit_experience_years:{type_code}") or 0.0
    if required == 0:
        # presence-style requirement: "has worked in a regional unit"
        return (1.0 if actual > 0 else 0.0), 1.0, \
               (f"{actual:.1f} y in {type_code}" if actual else f"no {type_code} experience"), None
    return actual, required, f"{actual:.1f} y in {type_code} (need {required:g})", None


def _handle_country_experience(db, employee, cond, metrics, req, table=None):
    country_code = cond.get("country_code")
    required = float(cond.get("min_years") or 0)
    actual = _metric(metrics, f"country_experience_years:{country_code}") or 0.0
    if required == 0:
        return (1.0 if actual > 0 else 0.0), 1.0, \
               (f"{actual:.1f} y in {country_code}" if actual else "no experience there"), None
    return actual, required, f"{actual:.1f} y in {country_code}", None


def _handle_competency(db, employee, cond, metrics, req, table=None):
    comp_code = cond.get("competency_code")
    required = float(cond.get("min_score") or 0)
    actual = _metric(metrics, f"competency:{comp_code}")
    if actual is None:
        return None, required, f"{comp_code}: not assessed", None
    return actual, required, f"{comp_code} {actual:g} (need {required:g})", None


def _handle_education(db, employee, cond, metrics, req, table=None):
    level_code = cond.get("min_level_code")
    field_code = cond.get("field_code")
    levels = getattr(db, "_education_ranks", None)
    if levels is None:
        levels = {r.code: r.rank for r in db.query(EducationLevel).all()}
        db._education_ranks = levels
    for row in employee.educations:
        level_ok = (not level_code) or (row.level and level_code in levels and row.level.rank >= levels[level_code])
        field_ok = (not field_code) or (row.field and row.field.code == field_code)
        if level_ok and field_ok:
            label = row.field.code if row.field else (row.level.code if row.level else "")
            return 1.0, 1.0, f"education matched ({label})", None
    return 0.0, 1.0, "no matching education", None


def _handle_training(db, employee, cond, metrics, req, table=None):
    family_code = cond.get("job_family_code")
    within_months = int(cond.get("within_months") or 0)
    for row in employee.trainings:
        if not row.date_to or row.date_to > date.today() or (row.valid_until and row.valid_until < date.today()):
            continue
        if family_code and (not row.job_family or row.job_family.code != family_code):
            continue
        if within_months and row.date_to:
            if (date.today() - row.date_to).days > within_months * 30:
                continue
        return 1.0, 1.0, f"course: {row.name}", None
    return 0.0, 1.0, "no qualifying course", None


HANDLERS = {
    "company_tenure": _handle_company_tenure,
    "total_experience": _handle_total_experience,
    "function_experience": _handle_function_experience,
    "language": _handle_language,
    "org_unit_experience": _handle_org_unit_experience,
    "country_experience": _handle_country_experience,
    "competency": _handle_competency,
    "education": _handle_education,
    "training": _handle_training,
}


# ---------------------------------------------------------------------------
# Scoring one candidate
# ---------------------------------------------------------------------------

def resolve_for_model(model: ScoringModel, req: Requirement):
    """Bind a requirement to the ACTIVE model's methodology rows.

    A requirement stores a foreign key to one particular scoring function and
    compensation table, and those rows belong to whichever model version was
    current when the requirement was written. Running under a different model
    must use that model's own rows, so we re-resolve by CODE inside the run's
    model. Without this the `scoring_model` on a run would be decorative and
    switching versions would change nothing.
    """
    fn = req.scoring_function
    if fn is not None and fn.model_id != model.id:
        fn = next((f for f in model.functions if f.code == fn.code), None)

    table = req.compensation_table
    if table is not None and table.model_id != model.id:
        table = next((c for c in model.compensations if c.code == table.code), None)

    return fn, table


def score_employee(db: Session, employee: Employee,
                   requirements: List[Requirement],
                   model: ScoringModel,
                   metrics: Optional[Dict[str, float]] = None
                   ) -> Dict[str, Any]:
    # Passed in when a whole population is being scored; derived here for a
    # single candidate, so both callers stay correct.
    if metrics is None:
        metrics = compute_employee_metrics(db, employee)

    lines: List[Dict[str, Any]] = []
    critical_failures: List[Dict[str, str]] = []
    unmet_must: List[str] = []
    gaps: List[Dict[str, str]] = []
    advantages: List[str] = []

    total_weight = sum(r.weight for r in requirements) or 0
    accumulated = 0.0

    for req in requirements:
        handler_code = req.requirement_type.handler if req.requirement_type else None
        handler = HANDLERS.get(handler_code)

        # Use the running model's own function / compensation rows.
        active_fn, active_table = resolve_for_model(model, req)

        if handler is None:
            value, required, note, compensation = None, None, "unsupported requirement type", None
        else:
            value, required, note, compensation = handler(
                db, employee, req.condition or {}, metrics, req, active_table
            )

        m = apply_scoring_function(active_fn, value, required)

        satisfied = bool(value is not None and required is not None and value >= required)
        compensated = False
        if req.criticality != "critical" and not satisfied and compensation and compensation["m"] > m:
            m = compensation["m"]
            compensated = True
            note = f"{note}; compensated by {compensation['label']}"

        if satisfied:
            status = "met"
            if required and value and required > 0 and value > required * 1.2:
                advantages.append(req.label_ru)
        elif compensated:
            status = "compensated"
        elif value is None:
            status = "not_assessed"
        elif m > 0:
            status = "partial"
        else:
            status = "gap"

        # Criticality gate: judged on the FACT, never on the partial credit.
        if not satisfied and not compensated:
            if req.criticality == "critical":
                critical_failures.append({"requirement": req.label_ru, "requirement_ru": req.label_ru, "requirement_kk": req.label_kk, "detail": note})
            elif req.criticality == "must":
                unmet_must.append(req.label_ru)
                gaps.append({"requirement": req.label_ru, "requirement_ru": req.label_ru, "requirement_kk": req.label_kk, "detail": note})
            else:
                gaps.append({"requirement": req.label_ru, "requirement_ru": req.label_ru, "requirement_kk": req.label_kk, "detail": note})

        contribution = m * req.weight
        accumulated += contribution

        lines.append({
            "requirement_id": req.id,
            "label_ru": req.label_ru,
            "label_kk": req.label_kk,
            "label_en": req.label_en,
            "type": req.requirement_type.code if req.requirement_type else None,
            "criticality": req.criticality,
            "weight": req.weight,
            "fact": note,
            "value": value,
            "required": required,
            "m": round(m, 3),
            "contribution": round(contribution, 2),
            "status": status,
            "scoring_function": active_fn.code if active_fn else None,
            "compensation": compensation,
        })

    score = round((accumulated / total_weight * 100.0) if total_weight else 0.0, 1)
    score = max(0.0, min(100.0, score))
    qualified = not critical_failures

    band = None
    for candidate_band in sorted(model.readiness_bands,
                                 key=lambda b: float(b.min_score), reverse=True):
        if score >= float(candidate_band.min_score):
            band = candidate_band
            break

    return {
        "score": score,
        "qualified": qualified,
        "readiness_code": band.code if band else None,
        "readiness_name_ru": band.name_ru if band else None,
        "readiness_name_kk": band.name_kk if band else None,
        "readiness_name_en": band.name_en if band else None,
        "explanation": {
            "requirements": lines,
            "critical_failures": critical_failures,
            "unmet_must": unmet_must,
            "gaps": gaps,
            "advantages": advantages,
            "total_weight": total_weight,
            "scoring_model": model.version,
        },
        "snapshot": {
            "employee_id": employee.id,
            "metrics": {k: v for k, v in metrics.items()},
            "captured_at": datetime.utcnow().isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Running a whole vacancy
# ---------------------------------------------------------------------------

def run_matching(db: Session, run_id: int,
                 employee_ids: Optional[List[int]] = None,
                 verified_only: bool = True) -> bool:
    run = db.query(MatchingRun).filter(MatchingRun.id == run_id).first()
    if not run:
        return False

    try:
        vacancy = run.vacancy
        requirements = [r for r in vacancy.requirements]
        if not requirements:
            run.status = "error"
            run.error_message = "Vacancy has no requirements"
            db.commit()
            return False

        model = run.scoring_model
        if not model:
            run.status = "error"
            run.error_message = "No scoring model bound to this run"
            db.commit()
            return False

        query = db.query(Employee).filter(Employee.employment_status == "active")
        if verified_only:
            # Only verified profiles may take part in matching.
            query = query.filter(Employee.profile_status == "verified")
        if employee_ids:
            query = query.filter(Employee.id.in_(employee_ids))
        employees = query.all()

        # Derive every candidate's figures up front. Scoring them one at a
        # time re-read the same reference tables once per career row: on 500
        # profiles that was over twelve thousand statements for one run.
        all_metrics = compute_metrics_bulk(db, employees)

        scored = []
        for employee in employees:
            outcome = score_employee(db, employee, requirements, model,
                                     all_metrics.get(employee.id))
            outcome["employee"] = employee
            scored.append(outcome)

        qualified = [s for s in scored if s["qualified"]]
        rejected = [s for s in scored if not s["qualified"]]
        qualified.sort(key=lambda s: (-s["score"], s["employee"].id))
        rejected.sort(key=lambda s: (-s["score"], s["employee"].id))

        db.query(MatchingResult).filter(MatchingResult.run_id == run_id).delete(
            synchronize_session=False
        )

        for rank, item in enumerate(qualified + rejected, 1):
            db.add(MatchingResult(
                run_id=run_id,
                employee_id=item["employee"].id,
                system_rank=rank,
                score=item["score"],
                readiness_code=item["readiness_code"],
                is_qualified=item["qualified"],
                explanation=item["explanation"],
                candidate_snapshot=item["snapshot"],
            ))

        run.status = "completed"
        run.total_evaluated = len(scored)
        run.total_qualified = len(qualified)
        run.completed_at = datetime.utcnow()
        db.commit()
        return True

    except Exception as exc:                                    # noqa: BLE001
        db.rollback()
        run = db.query(MatchingRun).filter(MatchingRun.id == run_id).first()
        if run:
            run.status = "error"
            run.error_message = str(exc)
            db.commit()
        return False
