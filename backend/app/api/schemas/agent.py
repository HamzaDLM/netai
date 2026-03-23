from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int | None = Field(default=None, ge=1, le=50)


class AgentEvidence(BaseModel):
    source: str
    content: str
    score: float


class AgentAskResponse(BaseModel):
    answer: str
    selected_capability: str
    confidence: float
    fallback_used: bool = False
    filters: dict = Field(default_factory=dict)
    evidence: list[AgentEvidence] = Field(default_factory=list)
    execution_trace: list[str] = Field(default_factory=list)
