from pydantic import BaseModel, Field


class RuleCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=255)
    dm_message: str = Field(..., min_length=1)


class RuleRead(BaseModel):
    rule_id: int
    keyword: str
    dm_message: str

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "linkplease"
