"""
Lead management: CRUD, filtering, pagination, detail views with conversations.
All queries are tenant-scoped via agency_id dependency.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_agency_id, get_current_user
from app.models.models import Agent, Conversation, Lead, LeadScore, Message
from app.schemas.schemas import (
    ConversationResponse, LeadCreate, LeadDetailResponse, LeadFilters,
    LeadResponse, LeadUpdate, MessageResponse, PaginatedResponse,
)
from app.services.analytics import emit_event
from app.services.scoring import assign_agent_round_robin

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=PaginatedResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str = Query(None),
    source: str = Query(None),
    score_min: int = Query(None, ge=0, le=100),
    score_max: int = Query(None, ge=0, le=100),
    agent_id: UUID = Query(None),
    campaign_id: UUID = Query(None),
    search: str = Query(None),
    sort: str = Query("-created_at"),
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """List leads with filters, search, and pagination."""

    query = select(Lead).where(Lead.agency_id == agency_id)
    count_query = select(func.count(Lead.id)).where(Lead.agency_id == agency_id)

    # Apply filters
    if status:
        query = query.where(Lead.status == status)
        count_query = count_query.where(Lead.status == status)
    if source:
        query = query.where(Lead.source == source)
        count_query = count_query.where(Lead.source == source)
    if score_min is not None:
        query = query.where(Lead.score >= score_min)
        count_query = count_query.where(Lead.score >= score_min)
    if score_max is not None:
        query = query.where(Lead.score <= score_max)
        count_query = count_query.where(Lead.score <= score_max)
    if agent_id:
        query = query.where(Lead.agent_id == agent_id)
        count_query = count_query.where(Lead.agent_id == agent_id)
    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
        count_query = count_query.where(Lead.campaign_id == campaign_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(Lead.name.ilike(pattern) | Lead.phone.ilike(pattern) | Lead.email.ilike(pattern))
        count_query = count_query.where(Lead.name.ilike(pattern) | Lead.phone.ilike(pattern) | Lead.email.ilike(pattern))

    # Sorting
    if sort == "-score":
        query = query.order_by(Lead.score.desc().nulls_last())
    elif sort == "score":
        query = query.order_by(Lead.score.asc().nulls_last())
    elif sort == "created_at":
        query = query.order_by(Lead.created_at.asc())
    else:
        query = query.order_by(Lead.created_at.desc())

    # Pagination
    total = (await db.execute(count_query)).scalar()
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    leads = result.scalars().all()

    return PaginatedResponse.build(
        data=[LeadResponse.model_validate(l) for l in leads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{lead_id}", response_model=LeadDetailResponse)
async def get_lead(
    lead_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Get full lead detail with conversations, scores, and agent info."""

    result = await db.execute(
        select(Lead)
        .where(Lead.id == lead_id, Lead.agency_id == agency_id)
        .options(
            selectinload(Lead.conversations),
            selectinload(Lead.scores),
            selectinload(Lead.agent),
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return LeadDetailResponse.model_validate(lead)


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(
    body: LeadCreate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a lead manually (from dashboard)."""

    lead = Lead(
        agency_id=agency_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        source=body.source,
        campaign_id=body.campaign_id,
        source_ref=body.source_ref,
    )
    db.add(lead)
    await db.flush()

    await emit_event(db, agency_id, "lead.created", "lead", lead_id=lead.id, source="dashboard")

    return LeadResponse.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: UUID,
    body: LeadUpdate,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Update lead fields (status, agent assignment, qualification data)."""

    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.agency_id == agency_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = body.model_dump(exclude_unset=True)
    old_status = lead.status

    for field, value in update_data.items():
        setattr(lead, field, value)

    if body.status and body.status != old_status:
        await emit_event(
            db, agency_id, "lead.status_changed", "lead",
            lead_id=lead.id,
            event_data={"old_status": old_status, "new_status": body.status},
        )

    await db.flush()
    return LeadResponse.model_validate(lead)


@router.get("/{lead_id}/conversations", response_model=list[ConversationResponse])
async def get_lead_conversations(
    lead_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for a lead."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.lead_id == lead_id, Conversation.agency_id == agency_id)
        .order_by(Conversation.started_at.desc())
    )
    return [ConversationResponse.model_validate(c) for c in result.scalars().all()]


@router.get("/{lead_id}/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    lead_id: UUID,
    conversation_id: UUID,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a conversation."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.lead_id == lead_id)
        .order_by(Message.created_at.asc())
    )
    return [MessageResponse.model_validate(m) for m in result.scalars().all()]


@router.get("/stats/overview")
async def get_lead_stats(
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """Quick stats: count by status."""
    result = await db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.agency_id == agency_id)
        .group_by(Lead.status)
    )
    return {row[0]: row[1] for row in result.all()}
