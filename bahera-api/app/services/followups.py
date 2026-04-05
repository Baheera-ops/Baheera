"""
Follow-up scheduler: creates and sends automated follow-up messages.
Uses APScheduler for background job processing.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FollowUp, FollowUpStatus, Lead, LeadSource, LeadStatus
from app.services.whatsapp import send_template_message

logger = logging.getLogger("bahera.followups")

# Template mapping: day_number → (template_key, description)
FOLLOW_UP_TEMPLATES = {
    1: ("follow_up_day1", "Thanks for your interest — advisor will reach out"),
    3: ("follow_up_day3", "Checking in — would you like to schedule a viewing?"),
    7: ("follow_up_day7", "New options matching your criteria"),
}


async def schedule_follow_ups(
    db: AsyncSession,
    lead_id: UUID,
    agency_id: UUID,
    channel: LeadSource = LeadSource.WHATSAPP,
    days: list[int] | None = None,
):
    """
    Create follow-up schedule entries for a newly qualified lead.
    Default: Day 1, 3, 7 follow-ups.
    """
    days = days or [1, 3, 7]
    now = datetime.utcnow()

    for day in days:
        template_key = FOLLOW_UP_TEMPLATES.get(day, (f"follow_up_day{day}", ""))[0]
        follow_up = FollowUp(
            lead_id=lead_id,
            agency_id=agency_id,
            day_number=day,
            channel=channel,
            template_key=template_key,
            status=FollowUpStatus.PENDING,
            scheduled_at=now + timedelta(days=day),
        )
        db.add(follow_up)

    await db.flush()
    logger.info(f"Scheduled {len(days)} follow-ups for lead {lead_id}")


async def process_pending_follow_ups(db: AsyncSession):
    """
    Process all pending follow-ups that are due.
    Called by APScheduler every 5 minutes.
    """
    now = datetime.utcnow()

    # Fetch due follow-ups
    result = await db.execute(
        select(FollowUp)
        .where(
            FollowUp.status == FollowUpStatus.PENDING,
            FollowUp.scheduled_at <= now,
        )
        .limit(50)  # Process in batches
    )
    follow_ups = result.scalars().all()

    if not follow_ups:
        return

    logger.info(f"Processing {len(follow_ups)} pending follow-ups")

    for fu in follow_ups:
        # Load the lead
        lead_result = await db.execute(select(Lead).where(Lead.id == fu.lead_id))
        lead = lead_result.scalar_one_or_none()

        if not lead:
            fu.status = FollowUpStatus.CANCELLED
            continue

        # Skip if lead is already converted or lost
        if lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST, LeadStatus.ARCHIVED):
            fu.status = FollowUpStatus.SKIPPED
            continue

        # Send via WhatsApp
        try:
            result = await send_template_message(
                to_phone=lead.phone,
                template_name=fu.template_key,
                parameters=[lead.name or "there"],
            )

            if result.get("success"):
                fu.status = FollowUpStatus.SENT
                fu.sent_at = datetime.utcnow()
                logger.info(f"Follow-up sent to {lead.phone} (day {fu.day_number})")
            else:
                fu.status = FollowUpStatus.FAILED
                logger.warning(f"Follow-up failed for {lead.phone}: {result.get('error')}")

        except Exception as e:
            fu.status = FollowUpStatus.FAILED
            logger.exception(f"Follow-up send error: {e}")

    await db.flush()
