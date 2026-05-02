from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.models.skills import SkillMarketplaceStatus
from app.api.models.users import UserRole


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
    slug: str
    description: str
    instructions: str
    enabled: bool
    archived: bool
    installed_from_listing_id: int | None
    marketplace_listing_id: int | None = None
    marketplace_status: SkillMarketplaceStatus | None = None
    marketplace_review_notes: str = ""
    created_at: datetime
    updated_at: datetime


class SkillMarketplaceListingResponse(ORMBaseModel):
    id: int
    owner_user_id: int
    owner_skill_id: int
    name: str
    slug: str
    description: str
    instructions: str
    status: SkillMarketplaceStatus
    review_notes: str
    reviewed_by_user_id: int | None
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
    viewer_role: UserRole
    skills: list[SkillResponse]
    catalog: list[ToolCatalogAgent]
    marketplace: list[SkillMarketplaceListingResponse]
    review_queue: list[SkillMarketplaceListingResponse]


class SkillMarketplaceReview(BaseModel):
    review_notes: str = Field(default="", max_length=4000)
