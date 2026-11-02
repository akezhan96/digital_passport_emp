"""Normalised data model for the Digital Employee Profile.

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
    Numeric, JSON, UniqueConstraint, CheckConstraint, Index,
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
    from sqlalchemy.ext.hybrid import hybrid_property

    @hybrid_property
    def is_confidential(self):
        return bool(self.category and self.category.is_confidential)

    @is_confidential.expression
    def is_confidential(cls):
        return cls.category.has(CompetencyCategory.is_confidential.is_(True))
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
    __table_args__ = (
        UniqueConstraint("code", name="uq_org_unit_code"),
        # Walked once per level when the tree is built, and checked before a
        # unit may be removed.
        Index("ix_org_unit_parent", "parent_id"),
    )


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


class StaffingPosition(Base, Stamped):
    """One line of a unit's establishment: a post that exists there, and how
    many people it is budgeted for.

    The distinction that matters: `Position` is the catalogue of job titles --
    "Ведущий специалист" exists once for the whole company. A StaffingPosition
    is that title *established in a particular unit*, with a headcount. Unit 1
    may hold seven posts across four titles, and Unit 2 may hold fifteen.

    Occupancy is never stored. Who currently holds a post is derived from the
    open work-experience intervals pointing at the same unit and title, so the
    establishment cannot drift out of step with the career record the way a
    counter maintained by hand always eventually does.
    """
    __tablename__ = "staffing_positions"
    id = Column(Integer, primary_key=True)
    org_unit_id = Column(Integer, ForeignKey("org_units.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)

    # Budgeted slots for this title in this unit ("3 ед." on a staffing table).
    headcount = Column(Integer, nullable=False, default=1)
    # The grade the post is established at, which may differ from the default
    # grade of the title elsewhere in the company.
    grade_id = Column(Integer, ForeignKey("ref_position_grades.id"))
    notes = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)

    org_unit = relationship("OrgUnit")
    position = relationship("Position")
    grade = relationship("PositionGrade")

    __table_args__ = (
        UniqueConstraint("org_unit_id", "position_id",
                         name="uq_staffing_unit_position"),
        CheckConstraint("headcount >= 0", name="ck_staffing_headcount"),
    )


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
    is_technical_specialist = Column(Boolean, nullable=False, default=False,
                                     server_default=text("false"))
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
    candidate_evaluations = relationship("CandidateEvaluation", back_populates="employee",
                                         cascade="all, delete-orphan")

    @property
    def full_name(self):
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class EmployeePersonnelRecord(Base, Stamped):
    """One documented contract, rank award or recognition in an employee's dossier."""
    __tablename__ = 'employee_personnel_records'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    kind = Column(String(16), nullable=False)
    title = Column(String(180), nullable=False, default='')
    event_date = Column(Date, nullable=False)
    end_date = Column(Date)
    indefinite = Column(Boolean, nullable=False, default=False)
    planned_date = Column(Date)
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}
    __table_args__ = (
        CheckConstraint("kind IN ('contract','rank','recognition')", name='ck_personnel_record_kind'),
        CheckConstraint("kind = 'contract' OR (end_date IS NULL AND NOT indefinite)", name='ck_personnel_contract_fields'),
        CheckConstraint("end_date IS NULL OR (end_date >= event_date AND NOT indefinite)", name='ck_personnel_end_date'),
        CheckConstraint("planned_date IS NULL OR (kind = 'rank' AND planned_date >= event_date)", name='ck_personnel_planned_date'),
        CheckConstraint("kind = 'contract' OR length(trim(title)) > 0", name='ck_personnel_title'),
        Index('ix_personnel_employee_kind_date', 'employee_id', 'kind', 'event_date', 'id'),
        {'sqlite_autoincrement': True},
    )


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

    __table_args__ = (Index("ix_education_employee", "employee_id"),)


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

    __table_args__ = (Index("ix_training_employee", "employee_id"),)


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

    # How this posting came about. An appointment made through the system
    # links back to the vacancy and decision that produced it, so the career
    # timeline doubles as the record of every transfer.
    appointment_type = Column(String(20), nullable=False, default="initial")
    source_vacancy_id = Column(Integer, ForeignKey("vacancies.id"))
    source_result_id = Column(Integer, ForeignKey("matching_results.id"))

    employee = relationship("Employee", back_populates="work_experience")
    source_vacancy = relationship("Vacancy", foreign_keys=[source_vacancy_id])
    org_unit = relationship("OrgUnit")
    position = relationship("Position")
    job_family = relationship("JobFamily")
    org_unit_type = relationship("OrgUnitType")
    country = relationship("Country")

    __table_args__ = (
        Index("ix_work_exp_employee", "employee_id", "date_from"),
        # Who currently holds which post: derived on every staffing view and
        # before every appointment. Partial, because only open postings are
        # ever asked for and closed ones accumulate for ever.
        Index("ix_work_exp_open_post", "org_unit_id", "position_id",
              postgresql_where=text("date_to IS NULL")),
        # Checked when a unit is deleted, and used by the org tree.
        Index("ix_work_exp_org_unit", "org_unit_id"),
    )


class DisposalPeriod(Base, Stamped):
    """Days out of post, inclusive of both boundaries. An open period has no end."""
    __tablename__ = "disposal_periods"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date)
    org_unit_id = Column(Integer, ForeignKey("org_units.id", ondelete="SET NULL"))
    reason = Column(Text)
    # Snapshot IDs deliberately survive removal of an old post or manual period.
    # Undo checks that the original records still exist before restoring anything.
    previous_position_id = Column(Integer)
    previous_org_unit_id = Column(Integer)
    closed_work_id = Column(Integer)
    closed_work_end = Column(Date)
    closed_work_post = Column(JSON)
    __table_args__ = (
        CheckConstraint("date_to IS NULL OR date_to >= date_from", name="ck_disposal_order"),
        UniqueConstraint("employee_id", "date_from", name="uq_disposal_start"),
        Index("uq_disposal_open", "employee_id", unique=True,
              postgresql_where=text("date_to IS NULL"), sqlite_where=text("date_to IS NULL")),
        {"sqlite_autoincrement": True},
    )


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

    __table_args__ = (Index("ix_session_employee", "employee_id",
                            "session_date"),)


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
    title_kk = Column(String(200))
    country_id = Column(Integer, ForeignKey("ref_countries.id"), nullable=False)
    org_unit_id = Column(Integer, ForeignKey("org_units.id"))
    description = Column(Text)
    description_kk = Column(Text)
    status = Column(String(30), nullable=False, default="draft")
    requirements_version = Column(Integer, nullable=False, default=1)
    candidate_methodology_id = Column(Integer, ForeignKey('candidate_methodologies.id'))
    min_candidate_percent = Column(Numeric(5, 2), nullable=False, default=70)
    requires_technical_profile = Column(Boolean, nullable=False, default=False)

    candidate_methodology = relationship('CandidateMethodology')
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

    @property
    def assessment_mode(self):
        return 'candidate' if self.candidate_methodology_id else 'legacy'


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

    __table_args__ = (Index("ix_requirement_vacancy", "vacancy_id",
                            "sort_order"),)
    scoring_function = relationship("ScoringFunction")
    compensation_table = relationship("CompensationTable")


# ===========================================================================
# MATCHING & DECISIONS
# ===========================================================================

class MatchingRun(Base):
    __tablename__ = "matching_runs"
    id = Column(Integer, primary_key=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"), nullable=False)
    scoring_model_id = Column(Integer, ForeignKey("scoring_models.id"))
    candidate_methodology_id = Column(Integer, ForeignKey('candidate_methodologies.id'))
    methodology_snapshot = Column(JSON)
    include_confidential = Column(Boolean, nullable=False, default=False)
    requirements_version = Column(Integer, nullable=False, default=1)

    status = Column(String(20), nullable=False, default="processing")
    total_evaluated = Column(Integer, default=0)
    total_qualified = Column(Integer, default=0)
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100))
    completed_at = Column(DateTime)

    vacancy = relationship("Vacancy", back_populates="matching_runs")

    __table_args__ = (Index("ix_run_vacancy", "vacancy_id", "created_at"),)
    scoring_model = relationship("ScoringModel")
    candidate_methodology = relationship('CandidateMethodology')
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

    __table_args__ = (
        # The ranked list of one run -- the shape every result page asks for.
        Index("ix_result_run_rank", "run_id", "system_rank"),
        # Checked before a profile may be deleted, and grows fastest of all:
        # one row per candidate per run.
        Index("ix_result_employee", "employee_id"),
    )
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
    visibility = Column(String(16), nullable=False, default='public', server_default='public')
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


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"
    id = Column(String(36), primary_key=True)
    owner = Column(String(60), ForeignKey("users.username"), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AssistantRequest(Base):
    """Private, local request history. Never exported in support diagnostics."""
    __tablename__ = "assistant_requests"
    id = Column(String(36), primary_key=True)
    owner = Column(String(60), ForeignKey("users.username"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("assistant_conversations.id"), index=True)
    kind = Column(String(20), nullable=False, default="query")
    prompt = Column(Text, nullable=False)
    lang = Column(String(2), nullable=False)
    model = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    plan = Column(JSON)
    error_code = Column(String(50))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)
    __table_args__ = (Index("ix_assistant_owner_created", "owner", "created_at"),)


class AssistantReport(Base):
    """Private immutable report snapshot, excluded from support exports."""
    __tablename__ = "assistant_reports"
    id = Column(String(36), primary_key=True)
    owner = Column(String(60), ForeignKey("users.username"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("assistant_conversations.id"), index=True)
    request_id = Column(String(36), ForeignKey("assistant_requests.id"), nullable=False)
    title = Column(String(180), nullable=False)
    spec = Column(JSON, nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


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
    auth_version = Column(Integer, nullable=False, default=0)


# ===========================================================================
# USER-DEFINED CATALOGUES
#
# The built-in catalogues are real tables with real foreign keys. These are
# for classifications the organisation invents later -- award types, project
# codes, anything the system was not born knowing about. Same shape over the
# API, so the admin screen treats both alike.
# ===========================================================================

class CustomCatalog(Base, Named, Stamped):
    __tablename__ = "custom_catalogs"
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)

    items = relationship("CustomCatalogItem", back_populates="catalog",
                         cascade="all, delete-orphan",
                         order_by="CustomCatalogItem.sort_order")
    __table_args__ = (UniqueConstraint("code", name="uq_custom_catalog_code"),)


class CustomCatalogItem(Base, Named, Stamped):
    __tablename__ = "custom_catalog_items"
    id = Column(Integer, primary_key=True)
    catalog_id = Column(Integer, ForeignKey("custom_catalogs.id"), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    catalog = relationship("CustomCatalog", back_populates="items")
    __table_args__ = (
        UniqueConstraint("catalog_id", "code", name="uq_item_per_catalog"),
    )


# ===========================================================================
# USER-BUILT ANALYTICS QUERIES
#
# The ready-made questions stay. This is the other half: a query the user
# assembles from fields, operators and values, then saves and re-runs.
# ===========================================================================

class SavedQuery(Base, Stamped):
    __tablename__ = "saved_queries"
    id = Column(Integer, primary_key=True)

    name = Column(String(200), nullable=False)
    description = Column(Text)

    # {"match": "all" | "any",
    #  "conditions": [{"field": "...", "argument": "...",
    #                  "operator": ">=", "value": 5}, ...]}
    definition = Column(JSON, nullable=False, default=dict)
    group_by = Column(String(80))

    is_shared = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(100), nullable=False, default="hr")
    last_run_at = Column(DateTime)
    last_run_count = Column(Integer)

    __table_args__ = (Index("ix_saved_query_owner", "created_by"),)

# Candidate point methodology. Active definitions and submitted evaluations are
# immutable: a change creates a new methodology/evaluation revision.
class CandidateMethodology(Base, Stamped):
    __tablename__ = 'candidate_methodologies'
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, unique=True)
    name_ru = Column(String(200), nullable=False)
    name_kk = Column(String(200), nullable=False)
    status = Column(String(16), nullable=False, default='draft')
    revision = Column(Integer, nullable=False, default=1)
    previous_id = Column(Integer, ForeignKey('candidate_methodologies.id'))
    created_by = Column(String(100), nullable=False)
    activated_by = Column(String(100))
    activated_at = Column(DateTime)
    sections = Column(JSON)
    criteria = relationship('CandidateCriterion', back_populates='methodology',
                            cascade='all, delete-orphan', order_by='CandidateCriterion.position')
    __table_args__ = (CheckConstraint("status IN ('draft', 'active', 'archived')", name='ck_candidate_method_status'),)


class CandidateCriterion(Base):
    __tablename__ = 'candidate_criteria'
    id = Column(Integer, primary_key=True)
    methodology_id = Column(Integer, ForeignKey('candidate_methodologies.id'), nullable=False)
    position = Column(Integer, nullable=False)
    block = Column(String(20), nullable=False)
    name_ru = Column(String(200), nullable=False)
    name_kk = Column(String(200), nullable=False)
    max_points = Column(Numeric(8, 2), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    source = Column(JSON)
    section_key = Column(String(80))
    display_order = Column(Integer)
    methodology = relationship('CandidateMethodology', back_populates='criteria')
    __table_args__ = (
        UniqueConstraint('methodology_id', 'position', name='uq_candidate_criterion_position'),
        CheckConstraint('position BETWEEN 3 AND 1000000', name='ck_candidate_criterion_position'),
        CheckConstraint('max_points > 0 AND max_points <= 10000', name='ck_candidate_criterion_max'),
        CheckConstraint("block IN ('general', 'technical', 'psychological')", name='ck_candidate_criterion_block'),
    )


class CandidateEvaluation(Base, Stamped):
    __tablename__ = 'candidate_evaluations'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id'), nullable=False)
    methodology_id = Column(Integer, ForeignKey('candidate_methodologies.id'), nullable=False)
    revision = Column(Integer, nullable=False)
    technical_profile = Column(Boolean, nullable=False)
    evaluated_by = Column(String(100), nullable=False)
    note = Column(Text)
    source_fingerprint = Column(String(64))
    source_snapshot = Column(JSON)
    employee = relationship('Employee', back_populates='candidate_evaluations')
    methodology = relationship('CandidateMethodology')
    scores = relationship('CandidateScore', back_populates='evaluation', cascade='all, delete-orphan')
    __table_args__ = (
        UniqueConstraint('employee_id', 'methodology_id', 'revision', name='uq_candidate_evaluation_revision'),
        Index('ix_candidate_evaluation_employee_method', 'employee_id', 'methodology_id', 'id'),
    )


class CandidateScore(Base):
    __tablename__ = 'candidate_scores'
    id = Column(Integer, primary_key=True)
    evaluation_id = Column(Integer, ForeignKey('candidate_evaluations.id'), nullable=False)
    criterion_id = Column(Integer, ForeignKey('candidate_criteria.id'), nullable=False)
    points = Column(Numeric(8, 2), nullable=False)
    source_snapshot = Column(JSON)
    evaluation = relationship('CandidateEvaluation', back_populates='scores')
    criterion = relationship('CandidateCriterion')
    __table_args__ = (
        UniqueConstraint('evaluation_id', 'criterion_id', name='uq_candidate_score'),
        CheckConstraint('points >= 0', name='ck_candidate_score_nonnegative'),
        Index('ix_candidate_score_evaluation', 'evaluation_id'),
    )

# Additional sections shared by employee dossiers; entries belong to one person.
class DossierSubsection(Base, Stamped):
    __tablename__ = 'dossier_subsections'
    id = Column(Integer, primary_key=True)
    tab = Column(String(20), nullable=False)
    name_ru = Column(String(120), nullable=False)
    name_kk = Column(String(120), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    visibility = Column(String(10), nullable=False, default='public')
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}
    __table_args__ = (
        CheckConstraint("visibility IN ('public', 'admin') AND (tab != 'history' OR visibility = 'admin')",
                        name='ck_dossier_subsection_visibility'),
        UniqueConstraint('tab', 'name_ru', name='uq_dossier_subsection_tab_ru'),
        UniqueConstraint('tab', 'name_kk', name='uq_dossier_subsection_tab_kk'),
    )


class DossierSubsectionEntry(Base, Stamped):
    __tablename__ = 'dossier_subsection_entries'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    subsection_id = Column(Integer, ForeignKey('dossier_subsections.id'), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default='')
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}
    __table_args__ = (
        Index('ix_dossier_subsection_employee_entries', 'employee_id', 'subsection_id', 'id'),
        {'sqlite_autoincrement': True},
    )


class DossierTabField(Base, Stamped):
    """A stable field identity shared by the records of one custom tab."""
    __tablename__ = 'dossier_tab_fields'
    id = Column(Integer, primary_key=True)
    subsection_id = Column(Integer, ForeignKey('dossier_subsections.id'), nullable=False)
    name_ru = Column(String(120), nullable=False)
    name_kk = Column(String(120), nullable=False)
    field_type = Column(String(12), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    revision = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}
    __table_args__ = (
        CheckConstraint("field_type IN ('text','date','number','boolean')", name='ck_dossier_tab_field_type'),
        UniqueConstraint('subsection_id', 'name_ru', name='uq_dossier_tab_field_ru'),
        UniqueConstraint('subsection_id', 'name_kk', name='uq_dossier_tab_field_kk'),
        {'sqlite_autoincrement': True},
    )


class DossierTabValue(Base, Stamped):
    __tablename__ = 'dossier_tab_values'
    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey('dossier_subsection_entries.id', ondelete='CASCADE'), nullable=False)
    field_id = Column(Integer, ForeignKey('dossier_tab_fields.id'), nullable=False)
    value = Column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint('entry_id', 'field_id', name='uq_dossier_tab_entry_value'),
        Index('ix_dossier_tab_value_field', 'field_id', 'entry_id'),
    )
