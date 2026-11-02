"""Editable, versioned candidate assessment. No executable rules or formulas."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class CandidateSourceRule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operator: Literal['eq', 'gte', 'lte', 'present'] = 'eq'
    value: str | bool | int | float
    points: Decimal = Field(ge=0, le=10000, max_digits=8, decimal_places=2)


class CandidateSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['manual', 'dossier_field', 'dossier_fact', 'tab_field'] = 'manual'
    field_id: int | None = Field(default=None, gt=0)
    fact: Literal['education_level', 'language_level', 'company_experience_years'] | None = None
    argument: int | None = Field(default=None, gt=0)
    scale_id: int | None = Field(default=None, gt=0)
    rules: list[CandidateSourceRule] = Field(default_factory=list, max_length=20)
    # These are server-owned, accepted for a round trip and recomputed on save.
    visibility: Literal['public', 'admin'] = 'public'
    label_ru: str | None = None
    label_kk: str | None = None


class CandidateCriterionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: int | None = Field(default=None, gt=0)
    position: int = Field(ge=3, le=1000000)
    section_key: str | None = Field(default=None, min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    display_order: int | None = Field(default=None, ge=0, le=1000000)
    name_ru: str = Field(min_length=1, max_length=200)
    name_kk: str = Field(min_length=1, max_length=200)
    max_points: Decimal = Field(gt=0, le=10000, max_digits=8, decimal_places=2)
    enabled: bool = True
    source: CandidateSource | None = None

    @field_validator('name_ru', 'name_kk')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Название не может быть пустым / Атау бос болмауы керек')
        return value


class CandidateSectionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    name_ru: str = Field(min_length=1, max_length=200)
    name_kk: str = Field(min_length=1, max_length=200)
    kind: Literal['general', 'technical', 'psychological'] = 'general'
    position: int = Field(default=0, ge=0, le=1000000)

    @field_validator('name_ru', 'name_kk')
    @classmethod
    def clean_name(cls, value):
        return CandidateCriterionIn.clean_name(value)


class CandidateCreateIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name_ru: str = Field(min_length=1, max_length=200)
    name_kk: str = Field(min_length=1, max_length=200)
    template_id: int | None = Field(default=None, gt=0)

    @field_validator('name_ru', 'name_kk')
    @classmethod
    def clean_name(cls, value):
        return CandidateCriterionIn.clean_name(value)


class CandidateMethodologyIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name_ru: str = Field(min_length=1, max_length=200)
    name_kk: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
    criteria: list[CandidateCriterionIn] = Field(default_factory=list, max_length=500)
    sections: list[CandidateSectionIn] | None = Field(default=None, max_length=50)

    @field_validator('name_ru', 'name_kk')
    @classmethod
    def clean_name(cls, value):
        return CandidateCriterionIn.clean_name(value)

    @field_validator('criteria')
    @classmethod
    def complete_positions(cls, values):
        if len({row.position for row in values}) != len(values):
            raise ValueError('Повторяющиеся ключи показателей / Қайталанатын көрсеткіш кілттері')
        return values

    @field_validator('sections')
    @classmethod
    def unique_sections(cls, values):
        if values is not None and len({row.key for row in values}) != len(values):
            raise ValueError('Повторяющиеся разделы / Қайталанатын бөлімдер')
        return values


class CandidateActivateIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)


class CandidateScoreIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    position: int = Field(ge=3, le=1000000)
    points: Decimal = Field(ge=0, le=10000, max_digits=8, decimal_places=2)


class CandidateEvaluationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    methodology_id: int = Field(gt=0)
    expected_revision: int = Field(ge=0)
    technical_profile: bool
    scores: list[CandidateScoreIn] = Field(max_length=500)
    note: str = Field(default='', max_length=2000)
    source_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    confirm_sources: bool = False

    @field_validator('scores')
    @classmethod
    def unique_positions(cls, values):
        if len({row.position for row in values}) != len(values):
            raise ValueError('Повторяющиеся показатели / Қайталанатын көрсеткіштер')
        return values
