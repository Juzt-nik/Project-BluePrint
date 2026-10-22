from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.enums import DepositMethod, DepositStatus


class DepositCreate(BaseModel):
    institution_id: str
    internal_reference: str = Field(min_length=2, max_length=80)
    deposit_method: DepositMethod
    security_term_start_date: date | None = None
    security_term_end_date: date | None = None
    applicable_rule_reference: str | None = Field(default=None, max_length=150)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_term(self):
        if self.security_term_start_date and self.security_term_end_date:
            if self.security_term_end_date < self.security_term_start_date:
                raise ValueError("Security term end date cannot precede start date.")
        return self


class DepositRead(DepositCreate):
    id: str
    status: DepositStatus
    model_config = ConfigDict(from_attributes=True)


class DepositTransitionRequest(BaseModel):
    target_status: DepositStatus
    reason: str | None = Field(default=None, max_length=2000)
