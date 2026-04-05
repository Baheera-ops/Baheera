"""
Campaigns router: CRUD + analytics per campaign.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agency_id, require_admin
from app.models.models import Campaign, Lead
from app.schemas.schemas import CampaignCreate, CampaignResponse, CampaignUpdate, PaginatedResponse

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.get("", response_model=PaginatedResponse)
async def list_campaigns(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    is_active: bool = Query(None),
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign).where(Campaign.agency_id == agency_id)
    count_q = select(func.count(Campaign.id)).where(Campaign.agency_id == agency_id)
    if is_active is not None:
        query = query.where(Campaign.is_active == is_active)
        count_q = count_q.where(Campaign.is_active == is_active)
    query = query.order_by(Campaign.created_at.desc())

    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))

    return PaginatedResponse.build(
        data=[CampaignResponse.model_validate(c) for c in result.scalars().all()],
        total=total, page=page, per_page=per_page,
    )


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    campaign = Campaign(agency_id=agency_id, **body.model_dump())
    db.add(campaign)
    await db.flush()
    return CampaignResponse.model_validate(campaign)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.agency_id == agency_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(campaign, field, value)
    await db.flush()
    return CampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}/analytics")
async def campaign_analytics(
    campaign_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Detailed analytics for a specific campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.agency_id == agency_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Score distribution for this campaign
    score_dist = await db.execute(
        select(
            func.count(Lead.id).filter(Lead.score >= 80).label("hot"),
            func.count(Lead.id).filter(Lead.score.between(60, 79)).label("warm"),
            func.count(Lead.id).filter(Lead.score.between(30, 59)).label("nurture"),
            func.count(Lead.id).filter(Lead.score < 30, Lead.score.isnot(None)).label("cold"),
        ).where(Lead.campaign_id == campaign_id)
    )
    dist = score_dist.one()

    return {
        "campaign": CampaignResponse.model_validate(campaign),
        "score_distribution": {"hot": dist.hot, "warm": dist.warm, "nurture": dist.nurture, "cold": dist.cold},
    }
