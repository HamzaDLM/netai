from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    instructions: str = Field(min_length=1, max_length=12000)
    enabled: bool = True


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    instructions: str | None = Field(default=None, min_length=1, max_length=12000)
    enabled: bool | None = None


class SkillToggle(BaseModel):
    enabled: bool


class SkillResponse(ORMBaseModel):
    id: int
    user_id: int
    name: str
    description: str
    instructions: str
    enabled: bool
    archived: bool
    created_at: datetime
    updated_at: datetime


class ToolCatalogTool(BaseModel):
    python_name: str
    runtime_name: str | None = None
    summary: str


class ToolCatalogAgent(BaseModel):
    agent_key: str
    agent_name: str
    specialist_tool: str | None = None
    tools: list[ToolCatalogTool]


class SkillBootstrapResponse(BaseModel):
    skills: list[SkillResponse]
    catalog: list[ToolCatalogAgent]
