from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.models.evals import EvalEvaluatorKind, EvalEvaluatorRule, EvalRunStatus


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class EvalEvaluatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: EvalEvaluatorKind
    rule: EvalEvaluatorRule | None = None
    description: str = Field(default="", max_length=500)
    criteria: str = Field(min_length=1, max_length=10_000)
    threshold: int = Field(default=85, ge=0, le=100)

    @model_validator(mode="after")
    def validate_rule(self) -> "EvalEvaluatorCreate":
        if self.kind == EvalEvaluatorKind.llm_judge:
            self.rule = EvalEvaluatorRule.llm_judge
        elif self.rule not in {
            EvalEvaluatorRule.tool_trajectory,
            EvalEvaluatorRule.completion_safety,
        }:
            raise ValueError("deterministic evaluators require a supported rule")
        return self


class EvalEvaluatorResponse(ORMBaseModel):
    id: str
    name: str
    kind: EvalEvaluatorKind
    rule: EvalEvaluatorRule
    description: str
    criteria: str
    threshold: int
    builtin: bool
    used_by: int = 0
    created_at: datetime


class EvalScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    prompt: str = Field(min_length=1, max_length=50_000)
    fixture: str = Field(default="", max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    required_tools: list[str] = Field(default_factory=list, max_length=100)
    forbidden_tools: list[str] = Field(default_factory=list, max_length=100)
    expected_facts: list[str] = Field(default_factory=list, max_length=100)
    evaluator_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator(
        "tags", "required_tools", "forbidden_tools", "expected_facts", "evaluator_ids"
    )
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        return _clean_list(values)


class EvalScenarioUpdate(EvalScenarioCreate):
    pass


class EvalScenarioResponse(ORMBaseModel):
    id: str
    name: str
    description: str
    owner: str
    tags: list[str]
    prompt: str
    fixture: str
    required_tools: list[str]
    forbidden_tools: list[str]
    expected_facts: list[str]
    evaluator_ids: list[str]
    enabled: bool
    last_run_id: str | None = None
    created_at: datetime


class EvalScenarioToggle(BaseModel):
    enabled: bool


class EvalEvaluatorUpdate(EvalEvaluatorCreate):
    pass


class EvalToolCallResponse(BaseModel):
    id: str
    name: str
    connector: str
    status: str
    expectation: str
    duration_ms: int
    summary: str


class EvalCheckResponse(BaseModel):
    id: str
    name: str
    kind: EvalEvaluatorKind
    status: str
    score: int
    detail: str


class EvalRunResponse(ORMBaseModel):
    id: str
    scenario_id: str
    scenario_name: str
    status: EvalRunStatus
    score: float | None
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    model: str
    version: str
    answer: str
    tool_calls: list[EvalToolCallResponse]
    checks: list[EvalCheckResponse]
    error: str | None
