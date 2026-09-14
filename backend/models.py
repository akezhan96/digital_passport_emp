"""Normalised data model for the HR Talent System.

Design rules taken from the source specification:

  * 1:N everywhere. An employee may have any number of educations, languages,
    courses, jobs and assessments -- never a wide table with 200 columns.
  * Job Family is stored on every work-experience row, so "marketing
    experience" is derived from the function, not from matching the word
    "marketer" inside a job title.
  * Work history is stored as intervals. Every tenure figure is COMPUTED,
    never typed in by a user.
  * Methodology (weights, match functions, compensation, readiness bands)
    lives in versioned rows, not in Python.
  * Reference data carries ru / kk / en names so the UI can be localised
    without a translation join.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey,
    Numeric, JSON, UniqueConstraint, Index,
)
from sqlalchemy import text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Named:
    """Mixin giving every reference table its three interface languages."""
    code = Column(String(50), nullable=False)
    name_ru = Column(String(200), nullable=False)
    name_kk = Column(String(200))
    name_en = Column(String(200))


class Stamped:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ===========================================================================
# REFERENCE DATA  (ref.*)  -- all editable through the admin UI
# ===========================================================================

class Country(Base, Named, Stamped):
    __tablename__ = "ref_countries"
    id = Column(Integer, primary_key=True)
    __table_args__ = (UniqueConstraint("code", name="uq_country_code"),)


class Nationality(Base, Named, Stamped):
    __tablename__ = "ref_nationalities"
    id = Column(Integer, primary_key=True)
    __table_args__ = (UniqueConstraint("code", name="uq_nationality_code"),)


class Language(Base, Named, Stamped):
    __tablename__ = "ref_languages"
    id = Column(Integer, primary_key=True)
    __table_args__ = (UniqueConstraint("code", name="uq_language_code"),)


class LanguageScale(Base, Named, Stamped):
    """CEFR, or a corporate scale mapped onto it."""
    __tablename__ = "ref_language_scales"
    id = Column(Integer, primary_key=True)
    levels = relationship("LanguageLevel", back_populates="scale",
                          cascade="all, delete-orphan", order_by="LanguageLevel.rank")
    __table_args__ = (UniqueConstraint("code", name="uq_lang_scale_code"),)


class LanguageLevel(Base, Named, Stamped):
    """A1..C2 for CEFR. `rank` makes levels comparable across scales.

    The specification's flagship validation: a level such as "B3" simply does
    not exist here for the CEFR scale, so it can never be stored.
    """
    __tablename__ = "ref_language_levels"
    id = Column(Integer, primary_key=True)
    scale_id = Column(Integer, ForeignKey("ref_language_scales.id"), nullable=False)
    rank = Column(Integer, nullable=False)  # comparable ordinal, CEFR A1=1 .. C2=6

    scale = relationship("LanguageScale", back_populates="levels")
    __table_args__ = (
        UniqueConstraint("scale_id", "code", name="uq_level_per_scale"),
    )


class EducationLevel(Base, Named, Stamped):
    """Среднее / среднее профессиональное / высшее / магистратура ..."""
    __tablename__ = "ref_education_levels"
    id = Column(Integer, primary_key=True)
    rank = Column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint("code", name="uq_edu_level_code"),)


class EducationField(Base, Named, Stamped):
    """Специальность. Optionally tied to a job family for compensation rules."""
    __tablename__ = "ref_education_fields"
    id = Column(Integer, primary_key=True)
    job_family_id = Column(Integer, ForeignKey("ref_job_families.id"))
    job_family = relationship("JobFamily")
    __table_args__ = (UniqueConstraint("code", name="uq_edu_field_code"),)


class JobFamily(Base, Named, Stamped):
    """Marketing, Analytics, Finance, IT, HR, Legal, Procurement, Operations.

    `parent_id` expresses relatedness (Marketing Analytics ⊂ Analytics) so
    adjacent-function experience can be credited.
    """
    __tablename__ = "ref_job_families"
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("ref_job_families.id"))
    children = relationship("JobFamily", backref="parent", remote_side=[id])
    __table_args__ = (UniqueConstraint("code", name="uq_job_family_code"),)


class OrgUnitType(Base, Named, Stamped):
    """Headquarters / Regional / Foreign Branch / Subsidiary / Other."""
    __tablename__ = "ref_org_unit_types"
    id = Column(Integer, primary_key=True)
    __table_args__ = (UniqueConstraint("code", name="uq_org_unit_type_code"),)


class PositionGrade(Base, Named, Stamped):
    __tablename__ = "ref_position_grades"
    id = Column(Integer, primary_key=True)
    rank = Column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint("code", name="uq_grade_code"),)


class TrainingType(Base, Named, Stamped):
    __tablename__ = "ref_training_types"
    id = Column(Integer, primary_key=True)
    __table_args__ = (UniqueConstraint("code", name="uq_training_type_code"),)


class AssessmentScale(Base, Named, Stamped):
    """Editable scale, e.g. 1-5 stars or 0-10. Stored with each session so a
    historical session keeps the scale it was measured on."""
    __tablename__ = "ref_assessment_scales"
    id = Column(Integer, primary_key=True)
    min_value = Column(Numeric(6, 2), nullable=False, default=0)
    max_value = Column(Numeric(6, 2), nullable=False, default=10)
    step = Column(Numeric(6, 2), nullable=False, default=0.1)
    __table_args__ = (UniqueConstraint("code", name="uq_assessment_scale_code"),)


class CompetencyCategory(Base, Named, Stamped):
    """professional | psychological -- psychological is access-restricted."""
    __tablename__ = "ref_competency_categories"
    id = Column(Integer, primary_key=True)
    is_confidential = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("code", name="uq_comp_category_code"),)


class Competency(Base, Named, Stamped):
    """THE editable assessment criterion.

    Adding "Negotiation" is one row here -- no schema change, no code change.
    Requirements point at competencies by id, and the scoring engine reads
    scores through this table.
    """
    __tablename__ = "ref_competencies"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("ref_competency_categories.id"), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, default=0)

    category = relationship("CompetencyCategory")
    __table_args__ = (UniqueConstraint("code", name="uq_competency_code"),)


class RequirementType(Base, Named, Stamped):
    """Declares the kinds of requirement the engine knows how to evaluate.

    `handler` names the evaluator; `condition_schema` documents the JSON shape
    the UI should render for this type.
    """
    __tablename__ = "ref_requirement_types"
    id = Column(Integer, primary_key=True)
    handler = Column(String(50), nullable=False)
    condition_schema = Column(JSON, default=dict)
    description = Column(Text)
    __table_args__ = (UniqueConstraint("code", name="uq_requirement_type_code"),)


# ===========================================================================
# ORGANISATION
# ===========================================================================

class OrgUnit(Base, Named, Stamped):
    __tablename__ = "org_units"
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("org_units.id"))
    country_id = Column(Integer, ForeignKey("ref_countries.id"))
    region = Column(String(120))
    unit_type_id = Column(Integer, ForeignKey("ref_org_unit_types.id"), nullable=False)
    valid_from = Column(Date)
    valid_to = Column(Date)

    country = relationship("Country")
    unit_type = relationship("OrgUnitType")
    parent = relationship("OrgUnit", remote_side=[id], backref="children")
    __table_args__ = (UniqueConstraint("code", name="uq_org_unit_code"),)


class Position(Base, Named, Stamped):
    """Job title, deliberately separate from professional function."""
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    job_family_id = Column(Integer, ForeignKey("ref_job_families.id"), nullable=False)
    grade_id = Column(Integer, ForeignKey("ref_position_grades.id"))
    management_level = Column(Integer, default=0)

    job_family = relationship("JobFamily")
    grade = relationship("PositionGrade")
    __table_args__ = (UniqueConstraint("code", name="uq_position_code"),)


# ===========================================================================
# EMPLOYEE PROFILE
# ===========================================================================

PROFILE_STATUSES = ("draft", "in_review", "verified", "archived")


class Employee(Base, Stamped):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)

    personnel_number = Column(String(50), unique=True)
    anonymous_code = Column(String(20), unique=True)  # shown instead of a name

    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100))

    birth_date = Column(Date)
    birth_place = Column(String(200))
    birth_country_id = Column(Integer, ForeignKey("ref_countries.id"))
    nationality_id = Column(Integer, ForeignKey("ref_nationalities.id"))

    email = Column(String(150))
    phone = Column(String(40))

    hire_date = Column(Date)
    current_position_id = Column(Integer, ForeignKey("positions.id"))
    current_org_unit_id = Column(Integer, ForeignKey("org_units.id"))

    employment_status = Column(String(20), nullable=False, default="active")
    profile_status = Column(String(20), nullable=False, default="draft")
    verified_at = Column(DateTime)
    verified_by = Column(String(100))

    birth_country = relationship("Country", foreign_keys=[birth_country_id])
    nationality = relationship("Nationality")
    current_position = relationship("Position")
    current_org_unit = relationship("OrgUnit")

    educations = relationship("EmployeeEducation", back_populates="employee",
                              cascade="all, delete-orphan")
    languages = relationship("EmployeeLanguage", back_populates="employee",
                             cascade="all, delete-orphan")
    trainings = relationship("EmployeeTraining", back_populates="employee",
                             cascade="all, delete-orphan")
    work_experience = relationship("WorkExperience", back_populates="employee",
                                   cascade="all, delete-orphan",
                                   order_by="WorkExperience.date_from")
    assessment_sessions = relationship("AssessmentSession", back_populates="employee",
                                       cascade="all, delete-orphan")
    metrics = relationship("EmployeeMetric", back_populates="employee",
                           cascade="all, delete-orphan")

    @property
    def full_name(self):
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class EmployeeEducation(Base, Stamped):
    __tablename__ = "employee_education"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    level_id = Column(Integer, ForeignKey("ref_education_levels.id"), nullable=False)
    institution = Column(String(250), nullable=False)
    country_id = Column(Integer, ForeignKey("ref_countries.id"))
    field_id = Column(Integer, ForeignKey("ref_education_fields.id"))
    start_year = Column(Integer)
    end_year = Column(Integer)
    qualification = Column(String(150))
    document_ref = Column(String(250))

    employee = relationship("Employee", back_populates="educations")
    level = relationship("EducationLevel")
    field = relationship("EducationField")
    country = relationship("Country")


class EmployeeLanguage(Base, Stamped):
    __tablename__ = "employee_languages"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    language_id = Column(Integer, ForeignKey("ref_languages.id"), nullable=False)
    scale_id = Column(Integer, ForeignKey("ref_language_scales.id"), nullable=False)
    level_id = Column(Integer, ForeignKey("ref_language_levels.id"), nullable=False)
    is_confirmed = Column(Boolean, nullable=False, default=False)
    document = Column(String(200))
    confirmed_at = Column(Date)
    valid_until = Column(Date)

    employee = relationship("Employee", back_populates="languages")
    language = relationship("Language")
    scale = relationship("LanguageScale")
    level = relationship("LanguageLevel")
    __table_args__ = (
        UniqueConstraint("employee_id", "language_id", name="uq_employee_language"),
    )


class EmployeeTraining(Base, Stamped):
    __tablename__ = "employee_training"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    name = Column(String(250), nullable=False)
    training_type_id = Column(Integer, ForeignKey("ref_training_types.id"))
    job_family_id = Column(Integer, ForeignKey("ref_job_families.id"))
    provider = Column(String(200))
    date_from = Column(Date)
    date_to = Column(Date)
    result = Column(String(150))
    certificate_ref = Column(String(250))
    valid_until = Column(Date)

    employee = relationship("Employee", back_populates="trainings")
    training_type = relationship("TrainingType")
    job_family = relationship("JobFamily")


class WorkExperience(Base, Stamped):
    """The career roadmap. Every tenure figure in the system derives from here.

    Job family, org-unit type and country are captured AS AT THE PERIOD, so a
    later reorganisation cannot retroactively rewrite somebody's history.
    """
    __tablename__ = "work_experience"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    is_internal = Column(Boolean, nullable=False, default=True)
    org_unit_id = Column(Integer, ForeignKey("org_units.id"))      # internal
    external_employer = Column(String(250))                         # external
    position_id = Column(Integer, ForeignKey("positions.id"))       # internal
    external_position_title = Column(String(250))                   # external

    job_family_id = Column(Integer, ForeignKey("ref_job_families.id"), nullable=False)
    org_unit_type_id = Column(Integer, ForeignKey("ref_org_unit_types.id"), nullable=False)
    country_id = Column(Integer, ForeignKey("ref_countries.id"))
    management_level = Column(Integer, default=0)

    date_from = Column(Date, nullable=False)
    date_to = Column(Date)  # NULL = current

    employee = relationship("Employee", back_populates="work_experience")
    org_unit = relationship("OrgUnit")
    position = relationship("Position")
    job_family = relationship("JobFamily")
    org_unit_type = relationship("OrgUnitType")
    country = relationship("Country")

    __table_args__ = (Index("ix_work_exp_employee", "employee_id", "date_from"),)


class AssessmentSession(Base, Stamped):
    """One assessment event. Old sessions are never overwritten, so the
    development history (2024 leadership 3.8 -> 2026 4.4) is preserved."""
    __tablename__ = "assessment_sessions"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    session_type = Column(String(20), nullable=False, default="professional")
    scale_id = Column(Integer, ForeignKey("ref_assessment_scales.id"), nullable=False)
    session_date = Column(Date, nullable=False)
    assessor = Column(String(150))
    conclusion_text = Column(Text)
    status = Column(String(20), nullable=False, default="confirmed")
    valid_until = Column(Date)

    employee = relationship("Employee", back_populates="assessment_sessions")
    scale = relationship("AssessmentScale")
    scores = relationship("CompetencyScore", back_populates="session",
                          cascade="all, delete-orphan")


class CompetencyScore(Base, Stamped):
    __tablename__ = "competency_scores"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("assessment_sessions.id"), nullable=False)
    competency_id = Column(Integer, ForeignKey("ref_competencies.id"), nullable=False)
    score = Column(Numeric(6, 2), nullable=False)

    session = relationship("AssessmentSession", back_populates="scores")
    competency = relationship("Competency")
    __table_args__ = (
        UniqueConstraint("session_id", "competency_id", name="uq_score_per_session"),
    )


class EmployeeMetric(Base):
    """Derived, materialised figures. Never entered by a user."""
    __tablename__ = "employee_metrics"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    metric_code = Column(String(80), nullable=False)
    metric_value = Column(Numeric(10, 3), nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    employee = relationship("Employee", back_populates="metrics")
    __table_args__ = (
        UniqueConstraint("employee_id", "metric_code", name="uq_metric_per_employee"),
    )


# ===========================================================================
# METHODOLOGY  -- versioned, owned by the HR methodologist, not by developers
# ===========================================================================

class ScoringModel(Base, Stamped):
    __tablename__ = "scoring_models"
    id = Column(Integer, primary_key=True)
    version = Column(String(20), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    status = Column(String(20), nullable=False, default="draft")  # draft/under_test/approved/retired
    is_default = Column(Boolean, nullable=False, default=False)
    approved_by = Column(String(100))
    approved_at = Column(DateTime)

    # A partial unique index: at most one row may carry is_default = true,
    # enforced by the database rather than by convention.
    __table_args__ = (
        Index("uq_single_default_scoring_model", "is_default",
              unique=True, postgresql_where=text("is_default")),
    )

    functions = relationship("ScoringFunction", back_populates="model",
                             cascade="all, delete-orphan")
    compensations = relationship("CompensationTable", back_populates="model",
                                 cascade="all, delete-orphan")
    readiness_bands = relationship("ReadinessBand", back_populates="model",
                                   cascade="all, delete-orphan",
                                   order_by="ReadinessBand.min_score.desc()")


class ScoringFunction(Base, Named, Stamped):
    """The M_i mapping, as DATA.

    kind = step_absolute : breakpoints [{"min_value":3,"m":1.0}, ...]
    kind = step_ratio    : breakpoints [{"min_ratio":1.0,"m":1.0}, ...]
    kind = linear        : m = clamp(value / required, 0, 1)
    kind = boolean       : m = 1.0 if satisfied else 0.0
    kind = level_scale   : ordinal comparison (language levels)
    """
    __tablename__ = "scoring_functions"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("scoring_models.id"), nullable=False)
    kind = Column(String(30), nullable=False, default="linear")
    breakpoints = Column(JSON, nullable=False, default=list)

    model = relationship("ScoringModel", back_populates="functions")
    __table_args__ = (UniqueConstraint("model_id", "code", name="uq_fn_per_model"),)


class CompensationTable(Base, Named, Stamped):
    """entries: [{"code":"direct_experience","m":1.0,"label_ru":"..."}, ...]"""
    __tablename__ = "compensation_tables"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("scoring_models.id"), nullable=False)
    entries = Column(JSON, nullable=False, default=list)

    model = relationship("ScoringModel", back_populates="compensations")
    __table_args__ = (UniqueConstraint("model_id", "code", name="uq_comp_per_model"),)


class ReadinessBand(Base, Named, Stamped):
    """90-100 Ready Now, 80-89 Ready <=6m, ..."""
    __tablename__ = "readiness_bands"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("scoring_models.id"), nullable=False)
    min_score = Column(Numeric(5, 2), nullable=False)
    color = Column(String(20))

    model = relationship("ScoringModel", back_populates="readiness_bands")


# ===========================================================================
# VACANCIES & REQUIREMENTS
# ===========================================================================

class PositionProfile(Base, Named, Stamped):
    """Reusable requirement template for a role."""
    __tablename__ = "position_profiles"
    id = Column(Integer, primary_key=True)
    job_family_id = Column(Integer, ForeignKey("ref_job_families.id"))
    grade_id = Column(Integer, ForeignKey("ref_position_grades.id"))
    description = Column(Text)

    job_family = relationship("JobFamily")
    requirements = relationship("Requirement",
                                primaryjoin="and_(Requirement.profile_id==PositionProfile.id,"
                                            "Requirement.vacancy_id==None)",
                                cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("code", name="uq_position_profile_code"),)


class Vacancy(Base, Stamped):
    __tablename__ = "vacancies"
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("position_profiles.id"))
    title = Column(String(200), nullable=False)
    country_id = Column(Integer, ForeignKey("ref_countries.id"), nullable=False)
    org_unit_id = Column(Integer, ForeignKey("org_units.id"))
    description = Column(Text)
    status = Column(String(30), nullable=False, default="draft")
    requirements_version = Column(Integer, nullable=False, default=1)

    profile = relationship("PositionProfile")
    country = relationship("Country")
    org_unit = relationship("OrgUnit")
    requirements = relationship(
        "Requirement",
        primaryjoin="Requirement.vacancy_id==Vacancy.id",
        cascade="all, delete-orphan",
        order_by="Requirement.sort_order",
    )
    matching_runs = relationship("MatchingRun", back_populates="vacancy")


CRITICALITIES = ("critical", "must", "nice")


class Requirement(Base, Stamped):
    """A criterion attached to a vacancy (or to a profile as a template).

    `condition` is JSON shaped by the requirement type, e.g.
      company_tenure       {"min_years": 5}
      function_experience  {"job_family_code": "MARKETING", "min_years": 3}
      language             {"any_of":[{"language_code":"EN","min_level":"B2"}]}
      competency           {"competency_code":"LEADERSHIP","min_score":3.5}
      org_unit_experience  {"org_unit_type_code":"REGIONAL","min_years":0}
    """
    __tablename__ = "requirements"
    id = Column(Integer, primary_key=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"))
    profile_id = Column(Integer, ForeignKey("position_profiles.id"))

    requirement_type_id = Column(Integer, ForeignKey("ref_requirement_types.id"), nullable=False)
    label_ru = Column(String(200), nullable=False)
    label_kk = Column(String(200))
    label_en = Column(String(200))

    condition = Column(JSON, nullable=False, default=dict)
    weight = Column(Integer, nullable=False, default=0)
    criticality = Column(String(20), nullable=False, default="must")

    scoring_function_id = Column(Integer, ForeignKey("scoring_functions.id"))
    compensation_table_id = Column(Integer, ForeignKey("compensation_tables.id"))
    sort_order = Column(Integer, default=0)

    requirement_type = relationship("RequirementType")
    scoring_function = relationship("ScoringFunction")
    compensation_table = relationship("CompensationTable")


# ===========================================================================
# MATCHING & DECISIONS
# ===========================================================================

class MatchingRun(Base):
    __tablename__ = "matching_runs"
    id = Column(Integer, primary_key=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"), nullable=False)
    scoring_model_id = Column(Integer, ForeignKey("scoring_models.id"), nullable=False)
    requirements_version = Column(Integer, nullable=False, default=1)

    status = Column(String(20), nullable=False, default="processing")
    total_evaluated = Column(Integer, default=0)
    total_qualified = Column(Integer, default=0)
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100))
    completed_at = Column(DateTime)

    vacancy = relationship("Vacancy", back_populates="matching_runs")
    scoring_model = relationship("ScoringModel")
    results = relationship("MatchingResult", back_populates="run",
                           cascade="all, delete-orphan", order_by="MatchingResult.system_rank")


class MatchingResult(Base):
    __tablename__ = "matching_results"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("matching_runs.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    system_rank = Column(Integer, nullable=False)
    score = Column(Numeric(5, 2), nullable=False)
    readiness_code = Column(String(40))
    is_qualified = Column(Boolean, nullable=False, default=True)

    explanation = Column(JSON, nullable=False, default=dict)
    candidate_snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("MatchingRun", back_populates="results")
    employee = relationship("Employee")
    decision = relationship("Decision", back_populates="result", uselist=False,
                            cascade="all, delete-orphan")


class Decision(Base, Stamped):
    """System ranking and the human decision are stored side by side; any
    divergence demands a written reason."""
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True)
    result_id = Column(Integer, ForeignKey("matching_results.id"), nullable=False, unique=True)

    system_rank = Column(Integer, nullable=False)
    final_rank = Column(Integer)
    decision = Column(String(20), nullable=False)  # selected/rejected/on_hold/reserve
    reason = Column(Text)
    decided_by = Column(String(100), nullable=False)
    decided_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    result = relationship("MatchingResult", back_populates="decision")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(60), nullable=False)
    entity_id = Column(Integer)
    old_values = Column(JSON)
    new_values = Column(JSON)
    reason = Column(Text)
    changed_by = Column(String(100), nullable=False, default="system")
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


# ===========================================================================
# EXTENSIBILITY: user-defined fields and file attachments
# ===========================================================================

# Sections of the profile that accept custom fields and attachments.
ATTACHABLE_ENTITIES = (
    "employee",         # general info -- passport photo, etc.
    "education",        # diploma scan
    "language",         # IELTS / Goethe certificate
    "training",         # course certificate
    "work_experience",  # reference letter
    "assessment",       # assessment report
)

CUSTOM_FIELD_TYPES = ("text", "textarea", "number", "date", "boolean", "select")


class CustomFieldDefinition(Base, Stamped):
    """A field the HR administrator adds without a schema change.

    Values are stored in typed columns (see CustomFieldValue) rather than a
    single stringly-typed blob, so numbers stay sortable and dates stay
    comparable.
    """
    __tablename__ = "custom_field_definitions"
    id = Column(Integer, primary_key=True)

    entity_type = Column(String(30), nullable=False)   # one of ATTACHABLE_ENTITIES
    code = Column(String(60), nullable=False)
    name_ru = Column(String(200), nullable=False)
    name_kk = Column(String(200))
    name_en = Column(String(200))

    field_type = Column(String(20), nullable=False, default="text")
    options = Column(JSON, default=list)      # for field_type == "select"
    help_text = Column(String(400))
    is_required = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, default=0)

    values = relationship("CustomFieldValue", back_populates="definition",
                          cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("entity_type", "code", name="uq_custom_field_per_entity"),
    )


class CustomFieldValue(Base, Stamped):
    """One value of a custom field for one record."""
    __tablename__ = "custom_field_values"
    id = Column(Integer, primary_key=True)

    definition_id = Column(Integer, ForeignKey("custom_field_definitions.id"),
                           nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)

    value_text = Column(Text)
    value_number = Column(Numeric(16, 4))
    value_date = Column(Date)
    value_bool = Column(Boolean)

    definition = relationship("CustomFieldDefinition", back_populates="values")

    __table_args__ = (
        UniqueConstraint("definition_id", "entity_type", "entity_id",
                         name="uq_value_per_record"),
        Index("ix_custom_value_entity", "entity_type", "entity_id"),
    )

    def as_python(self):
        kind = self.definition.field_type if self.definition else "text"
        if kind == "number":
            return float(self.value_number) if self.value_number is not None else None
        if kind == "date":
            return self.value_date.isoformat() if self.value_date else None
        if kind == "boolean":
            return self.value_bool
        return self.value_text


class Attachment(Base):
    """A file attached to a profile section.

    The binary lives on disk (an on-premise volume); only metadata is stored
    here. `stored_name` is a generated name, so a user-supplied filename can
    never influence the path on disk.
    """
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)

    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)

    stored_name = Column(String(120), nullable=False, unique=True)
    original_name = Column(String(300), nullable=False)
    content_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    description = Column(String(400))

    uploaded_by = Column(String(100), nullable=False, default="hr")
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_attachment_entity", "entity_type", "entity_id"),)


class User(Base, Stamped):
    """Application account. Roles: admin | viewer."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)

    username = Column(String(60), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    display_name = Column(String(150))
    is_active = Column(Boolean, nullable=False, default=True)
    last_login_at = Column(DateTime)
