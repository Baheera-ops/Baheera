"""
Analytics service: event emission and aggregation queries.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AnalyticsEvent, Campaign, Lead


async def emit_event(
    db: AsyncSession,
    agency_id: UUID,
    event_type: str,
    event_category: str,
    lead_id: Optional[UUID] = None,
    campaign_id: Optional[UUID] = None,
    agent_id: Optional[UUID] = None,
    event_data: Optional[dict] = None,
    source: Optional[str] = None,
):
    """Fire-and-forget analytics event."""
    event = AnalyticsEvent(
        agency_id=agency_id,
        event_type=event_type,
        event_category=event_category,
        lead_id=lead_id,
        campaign_id=campaign_id,
        agent_id=agent_id,
        event_data=event_data or {},
        source=source,
    )
    db.add(event)
    await db.flush()
    return event


async def get_overview_stats(db: AsyncSession, agency_id: UUID) -> dict:
    """Dashboard KPI aggregations."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    result = await db.execute(
        select(
            func.count(Lead.id).filter(Lead.created_at >= today_start).label("today"),
            func.count(Lead.id).filter(Lead.created_at >= week_start).label("week"),
            func.count(Lead.id).filter(Lead.created_at >= month_start).label("month"),
            func.round(func.avg(Lead.score).filter(Lead.score.isnot(None)), 1).label("avg_score"),
            func.count(Lead.id).filter(Lead.score >= 80).label("hot"),
            func.count(Lead.id).filter(Lead.status == "converted").label("conversions"),
            func.count(Lead.id).filter(Lead.score.isnot(None)).label("scored_total"),
        ).where(Lead.agency_id == agency_id)
    )
    row = result.one()

    scored = row.scored_total or 0
    return {
        "leads_today": row.today,
        "leads_this_week": row.week,
        "leads_this_month": row.month,
        "avg_score": float(row.avg_score) if row.avg_score else None,
        "hot_leads": row.hot,
        "total_conversions": row.conversions,
        "conversion_rate": round((row.conversions / scored * 100), 2) if scored > 0 else None,
    }


async def get_score_distribution(db: AsyncSession, agency_id: UUID) -> dict:
    """Lead score distribution for dashboard chart."""
    result = await db.execute(
        select(
            func.count(Lead.id).filter(Lead.score >= 80).label("hot"),
            func.count(Lead.id).filter(Lead.score.between(60, 79)).label("warm"),
            func.count(Lead.id).filter(Lead.score.between(30, 59)).label("nurture"),
            func.count(Lead.id).filter(Lead.score < 30, Lead.score.isnot(None)).label("cold"),
            func.count(Lead.id).filter(Lead.score.is_(None)).label("unscored"),
        ).where(Lead.agency_id == agency_id)
    )
    row = result.one()
    return {"hot": row.hot, "warm": row.warm, "nurture": row.nurture, "cold": row.cold, "unscored": row.unscored}


async def get_campaign_analytics(db: AsyncSession, agency_id: UUID) -> list[dict]:
    """Per-campaign performance metrics."""
    result = await db.execute(
        select(
            Campaign.id,
            Campaign.name,
            Campaign.total_leads,
            Campaign.qualified_leads,
            Campaign.converted_leads,
            Campaign.avg_lead_score,
            Campaign.cost_per_lead,
            Campaign.budget_spent,
        )
        .where(Campaign.agency_id == agency_id)
        .order_by(Campaign.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "campaign_id": r.id,
            "campaign_name": r.name,
            "total_leads": r.total_leads,
            "qualified_leads": r.qualified_leads,
            "converted_leads": r.converted_leads,
            "avg_score": float(r.avg_lead_score) if r.avg_lead_score else None,
            "cost_per_lead": float(r.cost_per_lead) if r.cost_per_lead else None,
            "cost_per_qualified": (
                round(float(r.budget_spent) / r.qualified_leads, 2)
                if r.qualified_leads and r.budget_spent else None
            ),
        }
        for r in rows
    ]
