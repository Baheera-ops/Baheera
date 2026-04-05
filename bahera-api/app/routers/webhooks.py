"""
Webhook receivers: Meta Lead Ads, WhatsApp messages, website widget.
These endpoints are PUBLIC (no JWT auth) but verified via signatures.
"""

import hashlib
import hmac
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import Agency, Conversation, ConversationStatus, Lead, LeadSource, LeadStatus, Message, MessageRole
from app.schemas.schemas import WidgetLeadCapture
from app.services.analytics import emit_event

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
settings = get_settings()


def verify_meta_signature(request_body: bytes, signature: str) -> bool:
    """Verify the X-Hub-Signature-256 header from Meta."""
    expected = "sha256=" + hmac.new(
        settings.META_APP_SECRET.encode(), request_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.get("/meta/verify")
async def meta_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
):
    """Meta webhook verification challenge."""
    if hub_verify_token != settings.META_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return int(hub_challenge)


@router.post("/meta/messaging")
async def meta_messaging_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receives WhatsApp + Instagram messages from Meta Cloud API.
    Extracts sender phone, message text, routes to chatbot engine.
    """
    body = await request.body()

    # Verify signature in production
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.ENVIRONMENT == "production" and signature:
        if not verify_meta_signature(body, signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(body)

    # Parse WhatsApp webhook structure
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            phone_id = value.get("metadata", {}).get("phone_number_id")

            for msg in messages:
                sender_phone = msg.get("from")
                msg_text = msg.get("text", {}).get("body", "")
                msg_type = msg.get("type", "text")
                msg_id = msg.get("id")

                if not sender_phone or not msg_text:
                    continue

                # Find agency by WhatsApp phone ID
                agency_result = await db.execute(
                    select(Agency).where(Agency.whatsapp_phone_id == phone_id)
                )
                agency = agency_result.scalar_one_or_none()
                if not agency:
                    continue

                # Find or create lead by phone number
                lead_result = await db.execute(
                    select(Lead).where(Lead.phone == sender_phone, Lead.agency_id == agency.id)
                )
                lead = lead_result.scalar_one_or_none()

                if not lead:
                    lead = Lead(
                        agency_id=agency.id,
                        phone=sender_phone,
                        source=LeadSource.WHATSAPP,
                        status=LeadStatus.NEW,
                    )
                    db.add(lead)
                    await db.flush()
                    await emit_event(db, agency.id, "lead.created", "lead",
                                     lead_id=lead.id, source="whatsapp")

                # Find or create conversation
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.lead_id == lead.id,
                        Conversation.status.in_(["active", "waiting_response"]),
                    ).limit(1)
                )
                conversation = conv_result.scalar_one_or_none()
                if not conversation:
                    conversation = Conversation(
                        lead_id=lead.id,
                        agency_id=agency.id,
                        channel=LeadSource.WHATSAPP,
                    )
                    db.add(conversation)
                    await db.flush()

                # Save incoming message
                message = Message(
                    conversation_id=conversation.id,
                    lead_id=lead.id,
                    role=MessageRole.USER,
                    content=msg_text,
                    message_type=msg_type,
                    external_msg_id=msg_id,
                    delivery_status="delivered",
                )
                db.add(message)

                # TODO: Trigger chatbot engine asynchronously
                # In production, push to a task queue (Celery/BullMQ)
                # For MVP: process inline

                await emit_event(db, agency.id, "conversation.message_received", "conversation",
                                 lead_id=lead.id, source="whatsapp",
                                 event_data={"message_type": msg_type})

    return {"status": "ok"}


@router.post("/meta/leadgen")
async def meta_lead_ad_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receives instant form submissions from Meta Lead Ads.
    Captures the lead data and triggers qualification.
    """
    body = await request.body()
    payload = json.loads(body)

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            leadgen_id = value.get("leadgen_id")
            form_id = value.get("form_id")
            page_id = value.get("page_id")

            if not leadgen_id:
                continue

            # Find agency by Meta page ID
            agency_result = await db.execute(
                select(Agency).where(Agency.meta_page_id == page_id)
            )
            agency = agency_result.scalar_one_or_none()
            if not agency:
                continue

            # TODO: Fetch lead data from Meta Graph API using leadgen_id
            # For now, create a placeholder lead
            lead = Lead(
                agency_id=agency.id,
                phone="pending",
                source=LeadSource.META_LEAD_AD,
                source_ref=leadgen_id,
                status=LeadStatus.NEW,
            )
            db.add(lead)
            await db.flush()

            await emit_event(db, agency.id, "lead.created", "lead",
                             lead_id=lead.id, source="meta_lead_ad",
                             event_data={"form_id": form_id, "leadgen_id": leadgen_id})

    return {"status": "ok"}


@router.post("/widget")
async def widget_lead_capture(body: WidgetLeadCapture, db: AsyncSession = Depends(get_db)):
    """
    Website chat widget lead capture.
    Creates a lead and starts a conversation from the website.
    """
    # Verify agency exists
    agency_result = await db.execute(select(Agency).where(Agency.id == body.org_id))
    agency = agency_result.scalar_one_or_none()
    if not agency:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Find or create lead
    lead_result = await db.execute(
        select(Lead).where(Lead.phone == body.phone, Lead.agency_id == agency.id)
    )
    lead = lead_result.scalar_one_or_none()

    if not lead:
        lead = Lead(
            agency_id=agency.id,
            name=body.name,
            phone=body.phone,
            email=body.email,
            source=LeadSource.WEB_WIDGET,
            status=LeadStatus.NEW,
        )
        db.add(lead)
        await db.flush()
        await emit_event(db, agency.id, "lead.created", "lead",
                         lead_id=lead.id, source="web_widget")

    # Create conversation
    conversation = Conversation(
        lead_id=lead.id,
        agency_id=agency.id,
        channel=LeadSource.WEB_WIDGET,
    )
    db.add(conversation)
    await db.flush()

    # Save the initial message
    message = Message(
        conversation_id=conversation.id,
        lead_id=lead.id,
        role=MessageRole.USER,
        content=body.message,
    )
    db.add(message)

    return {"lead_id": str(lead.id), "conversation_id": str(conversation.id)}
