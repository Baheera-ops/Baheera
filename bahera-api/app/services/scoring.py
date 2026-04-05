"""
Core business logic: lead scoring and round-robin agent assignment.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Agent, Lead, LeadScore


# ═══════════════════════════════════════════════════════════════════════
# LEAD SCORING
# ═══════════════════════════════════════════════════════════════════════

def calculate_lead_score(qualification_data: dict, messages: list[dict]) -> dict:
    """
    Rule-based lead scoring. Returns a dict matching the LeadScore columns.
    
    Component weights:
      budget_score:     0-25  (highest signal — specific budget = serious buyer)
      timeline_score:   0-20  (sooner = more motivated)
      payment_score:    0-20  (cash > mortgage > exploring)
      location_score:   0-15  (named community > general city)
      engagement_score: 0-10  (response length + asking questions)
      purpose_score:    0-10  (clear intent = higher score)
    """

    # Budget (0-25)
    budget_max = qualification_data.get("budget_max")
    budget_min = qualification_data.get("budget_min")
    if budget_max and budget_min:
        budget_score = 25
    elif budget_max:
        budget_score = 20
    elif budget_min:
        budget_score = 15
    else:
        budget_score = 0

    # Timeline (0-20)
    timeline = qualification_data.get("timeline_months")
    if timeline is None:
        timeline_score = 0
    elif timeline <= 1:
        timeline_score = 20
    elif timeline <= 3:
        timeline_score = 18
    elif timeline <= 6:
        timeline_score = 14
    elif timeline <= 12:
        timeline_score = 8
    else:
        timeline_score = 3

    # Payment (0-20)
    payment_map = {"cash": 20, "mortgage": 14, "installments": 12, "exploring": 6}
    payment = qualification_data.get("payment_method", "").lower()
    payment_score = payment_map.get(payment, 0)

    # Location (0-15)
    location = qualification_data.get("preferred_location", "")
    if not location:
        location_score = 0
    elif len(location.split()) >= 2:
        location_score = 15
    else:
        location_score = 8

    # Engagement (0-10)
    user_msgs = [m for m in messages if m.get("role") == "user"]
    if user_msgs:
        avg_len = sum(len(m.get("content", "")) for m in user_msgs) / len(user_msgs)
        engagement_score = 8 if avg_len > 80 else 6 if avg_len > 40 else 4 if avg_len > 15 else 2
        questions = sum(1 for m in user_msgs if "?" in m.get("content", ""))
        if questions >= 2:
            engagement_score = min(10, engagement_score + 2)
    else:
        engagement_score = 0

    # Purpose (0-10)
    purpose_map = {"investment": 10, "both": 9, "end_use": 8}
    purpose = qualification_data.get("purpose", "").lower()
    purpose_score = purpose_map.get(purpose, 3)

    rule_total = budget_score + timeline_score + payment_score + location_score + engagement_score + purpose_score

    return {
        "total_score": min(100, max(0, rule_total)),
        "budget_score": budget_score,
        "timeline_score": timeline_score,
        "payment_score": payment_score,
        "location_score": location_score,
        "engagement_score": engagement_score,
        "purpose_score": purpose_score,
        "ai_adjustment": 0,
        "rule_score_raw": rule_total,
    }


async def save_lead_score(
    db: AsyncSession,
    lead_id: UUID,
    agency_id: UUID,
    score_data: dict,
) -> LeadScore:
    """Persist a new score version and update the lead's denormalized score."""

    # Mark all previous scores as not current
    await db.execute(
        update(LeadScore)
        .where(LeadScore.lead_id == lead_id, LeadScore.is_current == True)
        .values(is_current=False)
    )

    # Create new score
    lead_score = LeadScore(
        lead_id=lead_id,
        agency_id=agency_id,
        is_current=True,
        **score_data,
    )
    db.add(lead_score)

    # Update denormalized score on lead
    await db.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(
            score=score_data["total_score"],
            status="qualified",
            qualified_at=datetime.utcnow(),
            qualification_complete=True,
        )
    )

    await db.flush()
    return lead_score


# ═══════════════════════════════════════════════════════════════════════
# AGENT ASSIGNMENT (Weighted Round-Robin)
# ═══════════════════════════════════════════════════════════════════════

async def assign_agent_round_robin(
    db: AsyncSession,
    agency_id: UUID,
    specialization: Optional[str] = None,
) -> Optional[Agent]:
    """
    Pick the next available agent using weighted round-robin.
    
    Algorithm:
    1. Filter eligible agents (active, available, under capacity)
    2. Sort by (last_assigned_at NULLS FIRST) → never-assigned agents go first
    3. Weight-adjust: divide total_leads_assigned by assignment_weight
    4. Pick the top result and update their counters
    
    Uses FOR UPDATE SKIP LOCKED to prevent race conditions in concurrent webhook processing.
    """

    query = (
        select(Agent)
        .where(
            Agent.agency_id == agency_id,
            Agent.is_active == True,
            Agent.is_available == True,
            Agent.active_lead_count < Agent.max_active_leads,
        )
        .order_by(
            Agent.last_assigned_at.asc().nulls_first(),
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    if specialization:
        query = query.where(Agent.specialization == specialization)

    result = await db.execute(query)
    agent = result.scalar_one_or_none()

    if not agent:
        # Retry without specialization filter
        if specialization:
            return await assign_agent_round_robin(db, agency_id, specialization=None)
        return None

    # Update agent counters
    agent.last_assigned_at = datetime.utcnow()
    agent.total_leads_assigned += 1
    agent.active_lead_count += 1
    await db.flush()

    return agent
