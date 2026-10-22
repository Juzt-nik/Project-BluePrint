from pydantic import BaseModel, ConfigDict, Field


class InstitutionCreate(BaseModel):
    institution_code: str = Field(min_length=2, max_length=50)
    legal_name: str = Field(min_length=2, max_length=255)
    institution_type: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    is_synthetic: bool = True


class InstitutionRead(InstitutionCreate):
    id: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)
