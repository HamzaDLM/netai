import re
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import AsyncSessionDep, CheckUserSSODep
from app.api.models.skills import Skill, SkillMarketplaceListing, SkillMarketplaceStatus
from app.api.models.users import UserRole
from app.api.schemas.skills import (
    SkillBootstrapResponse,
    SkillCreate,
    SkillMarketplaceListingResponse,
    SkillMarketplaceReview,
    SkillResponse,
    SkillToggle,
    SkillUpdate,
    ToolCatalogAgent,
)
from app.skills_catalog import get_agent_tool_catalog

router = APIRouter(prefix="/skills", tags=["skills"])

_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    normalized = _SLUG_SANITIZE_RE.sub("-", value.strip().lower()).strip("-")
    return normalized[:80] or "skill"


def _marketplace_status_sort_value(status: SkillMarketplaceStatus) -> int:
    if status == SkillMarketplaceStatus.pending:
        return 0
    if status == SkillMarketplaceStatus.rejected:
        return 1
    return 2


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


async def _get_listing_for_owner_skill(
    db: AsyncSessionDep,
    *,
    owner_skill_id: int,
) -> SkillMarketplaceListing | None:
    stmt = select(SkillMarketplaceListing).where(
        SkillMarketplaceListing.owner_skill_id == owner_skill_id,
        SkillMarketplaceListing.archived.is_(False),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_listing_or_404(
    db: AsyncSessionDep,
    *,
    listing_id: int,
) -> SkillMarketplaceListing:
    stmt = select(SkillMarketplaceListing).where(
        SkillMarketplaceListing.id == listing_id,
        SkillMarketplaceListing.archived.is_(False),
    )
    result = await db.execute(stmt)
    listing = result.scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return listing


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


async def _next_unique_skill_slug(
    db: AsyncSessionDep,
    *,
    user_id: int,
    base_name: str,
    exclude_skill_id: int | None = None,
) -> str:
    base_slug = _slugify(base_name)
    suffix = 0
    while True:
        slug = base_slug if suffix == 0 else f"{base_slug}-{suffix + 1}"
        stmt = select(Skill.id).where(
            Skill.user_id == user_id,
            Skill.archived.is_(False),
            Skill.slug == slug,
        )
        if exclude_skill_id is not None:
            stmt = stmt.where(Skill.id != exclude_skill_id)
        result = await db.execute(stmt.limit(1))
        if result.scalar_one_or_none() is None:
            return slug
        suffix += 1


async def _next_unique_listing_slug(
    db: AsyncSessionDep,
    *,
    base_name: str,
    exclude_listing_id: int | None = None,
) -> str:
    base_slug = _slugify(base_name)
    suffix = 0
    while True:
        slug = base_slug if suffix == 0 else f"{base_slug}-{suffix + 1}"
        stmt = select(SkillMarketplaceListing.id).where(
            SkillMarketplaceListing.archived.is_(False),
            SkillMarketplaceListing.slug == slug,
        )
        if exclude_listing_id is not None:
            stmt = stmt.where(SkillMarketplaceListing.id != exclude_listing_id)
        result = await db.execute(stmt.limit(1))
        if result.scalar_one_or_none() is None:
            return slug
        suffix += 1


async def _next_unique_skill_name(
    db: AsyncSessionDep,
    *,
    user_id: int,
    base_name: str,
) -> str:
    name = base_name.strip() or "Imported Skill"
    if not await _skill_name_exists(db, user_id=user_id, name=name):
        return name

    suffix = 2
    while True:
        candidate = f"{name} {suffix}"
        if not await _skill_name_exists(db, user_id=user_id, name=candidate):
            return candidate
        suffix += 1


async def _serialize_skills(
    db: AsyncSessionDep,
    *,
    skills: Sequence[Skill],
) -> list[SkillResponse]:
    if not skills:
        return []

    skill_ids = [skill.id for skill in skills]
    listing_result = await db.execute(
        select(SkillMarketplaceListing).where(
            SkillMarketplaceListing.owner_skill_id.in_(skill_ids),
            SkillMarketplaceListing.archived.is_(False),
        )
    )
    listings_by_skill_id = {
        listing.owner_skill_id: listing for listing in listing_result.scalars().all()
    }

    serialized_skills: list[SkillResponse] = []
    for skill in skills:
        listing = listings_by_skill_id.get(skill.id)
        serialized_skills.append(
            SkillResponse.model_validate(
                {
                    "id": skill.id,
                    "user_id": skill.user_id,
                    "name": skill.name,
                    "slug": skill.slug,
                    "description": skill.description,
                    "instructions": skill.instructions,
                    "enabled": skill.enabled,
                    "archived": skill.archived,
                    "installed_from_listing_id": skill.installed_from_listing_id,
                    "marketplace_listing_id": (
                        listing.id if listing is not None else None
                    ),
                    "marketplace_status": (
                        listing.status if listing is not None else None
                    ),
                    "marketplace_review_notes": (
                        listing.review_notes if listing is not None else ""
                    ),
                    "created_at": skill.created_at,
                    "updated_at": skill.updated_at,
                }
            )
        )
    return serialized_skills


def _serialize_listing(
    listing: SkillMarketplaceListing,
) -> SkillMarketplaceListingResponse:
    return SkillMarketplaceListingResponse.model_validate(listing)


def _require_admin(role: UserRole) -> None:
    if role not in {UserRole.admin, UserRole.superuser}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


async def _sync_listing_from_skill(
    db: AsyncSessionDep,
    *,
    skill: Skill,
    owner_user_id: int,
) -> SkillMarketplaceListing:
    listing = await _get_listing_for_owner_skill(db, owner_skill_id=skill.id)
    if listing is None:
        listing = SkillMarketplaceListing(
            owner_user_id=owner_user_id,
            owner_skill_id=skill.id,
            name=skill.name.strip(),
            slug=await _next_unique_listing_slug(db, base_name=skill.name),
            description=skill.description.strip(),
            instructions=skill.instructions.strip(),
            status=SkillMarketplaceStatus.pending,
            review_notes="",
        )
        db.add(listing)
        return listing

    listing.name = skill.name.strip()
    listing.slug = await _next_unique_listing_slug(
        db,
        base_name=skill.name,
        exclude_listing_id=listing.id,
    )
    listing.description = skill.description.strip()
    listing.instructions = skill.instructions.strip()
    listing.status = SkillMarketplaceStatus.pending
    listing.review_notes = ""
    listing.reviewed_by_user_id = None
    return listing


@router.get("", response_model=list[SkillResponse])
async def list_skills(db: AsyncSessionDep, user: CheckUserSSODep):
    stmt = (
        select(Skill)
        .where(
            Skill.user_id == user.id,
            Skill.archived.is_(False),
        )
        .order_by(Skill.created_at.asc(), Skill.id.asc())
    )
    result = await db.execute(stmt)
    return await _serialize_skills(db, skills=result.scalars().all())


@router.get("/catalog", response_model=list[ToolCatalogAgent])
async def get_tool_catalog():
    return [ToolCatalogAgent.model_validate(item) for item in get_agent_tool_catalog()]


@router.get("/bootstrap", response_model=SkillBootstrapResponse)
async def get_skills_bootstrap(db: AsyncSessionDep, user: CheckUserSSODep):
    skills_result = await db.execute(
        select(Skill)
        .where(
            Skill.user_id == user.id,
            Skill.archived.is_(False),
        )
        .order_by(Skill.created_at.asc(), Skill.id.asc())
    )
    skills = await _serialize_skills(db, skills=skills_result.scalars().all())

    marketplace_result = await db.execute(
        select(SkillMarketplaceListing).where(
            SkillMarketplaceListing.archived.is_(False),
            SkillMarketplaceListing.status == SkillMarketplaceStatus.approved,
            SkillMarketplaceListing.owner_user_id != user.id,
        )
    )
    marketplace = sorted(
        (_serialize_listing(item) for item in marketplace_result.scalars().all()),
        key=lambda item: (item.name.lower(), item.id),
    )

    review_queue: list[SkillMarketplaceListingResponse] = []
    if user.role in {UserRole.admin, UserRole.superuser}:
        pending_result = await db.execute(
            select(SkillMarketplaceListing).where(
                SkillMarketplaceListing.archived.is_(False),
                SkillMarketplaceListing.status == SkillMarketplaceStatus.pending,
            )
        )
        review_queue = sorted(
            (_serialize_listing(item) for item in pending_result.scalars().all()),
            key=lambda item: (
                _marketplace_status_sort_value(item.status),
                item.created_at,
                item.id,
            ),
        )

    catalog = [
        ToolCatalogAgent.model_validate(item) for item in get_agent_tool_catalog()
    ]
    return SkillBootstrapResponse(
        viewer_role=user.role,
        skills=skills,
        catalog=catalog,
        marketplace=marketplace,
        review_queue=review_queue,
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
        slug=await _next_unique_skill_slug(db, user_id=user.id, base_name=payload.name),
        description=payload.description.strip(),
        instructions=payload.instructions.strip(),
        enabled=payload.enabled,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return (await _serialize_skills(db, skills=[skill]))[0]


@router.post("/{skill_id}/share", response_model=SkillResponse)
async def request_skill_share(
    skill_id: int,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    skill = await _get_user_skill(db, skill_id=skill_id, user_id=user.id)
    if skill.installed_from_listing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="marketplace_installs_cannot_be_shared",
        )

    await _sync_listing_from_skill(db, skill=skill, owner_user_id=user.id)
    await db.commit()
    await db.refresh(skill)
    return (await _serialize_skills(db, skills=[skill]))[0]


@router.post(
    "/marketplace/{listing_id}/install",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_marketplace_skill(
    listing_id: int,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    listing = await _get_listing_or_404(db, listing_id=listing_id)
    if listing.status != SkillMarketplaceStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="listing_not_active"
        )

    name = await _next_unique_skill_name(db, user_id=user.id, base_name=listing.name)
    skill = Skill(
        user_id=user.id,
        name=name,
        slug=await _next_unique_skill_slug(db, user_id=user.id, base_name=name),
        description=listing.description,
        instructions=listing.instructions,
        enabled=True,
        installed_from_listing_id=listing.id,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return (await _serialize_skills(db, skills=[skill]))[0]


@router.post(
    "/marketplace/{listing_id}/approve", response_model=SkillMarketplaceListingResponse
)
async def approve_marketplace_listing(
    listing_id: int,
    payload: SkillMarketplaceReview,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    _require_admin(user.role)
    listing = await _get_listing_or_404(db, listing_id=listing_id)
    listing.status = SkillMarketplaceStatus.approved
    listing.review_notes = payload.review_notes.strip()
    listing.reviewed_by_user_id = user.id
    await db.commit()
    await db.refresh(listing)
    return _serialize_listing(listing)


@router.post(
    "/marketplace/{listing_id}/reject", response_model=SkillMarketplaceListingResponse
)
async def reject_marketplace_listing(
    listing_id: int,
    payload: SkillMarketplaceReview,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    _require_admin(user.role)
    listing = await _get_listing_or_404(db, listing_id=listing_id)
    listing.status = SkillMarketplaceStatus.rejected
    listing.review_notes = payload.review_notes.strip()
    listing.reviewed_by_user_id = user.id
    await db.commit()
    await db.refresh(listing)
    return _serialize_listing(listing)


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
        skill.slug = await _next_unique_skill_slug(
            db,
            user_id=user.id,
            base_name=payload.name,
            exclude_skill_id=skill.id,
        )

    if payload.description is not None:
        skill.description = payload.description.strip()

    if payload.instructions is not None:
        skill.instructions = payload.instructions.strip()

    if payload.enabled is not None:
        skill.enabled = payload.enabled

    if skill.installed_from_listing_id is None:
        listing = await _get_listing_for_owner_skill(db, owner_skill_id=skill.id)
        if listing is not None:
            await _sync_listing_from_skill(db, skill=skill, owner_user_id=user.id)

    await db.commit()
    await db.refresh(skill)
    return (await _serialize_skills(db, skills=[skill]))[0]


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
    return (await _serialize_skills(db, skills=[skill]))[0]


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: int, db: AsyncSessionDep, user: CheckUserSSODep):
    skill = await _get_user_skill(db, skill_id=skill_id, user_id=user.id)
    skill.archived = True
    listing = await _get_listing_for_owner_skill(db, owner_skill_id=skill.id)
    if listing is not None:
        listing.archived = True
    await db.commit()
