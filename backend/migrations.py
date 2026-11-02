"""Data migrations for databases created by an earlier version.

`schema_sync` reconciles the *shape* of the database. This module reconciles
its *contents* when a design decision changes something already stored -- the
kind of change a fresh seed would get right but an existing installation would
not.

Every step here must be:

  * idempotent -- running twice changes nothing the second time;
  * guarded -- it recognises the old state it was written for, and does
    nothing at all if an administrator has since moved on from it;
  * silent when there is nothing to do.

The guard is the important part. A migration that unconditionally rewrites
data will, on the second deployment, quietly undo whatever the customer did in
between.
"""

from datetime import datetime
from typing import List

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from models import OrgUnit, OrgUnitType, Position, StaffingPosition
from seed_catalogs import UNIT_TYPE_NAMES, UNIT_POSITION_NAMES, numbered_unit_names


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id           SERIAL PRIMARY KEY,
    step         VARCHAR(120) NOT NULL,
    release      VARCHAR(20),
    applied_at   TIMESTAMP NOT NULL DEFAULT now(),
    outcome      VARCHAR(20) NOT NULL,
    detail       TEXT,
    CONSTRAINT uq_migration_step UNIQUE (step)
)
"""


def _ensure_ledger(db: Session) -> None:
    db.execute(text(LEDGER_DDL))
    db.commit()


def applied_steps(db: Session) -> set:
    """Which steps this database has already seen."""
    try:
        rows = db.execute(text(
            "SELECT step FROM schema_migrations WHERE outcome IN ('applied', 'skipped')"
        )).fetchall()
        return {r[0] for r in rows}
    except Exception:                                            # noqa: BLE001
        return set()


def _record(db: Session, step: str, outcome: str, detail: str = "") -> None:
    """Note the outcome, without ever letting the note break the upgrade."""
    from version import RELEASE
    db.execute(text("""
        INSERT INTO schema_migrations (step, release, applied_at,
                                       outcome, detail)
        VALUES (:step, :release, :at, :outcome, :detail)
        ON CONFLICT (step) DO UPDATE
            SET applied_at = EXCLUDED.applied_at,
                outcome    = EXCLUDED.outcome,
                detail     = EXCLUDED.detail,
                release    = EXCLUDED.release
    """), {"step": step, "release": RELEASE, "at": datetime.utcnow(),
           "outcome": outcome, "detail": detail[:4000]})
    db.commit()


def migration_history(db: Session) -> List[dict]:
    """The ledger, newest first -- for the health endpoint and support."""
    try:
        rows = db.execute(text(
            "SELECT step, release, applied_at, outcome, detail "
            "FROM schema_migrations ORDER BY applied_at DESC"
        )).fetchall()
        return [{"step": r[0], "release": r[1],
                 "applied_at": r[2].isoformat() if r[2] else None,
                 "outcome": r[3], "detail": r[4]} for r in rows]
    except Exception:                                            # noqa: BLE001
        return []


def _centres_to_top_level(db: Session) -> List[str]:
    """Centres stand beside the head office, not inside it.

    They were first seeded as children of HQ, which made the tree read as
    though every centre were a department of head office. A centre carries its
    own establishment and its own people, so it belongs at the top level.

    Guarded: only a centre still parented exactly as the old seed left it is
    moved. One that has since been deliberately placed somewhere is left alone.
    """
    hq = db.query(OrgUnit).filter(OrgUnit.code == "HQ").first()
    if not hq:
        return []

    stranded = (db.query(OrgUnit)
                .filter(OrgUnit.parent_id == hq.id,
                        OrgUnit.code.like("CENTRE\\_%", escape="\\"))
                .all())
    if not stranded:
        return []

    for unit in stranded:
        unit.parent_id = None
    db.flush()
    return [f"{len(stranded)} centres moved to the top level"]


def _establishment_for_existing_posts(db: Session) -> List[str]:
    """Make sure everybody already in post is standing in an established one.

    Appointments are checked against the staffing table. On a database that
    predates the table, people hold posts that no line covers -- so their own
    unit would refuse to re-record them. Rather than exempting historical data
    from the rule, the establishment is back-filled from it: whatever the
    career record shows is currently occupied becomes an established post of at
    least that size.

    Only ever adds or widens. A line an administrator has set is never shrunk.
    """
    from services.staffing import occupancy

    held = occupancy(db)
    if not held:
        return []

    created = widened = 0
    for (unit_id, position_id), holders in held.items():
        if unit_id is None or position_id is None:
            continue
        line = (db.query(StaffingPosition)
                .filter(StaffingPosition.org_unit_id == unit_id,
                        StaffingPosition.position_id == position_id)
                .first())
        if line is None:
            position = db.query(Position).filter(
                Position.id == position_id).first()
            db.add(StaffingPosition(
                org_unit_id=unit_id, position_id=position_id,
                headcount=len(holders),
                grade_id=position.grade_id if position else None,
                notes="Создано из фактических назначений"))
            created += 1
        elif line.headcount < len(holders):
            line.headcount = len(holders)
            widened += 1

    if not (created or widened):
        return []

    db.flush()
    notes = []
    if created:
        notes.append(f"{created} staffing lines created from existing posts")
    if widened:
        notes.append(f"{widened} staffing lines widened to fit their holders")
    return notes


def _ordered_query_comparisons(db: Session) -> List[str]:
    from models import SavedQuery
    import copy
    changed = 0
    for row in db.query(SavedQuery).all():
        definition = copy.deepcopy(row.definition or {})
        modified = False
        for condition in definition.get("conditions", []):
            if condition.get("field") in ("language_level", "max_education_level") and condition.get("operator") == "eq":
                condition["operator"] = "gte"
                modified = True
        if modified:
            row.definition = definition
            changed += 1
    db.flush()
    return [f"Preserved minimum-level semantics in {changed} saved queries"] if changed else []


def _candidate_methodology_v25(db: Session) -> List[str]:
    from models import CandidateMethodology
    from services.candidate_methodology import seed_candidate_methodology
    changes = []
    if db.query(CandidateMethodology).count() == 0:
        seed_candidate_methodology(db)
        changes.append("Created the editable 44-indicator candidate methodology")
    root = db.query(OrgUnit).filter(OrgUnit.code == "HQ").first()
    if root and root.name_ru == "Зарубежные филиалы" and root.unit_type.code == "OTHER":
        root.name_ru = "Заграничные представительства"
        if root.name_kk == "Шетелдік филиалдар":
            root.name_kk = "Шетелдік өкілдіктер"
        if root.name_en == "Foreign branches":
            root.name_en = "Foreign representative offices"
        changes.append("Updated the seeded foreign representative offices label")
    db.flush()
    return changes


def _dynamic_candidate_sources_v26(db: Session) -> List[str]:
    """Additive columns are synced first; published scores are never recalculated."""
    from sqlalchemy import text
    from models import OrgUnitType
    notes = []
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('ALTER TABLE matching_runs ALTER COLUMN scoring_model_id DROP NOT NULL'))
        db.execute(text('ALTER TABLE candidate_criteria DROP CONSTRAINT IF EXISTS ck_candidate_criterion_position'))
        db.execute(text('ALTER TABLE candidate_criteria ADD CONSTRAINT ck_candidate_criterion_position CHECK (position BETWEEN 3 AND 1000000)'))
        inspector = inspect(db.connection())
        for table, name in (('vacancies', 'fk_vacancy_candidate_methodology'),
                            ('matching_runs', 'fk_run_candidate_methodology')):
            present = inspector.get_foreign_keys(table)
            if not any(fk['constrained_columns'] == ['candidate_methodology_id']
                       and fk['referred_table'] == 'candidate_methodologies'
                       and fk['referred_columns'] == ['id'] for fk in present):
                # schema_sync adds scalar columns but PostgreSQL foreign keys
                # are separate table constraints when upgrading old tables.
                db.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT {name} '
                                'FOREIGN KEY (candidate_methodology_id) REFERENCES candidate_methodologies(id)'))
        notes.append('Enabled dynamic candidate criteria and candidate-based matching runs')
    unit_type = db.query(OrgUnitType).filter_by(code='FOREIGN').first()
    if unit_type:
        if unit_type.name_ru in ('Зарубежный офис', 'Зарубежный филиал', 'Зарубежное представительство'):
            unit_type.name_ru = 'Заграничное представительство'
            notes.append('Updated the seeded foreign office type label')
        if unit_type.name_kk in ('Шетелдік кеңсе', 'Шетелдік филиал'):
            unit_type.name_kk = 'Шетелдік өкілдік'
    db.flush()
    return notes


def _rename_seeded_centres(db: Session) -> List[str]:
    """Rename only the labels this installer originally supplied, one language at a time."""
    def rename(row, old_names, new_names):
        changed = False
        for field, old, new in zip(("name_ru", "name_kk", "name_en"), old_names, new_names):
            if getattr(row, field) == old:
                setattr(row, field, new)
                changed = True
        return changed

    count = 0
    unit_type = db.query(OrgUnitType).filter_by(code="CENTRE").with_for_update().one_or_none()
    if unit_type:
        count += rename(unit_type, ("Центр", "Орталық", "Centre"), UNIT_TYPE_NAMES)
        # The modern seed has thirteen units. Older installations could also have №14.
        codes = {f"CENTRE_{n:02d}": n for n in range(1, 15)}
        units = db.query(OrgUnit).filter(OrgUnit.code.in_(codes), OrgUnit.unit_type_id == unit_type.id)
        for unit in units.order_by(OrgUnit.id).with_for_update():
            n = codes[unit.code]
            count += rename(unit, (f"Центр {n}", f"{n}-орталық", f"Centre {n}"), numbered_unit_names(n))
    previous_titles = {
        "CENTRE_DIR": ("Директор центра", "Орталық директоры", "Centre Director"),
        "CENTRE_DEP": ("Заместитель директора центра", "Орталық директорының орынбасары", "Deputy Centre Director"),
    }
    positions = db.query(Position).filter(Position.code.in_(previous_titles)).order_by(Position.id).with_for_update()
    for position in positions:
        count += rename(position, previous_titles[position.code], UNIT_POSITION_NAMES[position.code])
    db.flush()
    return [f"Обновлены стандартные названия подразделений и должностей в {count} записях"] if count else []


STEPS = (
    _centres_to_top_level,
    _establishment_for_existing_posts,
    _ordered_query_comparisons,
    _candidate_methodology_v25,
    _dynamic_candidate_sources_v26,
    _rename_seeded_centres,
)


def run_migrations(db: Session) -> List[str]:
    """Apply every step, reporting only what actually changed.

    A step that finds nothing to do is recorded as `skipped`, not omitted: the
    useful thing to know six months later is that it ran and had no work, as
    opposed to never having run at all.
    """
    _ensure_ledger(db)

    completed = applied_steps(db)
    done: List[str] = []
    for step in STEPS:
        name = step.__name__.lstrip("_")
        if name in completed:
            continue
        try:
            changes = step(db)
            if changes:
                done.extend(changes)
                _record(db, name, "applied", "; ".join(changes))
            else:
                _record(db, name, "skipped", "nothing to do")
        except Exception as exc:                                 # noqa: BLE001
            # Stop startup on a failed upgrade: using a partly migrated schema
            # could silently damage assessments. Record the failure and let
            # the installer restore the pre-update backup.
            db.rollback()
            message = f"{name} failed: {exc}"
            done.append(message)
            _record(db, name, "failed", str(exc))
            raise RuntimeError(f"Migration {name} failed; restore the pre-update backup") from exc
    return done
