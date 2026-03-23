from pydantic import BaseModel, Field


class LogAskRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int | None = Field(default=None, ge=1, le=50)


class LogEvidence(BaseModel):
    source: str
    content: str
    score: float


class LogAskResponse(BaseModel):
    answer: str
    filters: dict
    evidence: list[LogEvidence]
    used_llm: bool
