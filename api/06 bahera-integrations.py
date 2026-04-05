"""
BAHERA Messaging Integrations
==============================
Complete integration layer for Meta Lead Ads, WhatsApp Business,
and Instagram Messaging. Handles inbound webhooks, outbound messaging,
and automated follow-ups across all three channels.

Architecture:
  Inbound:  webhook → signature verify → channel parser → normalized event → lead resolver → chatbot
  Outbound: chatbot response → channel sender → delivery tracking

All three channels share a single Meta App and webhook URL.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import (
    Agency, AnalyticsEvent, Campaign, Conversation, ConversationStatus,
    FollowUp, FollowUpStatus, Lead, LeadSource, LeadStatus, Message,
    MessageRole,
)

logger = logging.getLogger("bahera.integrations")
settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

META_GRAPH_URL = "https://graph.facebook.com/v19.0"


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: NORMALIZED EVENT MODEL
# All three channels produce this structure after parsing.
# ═══════════════════════════════════════════════════════════════════════

class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    LEAD_AD = "lead_ad"

class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    LOCATION = "location"
    BUTTON_REPLY = "button_reply"
    LIST_REPLY = "list_reply"
    LEADGEN = "leadgen"         # Not a real message — form submission

@dataclass
class InboundEvent:
    """Normalized inbound event — produced by every channel parser."""
    channel: ChannelType
    agency_phone_id: str        # WhatsApp phone_number_id or IG page ID
    sender_id: str              # Phone number (WA) or IGSID (IG) or leadgen_id
    sender_phone: Optional[str] = None  # Actual phone, if available
    sender_name: Optional[str] = None
    message_text: Optional[str] = None
    message_type: MessageType = MessageType.TEXT
    external_msg_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    # Lead Ad specific
    leadgen_id: Optional[str] = None
    form_id: Optional[str] = None
    ad_id: Optional[str] = None
    page_id: Optional[str] = None
    # Metadata
    raw_payload: dict = field(default_factory=dict)

@dataclass
class OutboundMessage:
    """Normalized outbound message — sent to any channel."""
    channel: ChannelType
    recipient_id: str           # Phone (WA) or IGSID (IG)
    text: str
    message_type: str = "text"
    # WhatsApp-specific
    template_name: Optional[str] = None
    template_params: Optional[list[str]] = None
    buttons: Optional[list[dict]] = None
    # Tracking
    agency_phone_id: Optional[str] = None
    access_token: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: CHANNEL PARSERS
# Each parser takes the raw Meta webhook payload and produces
# a list of InboundEvent objects.
# ═══════════════════════════════════════════════════════════════════════

def parse_whatsapp_webhook(payload: dict) -> list[InboundEvent]:
    """
    Parse WhatsApp Cloud API webhook payload.
    
    Payload structure:
    {
      "entry": [{
        "changes": [{
          "value": {
            "messaging_product": "whatsapp",
            "metadata": { "phone_number_id": "PHONE_ID", "display_phone_number": "..." },
            "contacts": [{ "profile": { "name": "Ahmed" }, "wa_id": "971501234567" }],
            "messages": [{
              "from": "971501234567",
              "id": "wamid.xxx",
              "timestamp": "1712345678",
              "type": "text",
              "text": { "body": "Hi, I'm interested" }
            }],
            "statuses": [{...}]  # Delivery receipts — handled separately
          }
        }]
      }]
    }
    """
    events = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            if value.get("messaging_product") != "whatsapp":
                continue

            phone_id = value.get("metadata", {}).get("phone_number_id", "")
            contacts = {c["wa_id"]: c.get("profile", {}).get("name") for c in value.get("contacts", [])}

            # Handle incoming messages
            for msg in value.get("messages", []):
                sender = msg.get("from", "")
                msg_type = msg.get("type", "text")

                # Extract text based on message type
                text = None
                normalized_type = MessageType.TEXT

                if msg_type == "text":
                    text = msg.get("text", {}).get("body")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    reply_type = interactive.get("type")
                    if reply_type == "button_reply":
                        text = interactive.get("button_reply", {}).get("title")
                        normalized_type = MessageType.BUTTON_REPLY
                    elif reply_type == "list_reply":
                        text = interactive.get("list_reply", {}).get("title")
                        normalized_type = MessageType.LIST_REPLY
                elif msg_type == "image":
                    text = msg.get("image", {}).get("caption", "[Image]")
                    normalized_type = MessageType.IMAGE
                elif msg_type == "document":
                    text = msg.get("document", {}).get("caption", "[Document]")
                    normalized_type = MessageType.DOCUMENT
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    text = f"Location: {loc.get('latitude')}, {loc.get('longitude')}"
                    normalized_type = MessageType.LOCATION

                if text is None:
                    text = f"[{msg_type} message]"

                ts = None
                if msg.get("timestamp"):
                    ts = datetime.fromtimestamp(int(msg["timestamp"]))

                events.append(InboundEvent(
                    channel=ChannelType.WHATSAPP,
                    agency_phone_id=phone_id,
                    sender_id=sender,
                    sender_phone=sender,
                    sender_name=contacts.get(sender),
                    message_text=text,
                    message_type=normalized_type,
                    external_msg_id=msg.get("id"),
                    timestamp=ts,
                    raw_payload=msg,
                ))

            # Handle delivery status updates
            for status in value.get("statuses", []):
                await_delivery_update(status)

    return events


def parse_instagram_webhook(payload: dict) -> list[InboundEvent]:
    """
    Parse Instagram Messaging API webhook payload.
    
    Payload structure (Instagram messaging through Meta platform):
    {
      "entry": [{
        "id": "PAGE_ID",
        "messaging": [{
          "sender": { "id": "IGSID_12345" },
          "recipient": { "id": "PAGE_IGSID" },
          "timestamp": 1712345678000,
          "message": {
            "mid": "igmid.xxx",
            "text": "Hi, I saw your property ad"
          }
        }]
      }]
    }
    
    Note: Instagram uses a different webhook structure than WhatsApp.
    The "messaging" field is at the entry level, not nested in changes.
    """
    events = []

    for entry in payload.get("entry", []):
        page_id = entry.get("id", "")

        for msg_event in entry.get("messaging", []):
            sender = msg_event.get("sender", {}).get("id", "")
            message = msg_event.get("message", {})

            if not message or not sender:
                continue

            text = message.get("text", "")
            msg_id = message.get("mid", "")

            # Instagram image messages
            attachments = message.get("attachments", [])
            msg_type = MessageType.TEXT
            if attachments:
                att_type = attachments[0].get("type", "")
                if att_type == "image":
                    msg_type = MessageType.IMAGE
                    text = text or "[Image]"

            ts = None
            raw_ts = msg_event.get("timestamp")
            if raw_ts:
                ts = datetime.fromtimestamp(raw_ts / 1000)  # IG uses milliseconds

            events.append(InboundEvent(
                channel=ChannelType.INSTAGRAM,
                agency_phone_id=page_id,
                sender_id=sender,
                sender_phone=None,  # Instagram doesn't provide phone
                sender_name=None,   # Must be fetched via Graph API if needed
                message_text=text,
                message_type=msg_type,
                external_msg_id=msg_id,
                timestamp=ts,
                raw_payload=msg_event,
            ))

    return events


def parse_leadgen_webhook(payload: dict) -> list[InboundEvent]:
    """
    Parse Meta Lead Ads (leadgen) webhook payload.
    
    Payload structure:
    {
      "entry": [{
        "changes": [{
          "field": "leadgen",
          "value": {
            "leadgen_id": "LEAD_ID",
            "form_id": "FORM_ID",
            "page_id": "PAGE_ID",
            "ad_id": "AD_ID",
            "created_time": 1712345678
          }
        }]
      }]
    }
    
    The leadgen webhook only delivers IDs — actual form data must be
    fetched via a second Graph API call (see fetch_leadgen_data).
    """
    events = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue

            value = change.get("value", {})
            leadgen_id = value.get("leadgen_id")
            if not leadgen_id:
                continue

            ts = None
            if value.get("created_time"):
                ts = datetime.fromtimestamp(int(value["created_time"]))

            events.append(InboundEvent(
                channel=ChannelType.LEAD_AD,
                agency_phone_id=value.get("page_id", ""),
                sender_id=leadgen_id,
                leadgen_id=leadgen_id,
                form_id=value.get("form_id"),
                ad_id=value.get("ad_id"),
                page_id=value.get("page_id"),
                message_type=MessageType.LEADGEN,
                timestamp=ts,
                raw_payload=value,
            ))

    return events


def detect_channel(payload: dict) -> str:
    """
    Detect which channel sent the webhook based on payload structure.
    All three channels come through the same Meta App webhook URL.
    """
    for entry in payload.get("entry", []):
        # Instagram: has "messaging" at entry level
        if "messaging" in entry:
            return "instagram"

        for change in entry.get("changes", []):
            # Lead Ads: field is "leadgen"
            if change.get("field") == "leadgen":
                return "leadgen"

            # WhatsApp: has messaging_product = "whatsapp"
            value = change.get("value", {})
            if value.get("messaging_product") == "whatsapp":
                return "whatsapp"

    return "unknown"


def await_delivery_update(status: dict):
    """
    Process WhatsApp delivery status updates.
    Updates: sent → delivered → read
    """
    # In production, update the message row's delivery_status
    # For now, just log it
    msg_id = status.get("id")
    new_status = status.get("status")  # sent, delivered, read, failed
    logger.debug(f"Delivery update: {msg_id} → {new_status}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: META GRAPH API CLIENT
# Fetches lead form data, sends messages, manages tokens.
# ═══════════════════════════════════════════════════════════════════════

class MetaGraphClient:
    """Client for Meta's Graph API — used by all three channels."""

    def __init__(self):
        self.base_url = META_GRAPH_URL
        self.http = httpx.AsyncClient(timeout=15.0)

    async def fetch_leadgen_data(
        self, leadgen_id: str, page_access_token: str
    ) -> dict:
        """
        Fetch the actual form submission data for a Lead Ad.
        
        This is the critical second step: the webhook only delivers an ID,
        and we must call the Graph API to get the form fields.
        
        Returns:
        {
            "name": "Ahmed Al-Rashid",
            "phone": "+971501234567",
            "email": "ahmed@email.com",
            "fields": { "budget": "1-2M AED", "property_type": "Apartment" },
            "created_time": "2026-04-05T12:00:00+0000",
            "ad_id": "123",
            "form_id": "456"
        }
        """
        resp = await self.http.get(
            f"{self.base_url}/{leadgen_id}",
            params={
                "access_token": page_access_token,
                "fields": "field_data,created_time,ad_id,form_id,campaign_id,"
                          "ad_name,campaign_name,platform",
            },
        )

        if resp.status_code != 200:
            logger.error(f"Graph API leadgen fetch failed: {resp.status_code} {resp.text}")
            raise HTTPException(status_code=502, detail="Failed to fetch lead data from Meta")

        data = resp.json()

        # Parse field_data into a clean dict
        fields = {}
        name = None
        phone = None
        email = None

        for fd in data.get("field_data", []):
            field_name = fd.get("name", "").lower()
            values = fd.get("values", [])
            value = values[0] if values else None

            if field_name in ("full_name", "name"):
                name = value
            elif field_name in ("phone_number", "phone"):
                phone = value
            elif field_name == "email":
                email = value
            else:
                fields[field_name] = value

        return {
            "name": name,
            "phone": phone,
            "email": email,
            "fields": fields,
            "created_time": data.get("created_time"),
            "ad_id": data.get("ad_id"),
            "ad_name": data.get("ad_name"),
            "form_id": data.get("form_id"),
            "campaign_id": data.get("campaign_id"),
            "campaign_name": data.get("campaign_name"),
            "platform": data.get("platform"),
        }

    async def send_whatsapp_text(
        self, phone_id: str, access_token: str,
        to: str, text: str,
    ) -> dict:
        """Send a plain text message via WhatsApp Cloud API."""
        resp = await self.http.post(
            f"{self.base_url}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        result = resp.json()
        msg_id = None
        if resp.status_code == 200:
            msg_id = result.get("messages", [{}])[0].get("id")
        else:
            logger.error(f"WhatsApp send failed: {resp.status_code} {result}")
        return {"success": resp.status_code == 200, "message_id": msg_id, "raw": result}

    async def send_whatsapp_template(
        self, phone_id: str, access_token: str,
        to: str, template_name: str,
        language: str = "en_US",
        params: list[str] | None = None,
    ) -> dict:
        """Send a pre-approved WhatsApp template message."""
        components = []
        if params:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            })

        resp = await self.http.post(
            f"{self.base_url}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": components,
                },
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        result = resp.json()
        msg_id = None
        if resp.status_code == 200:
            msg_id = result.get("messages", [{}])[0].get("id")
        return {"success": resp.status_code == 200, "message_id": msg_id}

    async def send_whatsapp_interactive(
        self, phone_id: str, access_token: str,
        to: str, body_text: str,
        buttons: list[dict] | None = None,
        list_sections: list[dict] | None = None,
        header_text: str | None = None,
    ) -> dict:
        """
        Send an interactive message — buttons or list picker.
        
        Buttons (max 3): [{"id": "btn_1", "title": "View details"}]
        List sections: [{"title": "Properties", "rows": [{"id": "p1", "title": "Marina Heights", "description": "2BR from 1.4M"}]}]
        """
        if buttons:
            interactive = {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                        for b in buttons[:3]
                    ],
                },
            }
        elif list_sections:
            interactive = {
                "type": "list",
                "body": {"text": body_text},
                "action": {
                    "button": "View options",
                    "sections": list_sections,
                },
            }
        else:
            return await self.send_whatsapp_text(phone_id, access_token, to, body_text)

        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}

        resp = await self.http.post(
            f"{self.base_url}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": interactive,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        result = resp.json()
        msg_id = None
        if resp.status_code == 200:
            msg_id = result.get("messages", [{}])[0].get("id")
        return {"success": resp.status_code == 200, "message_id": msg_id}

    async def send_instagram_text(
        self, page_id: str, access_token: str,
        recipient_id: str, text: str,
    ) -> dict:
        """Send a text message via Instagram Messaging API."""
        resp = await self.http.post(
            f"{self.base_url}/{page_id}/messages",
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": text},
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        result = resp.json()
        msg_id = result.get("message_id") if resp.status_code == 200 else None
        if resp.status_code != 200:
            logger.error(f"Instagram send failed: {resp.status_code} {result}")
        return {"success": resp.status_code == 200, "message_id": msg_id}

    async def mark_whatsapp_read(
        self, phone_id: str, access_token: str, message_id: str
    ) -> bool:
        """Mark a WhatsApp message as read (blue checkmarks)."""
        resp = await self.http.post(
            f"{self.base_url}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return resp.status_code == 200

    async def get_instagram_user_profile(
        self, user_id: str, access_token: str
    ) -> dict:
        """Fetch Instagram user's name (used for personalization)."""
        resp = await self.http.get(
            f"{self.base_url}/{user_id}",
            params={"fields": "name,username", "access_token": access_token},
        )
        if resp.status_code == 200:
            return resp.json()
        return {}


# Global client instance
meta_client = MetaGraphClient()


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: LEAD RESOLUTION SERVICE
# Finds or creates leads, resolves agency, manages conversations.
# ═══════════════════════════════════════════════════════════════════════

async def resolve_agency_by_phone_id(
    db: AsyncSession, phone_id: str
) -> Agency | None:
    """Find which agency owns this WhatsApp phone number."""
    result = await db.execute(
        select(Agency).where(Agency.whatsapp_phone_id == phone_id)
    )
    return result.scalar_one_or_none()


async def resolve_agency_by_page_id(
    db: AsyncSession, page_id: str
) -> Agency | None:
    """Find which agency owns this Meta/Instagram page."""
    result = await db.execute(
        select(Agency).where(Agency.meta_page_id == page_id)
    )
    return result.scalar_one_or_none()


async def find_or_create_lead(
    db: AsyncSession,
    agency_id: UUID,
    phone: str | None,
    source: LeadSource,
    name: str | None = None,
    email: str | None = None,
    source_ref: str | None = None,
) -> tuple[Lead, bool]:
    """
    Find existing lead by phone+agency, or create a new one.
    Returns (lead, is_new).
    
    For Instagram leads without a phone, the IGSID is used as source_ref
    and the phone is set to a placeholder until collected in conversation.
    """
    is_new = False

    if phone:
        result = await db.execute(
            select(Lead).where(Lead.phone == phone, Lead.agency_id == agency_id)
        )
        lead = result.scalar_one_or_none()
        if lead:
            # Update name/email if we have better data now
            if name and not lead.name:
                lead.name = name
            if email and not lead.email:
                lead.email = email
            return lead, False

    # Create new lead
    lead = Lead(
        agency_id=agency_id,
        phone=phone or f"pending_{source_ref or uuid4().hex[:8]}",
        name=name,
        email=email,
        source=source,
        source_ref=source_ref,
        status=LeadStatus.NEW,
    )
    db.add(lead)
    await db.flush()
    is_new = True

    # Emit analytics event
    event = AnalyticsEvent(
        agency_id=agency_id,
        event_type="lead.created",
        event_category="lead",
        lead_id=lead.id,
        source=source.value,
        event_data={"channel": source.value, "source_ref": source_ref},
    )
    db.add(event)

    # Increment agency lead counter
    await db.execute(
        update(Agency)
        .where(Agency.id == agency_id)
        .values(leads_this_month=Agency.leads_this_month + 1)
    )

    return lead, is_new


async def get_or_create_conversation(
    db: AsyncSession,
    lead_id: UUID,
    agency_id: UUID,
    channel: LeadSource,
    channel_ref: str | None = None,
) -> Conversation:
    """Find an active conversation or create a new one."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.lead_id == lead_id,
            Conversation.channel == channel,
            Conversation.status.in_([
                ConversationStatus.ACTIVE,
                ConversationStatus.WAITING_RESPONSE,
            ]),
        ).order_by(Conversation.started_at.desc()).limit(1)
    )
    conv = result.scalar_one_or_none()

    if conv:
        return conv

    conv = Conversation(
        lead_id=lead_id,
        agency_id=agency_id,
        channel=channel,
        channel_ref=channel_ref,
        status=ConversationStatus.ACTIVE,
    )
    db.add(conv)
    await db.flush()
    return conv


async def save_inbound_message(
    db: AsyncSession,
    conversation_id: UUID,
    lead_id: UUID,
    text: str,
    message_type: str = "text",
    external_msg_id: str | None = None,
) -> Message:
    """Save an incoming message and update conversation counters."""
    msg = Message(
        conversation_id=conversation_id,
        lead_id=lead_id,
        role=MessageRole.USER,
        content=text,
        message_type=message_type,
        external_msg_id=external_msg_id,
        delivery_status="delivered",
    )
    db.add(msg)

    # Update conversation counters
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            message_count=Conversation.message_count + 1,
            last_message_at=datetime.utcnow(),
            status=ConversationStatus.ACTIVE,
        )
    )

    await db.flush()
    return msg


async def save_outbound_message(
    db: AsyncSession,
    conversation_id: UUID,
    lead_id: UUID,
    text: str,
    external_msg_id: str | None = None,
    token_count: int | None = None,
) -> Message:
    """Save an AI response message."""
    msg = Message(
        conversation_id=conversation_id,
        lead_id=lead_id,
        role=MessageRole.ASSISTANT,
        content=text,
        external_msg_id=external_msg_id,
        delivery_status="sent" if external_msg_id else "pending",
        token_count=token_count,
    )
    db.add(msg)

    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            message_count=Conversation.message_count + 1,
            last_message_at=datetime.utcnow(),
            total_ai_tokens=Conversation.total_ai_tokens + (token_count or 0),
            status=ConversationStatus.WAITING_RESPONSE,
        )
    )

    await db.flush()
    return msg


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: WEBHOOK ENDPOINTS
# Public endpoints — no JWT auth, verified by HMAC signature.
# ═══════════════════════════════════════════════════════════════════════

def verify_signature(body: bytes, signature_header: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header."""
    if not settings.META_APP_SECRET:
        return True  # Skip in development

    expected = "sha256=" + hmac.new(
        settings.META_APP_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.get("/meta/verify")
async def webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
):
    """
    Meta webhook verification challenge.
    
    During Meta App setup, Meta sends a GET request with a challenge
    to verify you own the webhook URL. You must return the challenge
    value if the verify_token matches.
    """
    if hub_verify_token != settings.META_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    return int(hub_challenge)


@router.post("/meta/incoming")
async def unified_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Unified webhook receiver for ALL Meta channels.
    
    This single endpoint handles:
    1. WhatsApp messages (text, image, interactive replies)
    2. Instagram DMs
    3. Meta Lead Ad form submissions
    
    The channel is auto-detected from the payload structure.
    """
    body = await request.body()

    # Verify HMAC signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.ENVIRONMENT == "production":
        if not verify_signature(body, signature):
            logger.warning("Invalid webhook signature rejected")
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Detect channel and parse
    channel = detect_channel(payload)
    logger.info(f"Webhook received: channel={channel}")

    events: list[InboundEvent] = []

    if channel == "whatsapp":
        events = parse_whatsapp_webhook(payload)
    elif channel == "instagram":
        events = parse_instagram_webhook(payload)
    elif channel == "leadgen":
        events = parse_leadgen_webhook(payload)
    else:
        logger.warning(f"Unknown webhook channel: {json.dumps(payload)[:500]}")
        return {"status": "ignored"}

    # Process each event
    for event in events:
        try:
            await process_inbound_event(db, event)
        except Exception as e:
            logger.exception(f"Error processing {event.channel} event: {e}")
            # Don't fail the whole webhook — process remaining events

    await db.commit()
    return {"status": "ok", "processed": len(events)}


async def process_inbound_event(db: AsyncSession, event: InboundEvent):
    """
    Route a normalized inbound event to the correct handler.
    This is the central dispatch function.
    """
    if event.channel == ChannelType.LEAD_AD:
        await handle_lead_ad_event(db, event)
    elif event.channel == ChannelType.WHATSAPP:
        await handle_whatsapp_event(db, event)
    elif event.channel == ChannelType.INSTAGRAM:
        await handle_instagram_event(db, event)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: CHANNEL-SPECIFIC HANDLERS
# Each handler implements the full flow for its channel.
# ═══════════════════════════════════════════════════════════════════════

async def handle_lead_ad_event(db: AsyncSession, event: InboundEvent):
    """
    Handle a Meta Lead Ad form submission.
    
    Flow:
    1. Resolve agency by page_id
    2. Fetch form data from Graph API (name, phone, email, custom fields)
    3. Create lead with pre-filled qualification data
    4. Attribute to campaign
    5. If WhatsApp is connected, send proactive welcome template
    """
    agency = await resolve_agency_by_page_id(db, event.page_id or event.agency_phone_id)
    if not agency:
        logger.warning(f"No agency found for page_id={event.page_id}")
        return

    # Fetch the actual form data from Meta
    # The agency must have a page access token configured
    page_token = agency.whatsapp_access_token  # Often the same token works
    if not page_token:
        logger.error(f"Agency {agency.id} has no access token for Graph API")
        return

    try:
        lead_data = await meta_client.fetch_leadgen_data(event.leadgen_id, page_token)
    except Exception as e:
        logger.error(f"Failed to fetch leadgen data: {e}")
        # Create lead with placeholder data
        lead_data = {"name": None, "phone": None, "email": None, "fields": {}}

    # Create or find lead
    lead, is_new = await find_or_create_lead(
        db,
        agency_id=agency.id,
        phone=lead_data.get("phone"),
        source=LeadSource.META_LEAD_AD,
        name=lead_data.get("name"),
        email=lead_data.get("email"),
        source_ref=event.leadgen_id,
    )

    # Store form fields as initial qualification data
    custom_fields = lead_data.get("fields", {})
    if custom_fields:
        existing = lead.qualification_data or {}
        lead.qualification_data = {**existing, **custom_fields}

    # Campaign attribution
    meta_campaign_id = lead_data.get("campaign_id")
    if meta_campaign_id:
        campaign_result = await db.execute(
            select(Campaign).where(
                Campaign.meta_campaign_id == meta_campaign_id,
                Campaign.agency_id == agency.id,
            )
        )
        campaign = campaign_result.scalar_one_or_none()
        if campaign:
            lead.campaign_id = campaign.id
            campaign.total_leads += 1
            if campaign.budget_spent and campaign.total_leads > 0:
                campaign.cost_per_lead = float(campaign.budget_spent) / campaign.total_leads

    await db.flush()

    # If agency has WhatsApp connected, send a proactive welcome
    if agency.whatsapp_phone_id and lead_data.get("phone"):
        try:
            await meta_client.send_whatsapp_template(
                phone_id=agency.whatsapp_phone_id,
                access_token=agency.whatsapp_access_token,
                to=lead_data["phone"],
                template_name="welcome_lead_ad",
                params=[lead_data.get("name") or "there"],
            )
            logger.info(f"Proactive welcome sent to {lead_data['phone']}")
        except Exception as e:
            logger.warning(f"Failed to send proactive welcome: {e}")

    logger.info(
        f"Lead Ad processed: lead={lead.id}, "
        f"name={lead_data.get('name')}, phone={lead_data.get('phone')}"
    )


async def handle_whatsapp_event(db: AsyncSession, event: InboundEvent):
    """
    Handle an incoming WhatsApp message.
    
    Flow:
    1. Resolve agency by phone_number_id
    2. Find or create lead by sender phone
    3. Get or create conversation
    4. Save the message
    5. Mark as read (blue checkmarks)
    6. Run chatbot engine
    7. Send AI response back via WhatsApp
    """
    agency = await resolve_agency_by_phone_id(db, event.agency_phone_id)
    if not agency:
        logger.warning(f"No agency for WA phone_id={event.agency_phone_id}")
        return

    lead, is_new = await find_or_create_lead(
        db,
        agency_id=agency.id,
        phone=event.sender_phone,
        source=LeadSource.WHATSAPP,
        name=event.sender_name,
    )

    # Update lead status if new
    if is_new or lead.status == LeadStatus.NEW:
        lead.status = LeadStatus.QUALIFYING

    conversation = await get_or_create_conversation(
        db, lead.id, agency.id, LeadSource.WHATSAPP,
        channel_ref=event.external_msg_id,
    )

    await save_inbound_message(
        db, conversation.id, lead.id,
        text=event.message_text or "",
        message_type=event.message_type.value,
        external_msg_id=event.external_msg_id,
    )

    # Mark as read
    if event.external_msg_id and agency.whatsapp_access_token:
        await meta_client.mark_whatsapp_read(
            agency.whatsapp_phone_id,
            agency.whatsapp_access_token,
            event.external_msg_id,
        )

    # Run chatbot engine
    from app.routers.chatbot import build_system_prompt, openai_client, TOOL_DEFINITIONS

    system_prompt = build_system_prompt(agency.name, lead.qualification_data or {})

    # Load conversation history
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    history = msg_result.scalars().all()

    messages = [{"role": "system", "content": system_prompt}]
    for msg in list(history)[-18:]:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        messages.append({"role": role, "content": msg.content})

    # Call OpenAI
    response = await openai_client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=500,
    )

    ai_text = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else None

    # Handle tool calls (qualification complete, property search)
    if response.choices[0].message.tool_calls:
        for tc in response.choices[0].message.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            if fn_name == "complete_qualification":
                lead.qualification_data = {**(lead.qualification_data or {}), **fn_args}
                lead.qualification_complete = True
                lead.status = LeadStatus.QUALIFIED
                lead.qualified_at = datetime.utcnow()

                from app.services.scoring import calculate_lead_score, save_lead_score, assign_agent_round_robin

                msg_dicts = [{"role": m.role.value if hasattr(m.role, "value") else m.role, "content": m.content} for m in history]
                score_data = calculate_lead_score(fn_args, msg_dicts)
                await save_lead_score(db, lead.id, agency.id, score_data)

                agent = await assign_agent_round_robin(db, agency.id)
                if agent:
                    lead.agent_id = agent.id

                conversation.status = ConversationStatus.QUALIFICATION_COMPLETE

                # Schedule follow-ups
                await schedule_whatsapp_follow_ups(db, lead.id, agency.id)

            # Re-call for final response text
            messages.append(response.choices[0].message.model_dump())
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({"status": "success"}),
            })
            followup = await openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )
            ai_text = followup.choices[0].message.content or ai_text

    # Send response via WhatsApp
    send_result = await meta_client.send_whatsapp_text(
        phone_id=agency.whatsapp_phone_id,
        access_token=agency.whatsapp_access_token,
        to=event.sender_phone,
        text=ai_text,
    )

    # Save outbound message
    await save_outbound_message(
        db, conversation.id, lead.id,
        text=ai_text,
        external_msg_id=send_result.get("message_id"),
        token_count=tokens,
    )

    await db.flush()
    logger.info(f"WA response sent to {event.sender_phone}: {ai_text[:80]}...")


async def handle_instagram_event(db: AsyncSession, event: InboundEvent):
    """
    Handle an incoming Instagram DM.
    
    Same flow as WhatsApp but:
    - User is identified by IGSID, not phone number
    - Response is sent via Instagram Messaging API
    - No template messages available (24h window only)
    """
    agency = await resolve_agency_by_page_id(db, event.agency_phone_id)
    if not agency:
        logger.warning(f"No agency for IG page_id={event.agency_phone_id}")
        return

    # Instagram doesn't give us a phone number directly.
    # We store the IGSID as source_ref and use a placeholder phone.
    lead, is_new = await find_or_create_lead(
        db,
        agency_id=agency.id,
        phone=None,
        source=LeadSource.INSTAGRAM_DM,
        source_ref=event.sender_id,
    )

    if is_new or lead.status == LeadStatus.NEW:
        lead.status = LeadStatus.QUALIFYING

    # Try to get their name from Instagram
    if is_new and agency.whatsapp_access_token:
        try:
            profile = await meta_client.get_instagram_user_profile(
                event.sender_id, agency.whatsapp_access_token
            )
            if profile.get("name"):
                lead.name = profile["name"]
        except Exception:
            pass

    conversation = await get_or_create_conversation(
        db, lead.id, agency.id, LeadSource.INSTAGRAM_DM,
        channel_ref=event.sender_id,
    )

    await save_inbound_message(
        db, conversation.id, lead.id,
        text=event.message_text or "",
        message_type=event.message_type.value,
        external_msg_id=event.external_msg_id,
    )

    # Run chatbot (same engine as WhatsApp)
    from app.routers.chatbot import build_system_prompt, openai_client, TOOL_DEFINITIONS

    # Add a note to the system prompt asking for the phone number
    extra_instruction = ""
    if lead.phone and lead.phone.startswith("pending_"):
        extra_instruction = (
            "\n\nIMPORTANT: This lead is from Instagram. You don't have their phone number yet. "
            "After your greeting, casually ask: 'What's the best phone number to reach you on?' "
            "This is needed so our property advisor can call them directly."
        )

    system_prompt = build_system_prompt(agency.name, lead.qualification_data or {}) + extra_instruction

    msg_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    history = msg_result.scalars().all()

    messages = [{"role": "system", "content": system_prompt}]
    for msg in list(history)[-18:]:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        messages.append({"role": role, "content": msg.content})

    response = await openai_client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=500,
    )

    ai_text = response.choices[0].message.content or ""

    # Send via Instagram
    send_result = await meta_client.send_instagram_text(
        page_id=event.agency_phone_id,
        access_token=agency.whatsapp_access_token,
        recipient_id=event.sender_id,
        text=ai_text,
    )

    await save_outbound_message(
        db, conversation.id, lead.id,
        text=ai_text,
        external_msg_id=send_result.get("message_id"),
    )

    await db.flush()
    logger.info(f"IG response sent to {event.sender_id}: {ai_text[:80]}...")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: FOLLOW-UP SCHEDULER
# ═══════════════════════════════════════════════════════════════════════

FOLLOW_UP_TEMPLATES = {
    1: "bahera_followup_day1",  # "Hi {name}, thanks for your interest..."
    3: "bahera_followup_day3",  # "Hi {name}, checking in..."
    7: "bahera_followup_day7",  # "Hi {name}, new options available..."
}


async def schedule_whatsapp_follow_ups(
    db: AsyncSession, lead_id: UUID, agency_id: UUID
):
    """Create Day 1, 3, 7 follow-up schedule for a qualified lead."""
    now = datetime.utcnow()
    for day, template in FOLLOW_UP_TEMPLATES.items():
        fu = FollowUp(
            lead_id=lead_id,
            agency_id=agency_id,
            day_number=day,
            channel=LeadSource.WHATSAPP,
            template_key=template,
            status=FollowUpStatus.PENDING,
            scheduled_at=now + timedelta(days=day),
        )
        db.add(fu)
    await db.flush()


async def process_due_follow_ups(db: AsyncSession):
    """
    Job runner: process all follow-ups that are due.
    Call this from APScheduler every 5 minutes.
    """
    now = datetime.utcnow()
    result = await db.execute(
        select(FollowUp)
        .where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.scheduled_at <= now)
        .limit(50)
    )
    follow_ups = result.scalars().all()

    for fu in follow_ups:
        lead_result = await db.execute(select(Lead).where(Lead.id == fu.lead_id))
        lead = lead_result.scalar_one_or_none()
        if not lead or lead.status in ("converted", "lost", "archived"):
            fu.status = FollowUpStatus.SKIPPED
            continue

        agency_result = await db.execute(select(Agency).where(Agency.id == fu.agency_id))
        agency = agency_result.scalar_one_or_none()
        if not agency or not agency.whatsapp_phone_id:
            fu.status = FollowUpStatus.CANCELLED
            continue

        try:
            result = await meta_client.send_whatsapp_template(
                phone_id=agency.whatsapp_phone_id,
                access_token=agency.whatsapp_access_token,
                to=lead.phone,
                template_name=fu.template_key,
                params=[lead.name or "there"],
            )
            if result.get("success"):
                fu.status = FollowUpStatus.SENT
                fu.sent_at = datetime.utcnow()
            else:
                fu.status = FollowUpStatus.FAILED
        except Exception as e:
            fu.status = FollowUpStatus.FAILED
            logger.exception(f"Follow-up failed: {e}")

    await db.flush()
    if follow_ups:
        logger.info(f"Processed {len(follow_ups)} follow-ups")
