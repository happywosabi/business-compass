"""档案请求与响应；参数硬性约束复用计算引擎模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.engine import PhysicalStoreParams
from app.templates.loader import ParamSpec

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
ProfileStage = Literal["idea", "preparing", "operating"]
ProfileStatus = Literal["draft", "active", "archived"]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ProfileCreate(StrictBody):
    name: Name
    industry: str = Field(default="drinks", max_length=40)
    template_key: Literal["physical_store"] = "physical_store"
    city: City
    district: str | None = Field(default=None, max_length=60)
    stage: ProfileStage = "idea"
    opened_on: date | None = None
    parameters: PhysicalStoreParams = Field(default_factory=PhysicalStoreParams)


class RevisionBody(StrictBody):
    revision: int = Field(ge=1)


class ProfileUpdate(RevisionBody):
    name: Name | None = None
    city: City | None = None
    district: str | None = Field(default=None, max_length=60)
    stage: ProfileStage | None = None
    status: ProfileStatus | None = None
    opened_on: date | None = None
    value_proposition: dict[str, str] | None = None

    @field_validator("name", "city", "stage", "status", "value_proposition")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("此字段不能清空")
        return value


class ParametersUpdate(RevisionBody):
    changes: dict[str, Any] = Field(min_length=1, max_length=40)
    reason: str | None = Field(default=None, max_length=1000)


class DefaultRequest(RevisionBody):
    keys: list[str] = Field(min_length=1, max_length=40)


class ProfileCopy(RevisionBody):
    name: Name | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    template_key: str
    template_version: int
    industry: str
    city: str
    district: str | None
    stage: ProfileStage
    status: ProfileStatus
    opened_on: date | None
    value_proposition: dict[str, Any]
    parameters: PhysicalStoreParams
    revision: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    quick_missing: list[str]
    derived_stale_keys: list[str]


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    profile_revision: int
    parameter_key: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    source: str
    reason: str | None
    created_at: datetime


class IndustryOut(BaseModel):
    code: str
    label: str


class FieldOut(ParamSpec):
    value_schema: dict[str, Any]


class TemplateOut(BaseModel):
    key: str
    version: int
    label: str
    industries: list[IndustryOut]
    fields: list[FieldOut]
    definitions: dict[str, Any]
    defaults_provisional: bool = True
