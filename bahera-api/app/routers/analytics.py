"""Analytics router: dashboard KPIs, score distribution, campaign comparisons."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agency_id
from app.services.analytics import get_campaign_analytics, get_overview_stats, get_score_distribution

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
async def overview(
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard KPI cards: today/week/month leads, avg score, conversions."""
    return await get_overview_stats(db, agency_id)


@router.get("/score-distribution")
async def score_distribution(
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Lead score histogram: hot/warm/nurture/cold/unscored counts."""
    return await get_score_distribution(db, agency_id)


@router.get("/campaigns")
async def campaigns_comparison(
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Performance metrics across all campaigns."""
    return await get_campaign_analytics(db, agency_id)
