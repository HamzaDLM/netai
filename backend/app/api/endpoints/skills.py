from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import AsyncSessionDep, CheckUserSSODep
from app.api.models.skills import Skill
from app.api.schemas.skills import (
    SkillBootstrapResponse,
    SkillCreate,
    SkillResponse,
    SkillToggle,
    SkillUpdate,
    ToolCatalogAgent,
)
from app.skills_catalog import get_agent_tool_catalog

router = APIRouter(prefix="/skills", tags=["skills"])


async def _get_user_skill(db: AsyncSessionDep, skill_id: int, user_id: int) -> Skill:
    stmt = select(Skill).where(
        Skill.id == skill_id,
        Skill.user_id == user_id,
        Skill.archived.is_(False),
    )
    result = await db.execute(stmt)
    skill = result.scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return skill


async def _skill_name_exists(
    db: AsyncSessionDep,
    *,
    user_id: int,
    name: str,
    exclude_skill_id: int | None = None,
) -> bool:
    stmt = select(Skill.id).where(
        Skill.user_id == user_id,
        Skill.archived.is_(False),
        func.lower(Skill.name) == name.strip().lower(),
    )
    if exclude_skill_id is not None:
        stmt = stmt.where(Skill.id != exclude_skill_id)
    result = await db.execute(stmt.limit(1))
    return result.scalar_one_or_none() is not None


@router.get("", response_model=list[SkillResponse])
async def list_skills(db: AsyncSessionDep, user: CheckUserSSODep):
    stmt = (
        select(Skill)
        .where(
            Skill.user_id == user.id,
            Skill.archived.is_(False),
        )
        .order_by(Skill.created_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/catalog", response_model=list[ToolCatalogAgent])
async def get_tool_catalog():
    return [ToolCatalogAgent.model_validate(item) for item in get_agent_tool_catalog()]


@router.get("/bootstrap", response_model=SkillBootstrapResponse)
async def get_skills_bootstrap(db: AsyncSessionDep, user: CheckUserSSODep):
    stmt = (
        select(Skill)
        .where(
            Skill.user_id == user.id,
            Skill.archived.is_(False),
        )
        .order_by(Skill.created_at.asc())
    )
    result = await db.execute(stmt)
    skills = [SkillResponse.model_validate(item) for item in result.scalars().all()]
    catalog = [
        ToolCatalogAgent.model_validate(item) for item in get_agent_tool_catalog()
    ]
    return SkillBootstrapResponse(
        skills=skills,
        catalog=catalog,
    )


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: SkillCreate, db: AsyncSessionDep, user: CheckUserSSODep
):
    if await _skill_name_exists(db, user_id=user.id, name=payload.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="skill_name_already_exists",
        )

    skill = Skill(
        user_id=user.id,
        name=payload.name.strip(),
        instructions=payload.instructions.strip(),
        enabled=payload.enabled,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: int,
    payload: SkillUpdate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    skill = await _get_user_skill(db, skill_id=skill_id, user_id=user.id)

    if payload.name is not None:
        if await _skill_name_exists(
            db,
            user_id=user.id,
            name=payload.name,
            exclude_skill_id=skill.id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="skill_name_already_exists",
            )
        skill.name = payload.name.strip()

    if payload.instructions is not None:
        skill.instructions = payload.instructions.strip()

    if payload.enabled is not None:
        skill.enabled = payload.enabled

    await db.commit()
    await db.refresh(skill)
    return skill


@router.patch("/{skill_id}/enabled", response_model=SkillResponse)
async def toggle_skill_enabled(
    skill_id: int,
    payload: SkillToggle,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    skill = await _get_user_skill(db, skill_id=skill_id, user_id=user.id)
    skill.enabled = payload.enabled
    await db.commit()
    await db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: int, db: AsyncSessionDep, user: CheckUserSSODep):
    skill = await _get_user_skill(db, skill_id=skill_id, user_id=user.id)
    skill.archived = True
    await db.commit()
