from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.engine import EvaluationResult, PhysicalStoreParams
from app.profiles.schemas import RevisionBody, StrictBody


class EvaluationCreate(RevisionBody):
    label: str | None = Field(default=None, max_length=80)


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    profile_id: UUID
    profile_revision: int
    trigger: str
    label: str | None
    template_key: str
    template_version: int
    engine_version: str
    parameters: PhysicalStoreParams
    results: EvaluationResult
    summary: str
    created_at: datetime


class EvaluationLabel(StrictBody):
    label: str | None = Field(max_length=80)


class WhatIfRequest(StrictBody):
    changes: dict[str, Any] = Field(min_length=1, max_length=20)
    evaluation_id: UUID | None = None
    revision: int = Field(ge=1)


class ApplyWhatIf(WhatIfRequest):
    evaluation_id: UUID
