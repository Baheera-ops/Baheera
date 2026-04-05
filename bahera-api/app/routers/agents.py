"""Agents router: CRUD, assignment management, performance stats."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_agency_id, require_admin
from app.models.models import Agent, Lead
from app.schemas.schemas import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.agency_id == agency_id).order_by(Agent.name)
    )
    return [AgentResponse.model_validate(a) for a in result.scalars().all()]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    agent = Agent(agency_id=agency_id, **body.model_dump())
    db.add(agent)
    await db.flush()
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.agency_id == agency_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    await db.flush()
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/leads", response_model=list)
async def agent_leads(
    agent_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Get all active leads assigned to an agent."""
    from app.schemas.schemas import LeadResponse
    result = await db.execute(
        select(Lead)
        .where(Lead.agent_id == agent_id, Lead.agency_id == agency_id)
        .where(Lead.status.notin_(["archived", "lost"]))
        .order_by(Lead.score.desc().nulls_last())
    )
    return [LeadResponse.model_validate(l) for l in result.scalars().all()]


@router.get("/{agent_id}/stats")
async def agent_stats(
    agent_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Performance stats for a single agent."""
    result = await db.execute(
        select(
            func.count(Lead.id).label("total"),
            func.count(Lead.id).filter(Lead.status == "converted").label("converted"),
            func.count(Lead.id).filter(Lead.status.notin_(["archived", "lost", "converted"])).label("active"),
            func.round(func.avg(Lead.score).filter(Lead.score.isnot(None)), 1).label("avg_score"),
        ).where(Lead.agent_id == agent_id, Lead.agency_id == agency_id)
    )
    row = result.one()
    return {
        "total_leads": row.total,
        "converted": row.converted,
        "active": row.active,
        "avg_lead_score": float(row.avg_score) if row.avg_score else None,
        "conversion_rate": round(row.converted / row.total * 100, 1) if row.total > 0 else 0,
    }
