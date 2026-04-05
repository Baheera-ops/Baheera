"""
WhatsApp Cloud API integration: send messages, templates, and interactive messages.
"""

import logging
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger("bahera.whatsapp")
settings = get_settings()

BASE_URL = "https://graph.facebook.com/v19.0"


async def send_text_message(
    to_phone: str,
    text: str,
    phone_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """
    Send a plain text message via WhatsApp Cloud API.
    
    Args:
        to_phone: Recipient phone number (with country code, no +)
        text: Message text (max 4096 chars)
        phone_id: WhatsApp Business phone number ID (defaults to env var)
        access_token: API access token (defaults to env var)
    """
    phone_id = phone_id or settings.WHATSAPP_PHONE_ID
    access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {"body": text},
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    if response.status_code != 200:
        logger.error(f"WhatsApp send failed: {response.status_code} {response.text}")
        return {"success": False, "error": response.text}

    data = response.json()
    msg_id = data.get("messages", [{}])[0].get("id")
    return {"success": True, "message_id": msg_id}


async def send_template_message(
    to_phone: str,
    template_name: str,
    language_code: str = "en_US",
    parameters: Optional[list[str]] = None,
    phone_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """
    Send a pre-approved WhatsApp template message.
    Templates must be approved in Meta Business Suite before use.
    
    Example templates for Bahera:
      - follow_up_day1: "Hi {{1}}, thanks for your interest in {{2}}..."
      - follow_up_day3: "Hi {{1}}, just checking in..."
      - follow_up_day7: "Hi {{1}}, we have new options..."
    """
    phone_id = phone_id or settings.WHATSAPP_PHONE_ID
    access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN

    components = []
    if parameters:
        components.append({
            "type": "body",
            "parameters": [
                {"type": "text", "text": p} for p in parameters
            ],
        })

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    "components": components,
                },
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    if response.status_code != 200:
        logger.error(f"WhatsApp template send failed: {response.status_code} {response.text}")
        return {"success": False, "error": response.text}

    data = response.json()
    msg_id = data.get("messages", [{}])[0].get("id")
    return {"success": True, "message_id": msg_id}


async def send_interactive_buttons(
    to_phone: str,
    body_text: str,
    buttons: list[dict],
    header_text: Optional[str] = None,
    phone_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """
    Send an interactive button message (max 3 buttons).
    
    Args:
        buttons: [{"id": "btn_1", "title": "Yes"}, ...]
    """
    phone_id = phone_id or settings.WHATSAPP_PHONE_ID
    access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN

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
    if header_text:
        interactive["header"] = {"type": "text", "text": header_text}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "interactive",
                "interactive": interactive,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    if response.status_code != 200:
        logger.error(f"WhatsApp interactive send failed: {response.status_code} {response.text}")
        return {"success": False, "error": response.text}

    data = response.json()
    msg_id = data.get("messages", [{}])[0].get("id")
    return {"success": True, "message_id": msg_id}


async def mark_as_read(
    message_id: str,
    phone_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> bool:
    """Mark a received message as read (shows blue ticks)."""
    phone_id = phone_id or settings.WHATSAPP_PHONE_ID
    access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5.0,
        )
    return response.status_code == 200
