from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime


class ORMModel(BaseModel):
    # protected_namespaces=() so fields such as `model_id` are allowed.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# ---------------------------------------------------------------------------
# Reference data (generic)
# ---------------------------------------------------------------------------

class RefBase(BaseModel):
    code: str
    name_ru: str
    name_kk: Optional[str] = None
    name_en: Optional[str] = None


class RefCreate(RefBase):
    extra: Dict[str, Any] = Field(default_factory=dict)


class RefUpdate(BaseModel):
    code: Optional[str] = None
    name_ru: Optional[str] = None
    name_kk: Optional[str] = None
    name_en: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class RefOut(ORMModel):
    id: int
    code: str
    name_ru: str
    name_kk: Optional[str] = None
    name_en: Optional[str] = None


# ---------------------------------------------------------------------------
# Employee sub-entities
# ---------------------------------------------------------------------------

class EducationIn(BaseModel):
    level_id: int
    institution: str
    country_id: Optional[int] = None
    field_id: Optional[int] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    qualification: Optional[str] = None
    document_ref: Optional[str] = None


class EducationOut(EducationIn, ORMModel):
    id: int
    employee_id: int


class LanguageIn(BaseModel):
    language_id: int
    scale_id: int
    level_id: int
    is_confirmed: bool = False
    document: Optional[str] = None
    confirmed_at: Optional[date] = None
    valid_until: Optional[date] = None


class LanguageOut(LanguageIn, ORMModel):
    id: int
    employee_id: int


class TrainingIn(BaseModel):
    name: str
    training_type_id: Optional[int] = None
    job_family_id: Optional[int] = None
    provider: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    result: Optional[str] = None
    certificate_ref: Optional[str] = None
    valid_until: Optional[date] = None


class TrainingOut(TrainingIn, ORMModel):
    id: int
    employee_id: int


class WorkExperienceIn(BaseModel):
    is_internal: bool = True
    org_unit_id: Optional[int] = None
    external_employer: Optional[str] = None
    position_id: Optional[int] = None
    external_position_title: Optional[str] = None
    job_family_id: int
    org_unit_type_id: int
    country_id: Optional[int] = None
    management_level: int = 0
    date_from: date
    date_to: Optional[date] = None


class WorkExperienceOut(WorkExperienceIn, ORMModel):
    id: int
    employee_id: int


class CompetencyScoreIn(BaseModel):
    competency_id: int
    score: float


class CompetencyScoreOut(ORMModel):
    id: int
    competency_id: int
    score: float


class AssessmentSessionIn(BaseModel):
    session_type: str = "professional"
    scale_id: int
    session_date: date
    assessor: Optional[str] = None
    conclusion_text: Optional[str] = None
    valid_until: Optional[date] = None
    scores: List[CompetencyScoreIn] = Field(default_factory=list)


class AssessmentSessionOut(ORMModel):
    id: int
    employee_id: int
    session_type: str
    scale_id: int
    session_date: date
    assessor: Optional[str] = None
    conclusion_text: Optional[str] = None
    status: str
    scores: List[CompetencyScoreOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

class EmployeeIn(BaseModel):
    personnel_number: Optional[str] = None
    last_name: str
    first_name: str
    middle_name: Optional[str] = None
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    birth_country_id: Optional[int] = None
    nationality_id: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    current_position_id: Optional[int] = None
    current_org_unit_id: Optional[int] = None
    employment_status: str = "active"


class EmployeeUpdate(BaseModel):
    personnel_number: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    birth_country_id: Optional[int] = None
    nationality_id: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    current_position_id: Optional[int] = None
    current_org_unit_id: Optional[int] = None
    employment_status: Optional[str] = None
    profile_status: Optional[str] = None


class EmployeeOut(ORMModel):
    id: int
    personnel_number: Optional[str] = None
    anonymous_code: Optional[str] = None
    last_name: str
    first_name: str
    middle_name: Optional[str] = None
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    birth_country_id: Optional[int] = None
    nationality_id: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    current_position_id: Optional[int] = None
    current_org_unit_id: Optional[int] = None
    employment_status: str
    profile_status: str
    created_at: datetime


class EmployeeDetail(EmployeeOut):
    educations: List[EducationOut] = Field(default_factory=list)
    languages: List[LanguageOut] = Field(default_factory=list)
    trainings: List[TrainingOut] = Field(default_factory=list)
    work_experience: List[WorkExperienceOut] = Field(default_factory=list)
    assessment_sessions: List[AssessmentSessionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Methodology
# ---------------------------------------------------------------------------

class ScoringFunctionIn(BaseModel):
    code: str
    name_ru: str
    name_kk: Optional[str] = None
    name_en: Optional[str] = None
    kind: str = "linear"
    breakpoints: List[Dict[str, Any]] = Field(default_factory=list)


class ScoringFunctionOut(ScoringFunctionIn, ORMModel):
    id: int
    model_id: int


class CompensationTableIn(BaseModel):
    code: str
    name_ru: str
    name_kk: Optional[str] = None
    name_en: Optional[str] = None
    entries: List[Dict[str, Any]] = Field(default_factory=list)


class CompensationTableOut(CompensationTableIn, ORMModel):
    id: int
    model_id: int


class ReadinessBandIn(BaseModel):
    code: str
    name_ru: str
    name_kk: Optional[str] = None
    name_en: Optional[str] = None
    min_score: float
    color: Optional[str] = None


class ReadinessBandOut(ReadinessBandIn, ORMModel):
    id: int
    model_id: int


class ScoringModelIn(BaseModel):
    version: str
    name: str
    description: Optional[str] = None
    status: str = "draft"


class ScoringModelOut(ORMModel):
    id: int
    version: str
    name: str
    description: Optional[str] = None
    status: str
    is_default: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ScoringModelDetail(ScoringModelOut):
    functions: List[ScoringFunctionOut] = Field(default_factory=list)
    compensations: List[CompensationTableOut] = Field(default_factory=list)
    readiness_bands: List[ReadinessBandOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Vacancies & requirements
# ---------------------------------------------------------------------------

class RequirementIn(BaseModel):
    requirement_type_id: int
    label_ru: str
    label_kk: Optional[str] = None
    label_en: Optional[str] = None
    condition: Dict[str, Any] = Field(default_factory=dict)
    weight: int = 0
    criticality: str = "must"
    scoring_function_id: Optional[int] = None
    compensation_table_id: Optional[int] = None
    sort_order: int = 0


class RequirementUpdate(BaseModel):
    label_ru: Optional[str] = None
    label_kk: Optional[str] = None
    label_en: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None
    weight: Optional[int] = None
    criticality: Optional[str] = None
    scoring_function_id: Optional[int] = None
    compensation_table_id: Optional[int] = None
    sort_order: Optional[int] = None


class RequirementOut(ORMModel):
    id: int
    vacancy_id: Optional[int] = None
    profile_id: Optional[int] = None
    requirement_type_id: int
    label_ru: str
    label_kk: Optional[str] = None
    label_en: Optional[str] = None
    condition: Dict[str, Any]
    weight: int
    criticality: str
    scoring_function_id: Optional[int] = None
    compensation_table_id: Optional[int] = None
    sort_order: Optional[int] = 0


class PositionProfileIn(BaseModel):
    code: str
    name_ru: str
    name_kk: Optional[str] = None
    name_en: Optional[str] = None
    job_family_id: Optional[int] = None
    grade_id: Optional[int] = None
    description: Optional[str] = None


class PositionProfileOut(PositionProfileIn, ORMModel):
    id: int


class VacancyIn(BaseModel):
    profile_id: Optional[int] = None
    title: str
    country_id: int
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    status: str = "draft"


class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    country_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None


class VacancyOut(ORMModel):
    id: int
    profile_id: Optional[int] = None
    title: str
    country_id: int
    org_unit_id: Optional[int] = None
    description: Optional[str] = None
    status: str
    requirements_version: int
    created_at: datetime


class VacancyDetail(VacancyOut):
    requirements: List[RequirementOut] = Field(default_factory=list)
    total_weight: int = 0


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

class MatchingRunIn(BaseModel):
    vacancy_id: int
    scoring_model_id: Optional[int] = None
    employee_ids: Optional[List[int]] = None
    verified_only: bool = True


class MatchingRunOut(ORMModel):
    id: int
    vacancy_id: int
    scoring_model_id: int
    status: str
    total_evaluated: Optional[int] = 0
    total_qualified: Optional[int] = 0
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class DecisionIn(BaseModel):
    decision: str
    final_rank: Optional[int] = None
    reason: Optional[str] = None
    decided_by: str = "hr"


class DecisionOut(ORMModel):
    id: int
    result_id: int
    system_rank: int
    final_rank: Optional[int] = None
    decision: str
    reason: Optional[str] = None
    decided_by: str
    decided_at: datetime
