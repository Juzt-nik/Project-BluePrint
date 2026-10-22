from pydantic import BaseModel, Field
from app.models.enums import CaseStatus, ReleaseStatus


class CaseTransitionRequest(BaseModel):
    target_status: CaseStatus
    actor_user_id: str | None = None
    reason: str | None = Field(default=None, max_length=2000)


class ReleaseTransitionRequest(BaseModel):
    target_status: ReleaseStatus
    actor_user_id: str | None = None
    reason: str | None = Field(default=None, max_length=2000)
