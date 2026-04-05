"""
Chatbot API: receives messages from any channel, runs AI qualification,
returns responses. This is the core revenue-generating endpoint.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_agency_id
from app.models.models import (
    Agency, Agent, Conversation, ConversationStatus, Lead, LeadSource,
    LeadStatus, Message, MessageRole,
)
from app.schemas.schemas import ChatbotMessageRequest, ChatbotResponse
from app.services.analytics import emit_event
from app.services.scoring import assign_agent_round_robin, calculate_lead_score, save_lead_score

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])
settings = get_settings()
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


SYSTEM_PROMPT_TEMPLATE = """You are Bahera, a professional real estate assistant for {agency_name}.

RULES:
- Respond in the buyer's language (detect from their message)
- Keep responses to 2-3 sentences max
- Ask ONE qualification question at a time
- If they ask about properties, answer helpfully then continue qualifying
- Never fabricate property details

QUALIFICATION TARGETS (collect through natural conversation):
- budget_range (min/max in local currency)
- property_type (apartment/villa/townhouse/etc)
- preferred_location (area or district)
- timeline_months (when they plan to buy)
- payment_method (cash/mortgage/installments)
- purpose (investment/end_use/both)

ALREADY COLLECTED:
{collected_data}

STILL NEEDED:
{missing_fields}

When ALL required fields are collected, call the complete_qualification function.
When the buyer asks about specific properties, call the property_search function.
"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "complete_qualification",
            "description": "Call when ALL required qualification data has been collected from the buyer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_min": {"type": "number"},
                    "budget_max": {"type": "number"},
                    "property_type": {"type": "string"},
                    "preferred_location": {"type": "string"},
                    "timeline_months": {"type": "integer"},
                    "payment_method": {"type": "string", "enum": ["cash", "mortgage", "installments"]},
                    "purpose": {"type": "string", "enum": ["investment", "end_use", "both"]},
                    "bedrooms": {"type": "integer"},
                    "notes": {"type": "string"},
                },
                "required": ["budget_max", "property_type", "preferred_location",
                             "timeline_months", "payment_method", "purpose"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "property_search",
            "description": "Search for matching properties based on buyer criteria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "location": {"type": "string"},
                    "property_type": {"type": "string"},
                    "budget_max": {"type": "number"},
                    "bedrooms": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
]


def build_system_prompt(agency_name: str, qualification_data: dict) -> str:
    """Assemble the system prompt with live qualification progress."""
    required = ["budget_range", "property_type", "preferred_location",
                "timeline_months", "payment_method", "purpose"]

    collected = []
    missing = []
    for field in required:
        val = qualification_data.get(field) or qualification_data.get(field.replace("_range", "_max"))
        if val:
            collected.append(f"  - {field}: {val}")
        else:
            missing.append(f"  - {field}")

    return SYSTEM_PROMPT_TEMPLATE.format(
        agency_name=agency_name,
        collected_data="\n".join(collected) if collected else "  (none yet)",
        missing_fields="\n".join(missing) if missing else "  (all collected — call complete_qualification!)",
    )


@router.post("/{lead_id}/message", response_model=ChatbotResponse)
async def send_message(
    lead_id: UUID,
    body: ChatbotMessageRequest,
    agency_id: str = Depends(get_current_agency_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Process an incoming message from a lead.
    Runs AI qualification, handles tool calls, returns the response.
    """

    # ── Load lead ────────────────────────────────────────────────────
    result = await db.execute(select(Lead).where(Lead.id == lead_id, Lead.agency_id == agency_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # ── Load agency ──────────────────────────────────────────────────
    agency_result = await db.execute(select(Agency).where(Agency.id == agency_id))
    agency = agency_result.scalar_one()

    # ── Get or create conversation ───────────────────────────────────
    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.lead_id == lead_id,
            Conversation.agency_id == agency_id,
            Conversation.status.in_(["active", "waiting_response"]),
        )
        .order_by(Conversation.started_at.desc())
        .limit(1)
    )
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(
            lead_id=lead_id,
            agency_id=agency_id,
            channel=body.channel,
            status=ConversationStatus.ACTIVE,
        )
        db.add(conversation)
        await db.flush()

        lead.status = LeadStatus.QUALIFYING
        await db.flush()

    # ── Load message history ─────────────────────────────────────────
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    history = msg_result.scalars().all()

    # ── Save the incoming user message ───────────────────────────────
    user_msg = Message(
        conversation_id=conversation.id,
        lead_id=lead_id,
        role=MessageRole.USER,
        content=body.message,
    )
    db.add(user_msg)
    await db.flush()

    # ── Build OpenAI messages array ──────────────────────────────────
    system_prompt = build_system_prompt(agency.name, lead.qualification_data or {})
    messages = [{"role": "system", "content": system_prompt}]

    for msg in history[-18:]:  # Keep last 18 messages to stay within context
        messages.append({"role": msg.role.value if hasattr(msg.role, 'value') else msg.role, "content": msg.content})

    messages.append({"role": "user", "content": body.message})

    # ── Call OpenAI ──────────────────────────────────────────────────
    response = await openai_client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=500,
    )

    ai_message = response.choices[0].message
    qualification_complete = False
    score = None
    assigned_agent_name = None

    # ── Handle tool calls ────────────────────────────────────────────
    if ai_message.tool_calls:
        for tool_call in ai_message.tool_calls:
            import json
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            if fn_name == "complete_qualification":
                # Save qualification data
                lead.qualification_data = {**lead.qualification_data, **fn_args}
                await db.flush()

                # Score the lead
                msg_dicts = [{"role": m.role.value if hasattr(m.role, 'value') else m.role, "content": m.content} for m in history]
                score_data = calculate_lead_score(fn_args, msg_dicts)
                lead_score = await save_lead_score(db, lead.id, UUID(agency_id), score_data)

                # Assign agent
                agent = await assign_agent_round_robin(db, UUID(agency_id))
                if agent:
                    lead.agent_id = agent.id
                    assigned_agent_name = agent.name
                    await db.flush()

                qualification_complete = True
                score = score_data["total_score"]

                await emit_event(
                    db, agency_id, "lead.qualified", "lead",
                    lead_id=lead.id, agent_id=agent.id if agent else None,
                    event_data={"score": score, "agent": assigned_agent_name},
                )

            elif fn_name == "property_search":
                pass  # RAG search would execute here

            # Re-call OpenAI with tool result for final response
            messages.append(ai_message.model_dump())
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps({"status": "success", "agent": assigned_agent_name}),
            })

            followup = await openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )
            ai_message = followup.choices[0].message

    response_text = ai_message.content or ""

    # ── Save AI response ─────────────────────────────────────────────
    ai_msg = Message(
        conversation_id=conversation.id,
        lead_id=lead_id,
        role=MessageRole.ASSISTANT,
        content=response_text,
        token_count=response.usage.total_tokens if response.usage else None,
    )
    db.add(ai_msg)

    # Update conversation counters
    conversation.message_count += 2
    conversation.last_message_at = datetime.utcnow()
    if qualification_complete:
        conversation.status = ConversationStatus.QUALIFICATION_COMPLETE

    await db.flush()

    return ChatbotResponse(
        response=response_text,
        lead_id=lead_id,
        conversation_id=conversation.id,
        qualification_complete=qualification_complete,
        score=score,
        assigned_agent=assigned_agent_name,
    )
