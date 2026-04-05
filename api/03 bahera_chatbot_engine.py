"""
BAHERA AI Chatbot Engine
=========================
Complete implementation of the conversation engine, qualification flow,
lead scoring, property recommendation, and prompt management.

Architecture: OpenAI function calling + RAG via pgvector
Model: gpt-4o-mini (qualification) / gpt-4o (complex property Q&A fallback)
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger("bahera.chatbot")


# =============================================================================
# SECTION 1: MASTER SYSTEM PROMPT
# =============================================================================

MASTER_SYSTEM_PROMPT = """
You are Bahera, a professional and friendly real estate assistant working for {agency_name}.

═══════════════════════════════════════════
CORE IDENTITY
═══════════════════════════════════════════

You help potential property buyers find their ideal home or investment. You are warm,
knowledgeable, and efficient. You feel like a trusted advisor — not a salesperson, and
definitely not a chatbot filling out a form.

═══════════════════════════════════════════
CONVERSATION RULES
═══════════════════════════════════════════

1. RESPOND IN THE BUYER'S LANGUAGE. If they write in Arabic, respond in Arabic.
   If English, respond in English. If they mix, follow their dominant language.
   Supported: English, Arabic, Russian, French, Chinese, Hindi, Urdu.

2. Keep messages SHORT — 2 to 3 sentences maximum per response.
   WhatsApp users hate walls of text. Be concise.

3. Ask ONE qualification question at a time.
   Exception: you may bundle 2 questions if the lead is highly engaged
   (giving detailed answers, asking follow-up questions themselves).

4. NEVER repeat a question the lead has already answered.
   Refer to the QUALIFICATION PROGRESS section below to see what's been collected.

5. If the lead asks about a specific property or project at ANY point,
   IMMEDIATELY call the property_search function and answer their question.
   Qualification can wait — the lead's interest is more valuable than your checklist.

6. If the lead asks a question you don't know the answer to and the knowledge base
   has no relevant results, say: "Let me connect you with a specialist who can
   answer that in detail" — never fabricate property details.

7. NEVER pressure the buyer. If they say "just browsing" or "not sure yet",
   acknowledge that warmly and still try to understand their general preferences.

8. Use the buyer's name when you know it. Personal touch matters.

9. When recommending properties, present a MAXIMUM of 3 options. Format them
   as a numbered list with: project name, unit type, price, and one standout feature.

10. After qualification is complete, ALWAYS offer to connect with a human advisor.
    Frame it as a benefit: "I can connect you with [Agent Name], our [area] specialist,
    who can arrange a viewing for you."

═══════════════════════════════════════════
QUALIFICATION TARGETS
═══════════════════════════════════════════

You need to collect these data points through natural conversation.
Do NOT ask them as a checklist — weave them into the dialogue.

REQUIRED (must collect before calling complete_qualification):
  • budget_range — Their price range (min and/or max in local currency)
  • property_type — apartment, villa, townhouse, penthouse, studio, office, land
  • preferred_location — Area, district, or city
  • timeline_months — When they plan to buy (number of months)
  • payment_method — cash, mortgage, or installments
  • purpose — investment, end_use (living in it), or both

OPTIONAL (collect if conversation flows naturally, don't force):
  • bedrooms — Number of bedrooms
  • nationality — Buyer's nationality (relevant for ownership rules in some markets)
  • specific_features — Sea view, high floor, garden, etc.

═══════════════════════════════════════════
QUALIFICATION PROGRESS (LIVE STATE)
═══════════════════════════════════════════

{qualification_progress}

═══════════════════════════════════════════
DYNAMIC FOLLOW-UP STRATEGY
═══════════════════════════════════════════

Your next question should be chosen based on what's already known and what's
most natural to ask next. Here's the priority order:

IF budget is unknown → Ask about budget (highest scoring signal)
IF property_type is unknown → Ask what type of property they're looking for
IF location is unknown → Suggest areas based on their budget + type
IF timeline is unknown → Ask when they're planning to make the move
IF payment_method is unknown → Ask about financing preference
IF purpose is unknown → Ask if it's for investment or personal use

FOLLOW-UP INTELLIGENCE:
- If budget is high (>2M AED) and type is villa → ask about plot size preference
- If purpose is investment → ask about rental yield expectations
- If timeline is <3 months → emphasize ready-to-move-in properties
- If payment_method is installments → highlight developer payment plans
- If location is mentioned → immediately suggest matching projects from knowledge base
- If they mention a specific building or project → call property_search immediately

═══════════════════════════════════════════
AGENCY CONTEXT
═══════════════════════════════════════════

Agency: {agency_name}
Specialization: {agency_specialization}
Active markets: {agency_markets}
Language preference: {agency_language}

═══════════════════════════════════════════
PROPERTY KNOWLEDGE
═══════════════════════════════════════════

{property_context}

When you have property knowledge above, use it to:
- Answer specific questions about projects (pricing, payment plans, amenities)
- Recommend matching properties based on the buyer's stated criteria
- Provide accurate details — never guess or extrapolate beyond the provided data

If no property knowledge is provided, you can still have the qualification
conversation — just don't recommend specific projects.

═══════════════════════════════════════════
GUARDRAILS
═══════════════════════════════════════════

- NEVER share other buyers' information or conversations
- NEVER make promises about price, availability, or returns that aren't in the knowledge base
- NEVER discuss competitors negatively
- If asked about legal matters (visas, ownership laws, taxes), give general guidance
  only and recommend consulting a legal advisor
- If the conversation becomes hostile or abusive, respond once with: "I understand
  this can be frustrating. Let me connect you with a team member who can help."
  Then call complete_qualification with whatever data you have.
- Maximum conversation length: 20 messages. If you haven't completed qualification
  by message 15, start bundling remaining questions.
"""


# =============================================================================
# SECTION 2: QUALIFICATION PROGRESS TEMPLATE
# =============================================================================

QUALIFICATION_PROGRESS_TEMPLATE = """
Already collected:
{collected_items}

Still needed:
{missing_items}

Conversation turn: {turn_count} / 20
Questions asked so far: {questions_asked}
"""

def build_qualification_progress(qualification_data: dict, questions_asked: list[str], turn_count: int) -> str:
    """Build the live qualification progress string injected into the system prompt."""

    all_fields = {
        "budget_range": "Budget range",
        "property_type": "Property type",
        "preferred_location": "Preferred location",
        "timeline_months": "Purchase timeline",
        "payment_method": "Payment method (cash/mortgage/installments)",
        "purpose": "Purpose (investment/living/both)",
        "bedrooms": "Bedrooms (optional)",
        "nationality": "Nationality (optional)",
        "specific_features": "Specific features (optional)",
    }

    required = ["budget_range", "property_type", "preferred_location",
                "timeline_months", "payment_method", "purpose"]

    collected = []
    missing = []

    for field, label in all_fields.items():
        value = qualification_data.get(field)
        if value:
            collected.append(f"  ✓ {label}: {value}")
        elif field in required:
            missing.append(f"  ✗ {label} ← REQUIRED")
        else:
            missing.append(f"  ○ {label} (optional, skip if not natural)")

    return QUALIFICATION_PROGRESS_TEMPLATE.format(
        collected_items="\n".join(collected) if collected else "  (none yet — this is the start of the conversation)",
        missing_items="\n".join(missing),
        turn_count=turn_count,
        questions_asked=", ".join(questions_asked) if questions_asked else "none yet",
    )


# =============================================================================
# SECTION 3: TOOL DEFINITIONS (OpenAI Function Calling)
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "property_search",
            "description": (
                "Search the knowledge base for properties matching the buyer's criteria. "
                "Call this when: (1) the lead asks about a specific project or area, "
                "(2) you have enough info to recommend properties, or "
                "(3) the lead asks a specific question like pricing or payment plans."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query, e.g., '2BR apartment Dubai Marina sea view under 1.5M'"
                    },
                    "location": {
                        "type": "string",
                        "description": "Area or district name"
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["apartment", "villa", "townhouse", "penthouse",
                                "studio", "office", "retail", "land"]
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Maximum budget in local currency"
                    },
                    "bedrooms": {
                        "type": "integer",
                        "description": "Number of bedrooms"
                    },
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Desired features like 'sea view', 'garden', 'high floor'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_qualification",
            "description": (
                "Call this ONLY when you have collected ALL required qualification data "
                "(budget, property type, location, timeline, payment method, purpose). "
                "This triggers lead scoring and agent assignment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_min": {
                        "type": "number",
                        "description": "Minimum budget in local currency"
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Maximum budget in local currency"
                    },
                    "budget_currency": {
                        "type": "string",
                        "default": "AED"
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["apartment", "villa", "townhouse", "penthouse",
                                "studio", "office", "land", "other"]
                    },
                    "bedrooms": {
                        "type": "integer"
                    },
                    "preferred_location": {
                        "type": "string",
                        "description": "Area, district, or community name"
                    },
                    "timeline_months": {
                        "type": "integer",
                        "description": "How many months until they plan to buy"
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["cash", "mortgage", "installments", "unknown"]
                    },
                    "purpose": {
                        "type": "string",
                        "enum": ["investment", "end_use", "both", "unknown"]
                    },
                    "nationality": {
                        "type": "string"
                    },
                    "specific_features": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional context from the conversation"
                    }
                },
                "required": [
                    "budget_max", "property_type", "preferred_location",
                    "timeline_months", "payment_method", "purpose"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_viewing",
            "description": (
                "Call this when the lead explicitly asks to schedule a property viewing "
                "or meet with an agent. This triggers the agent assignment flow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "property_name": {
                        "type": "string",
                        "description": "Name of the property/project they want to view"
                    },
                    "preferred_date": {
                        "type": "string",
                        "description": "When they'd like to visit (if mentioned)"
                    },
                    "notes": {
                        "type": "string"
                    }
                },
                "required": ["property_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hand_to_agent",
            "description": (
                "Call this when: (1) the lead explicitly asks to speak to a human, "
                "(2) the conversation becomes hostile, or (3) the lead asks complex "
                "legal/financial questions beyond your scope."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the conversation is being transferred"
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "How quickly the agent should respond"
                    }
                },
                "required": ["reason"]
            }
        }
    }
]


# =============================================================================
# SECTION 4: LEAD SCORING ENGINE
# =============================================================================

class ScoreBreakdown(BaseModel):
    """Full scoring breakdown for audit trail and analytics."""
    total_score: int = Field(ge=0, le=100)
    budget_score: int = Field(ge=0, le=25)
    timeline_score: int = Field(ge=0, le=20)
    payment_score: int = Field(ge=0, le=20)
    location_score: int = Field(ge=0, le=15)
    engagement_score: int = Field(ge=0, le=10)
    purpose_score: int = Field(ge=0, le=10)
    ai_adjustment: int = Field(ge=-10, le=10, default=0)
    ai_reasoning: str = ""
    rule_score_raw: int = 0


def calculate_rule_based_score(
    qualification_data: dict,
    conversation_messages: list[dict],
) -> ScoreBreakdown:
    """
    Calculate the rule-based lead score from qualification data.
    
    Scoring philosophy:
    - Budget clarity (25 pts): Specific = serious buyer. Vague = tire-kicker.
    - Timeline urgency (20 pts): Sooner = more motivated. 
    - Payment method (20 pts): Cash > pre-approved mortgage > exploring.
    - Location specificity (15 pts): Named community > general area > "anywhere".
    - Engagement quality (10 pts): Long, detailed answers = genuine interest.
    - Purpose clarity (10 pts): Investment with clear ROI goals > vague browsing.
    """
    
    breakdown = ScoreBreakdown(total_score=0, rule_score_raw=0)
    
    # ── 1. Budget clarity (0-25 points) ──────────────────────────────
    budget_max = qualification_data.get("budget_max")
    budget_min = qualification_data.get("budget_min")
    
    if budget_max and budget_min:
        # Specific range: "1.2M to 1.8M" — very serious
        breakdown.budget_score = 25
    elif budget_max:
        # Only max given: "up to 1.5M" — still good
        breakdown.budget_score = 20
    elif budget_min:
        # Only min: "at least 1M" — somewhat defined
        breakdown.budget_score = 15
    else:
        # No budget at all
        breakdown.budget_score = 0
    
    # Budget size bonus: higher budgets slightly increase score
    # (investors with large budgets are typically more serious)
    if budget_max and budget_max > 5_000_000:
        breakdown.budget_score = min(25, breakdown.budget_score + 3)
    
    # ── 2. Timeline urgency (0-20 points) ────────────────────────────
    timeline = qualification_data.get("timeline_months")
    
    if timeline is not None:
        if timeline <= 1:
            breakdown.timeline_score = 20   # Immediate buyer
        elif timeline <= 3:
            breakdown.timeline_score = 18   # Very soon
        elif timeline <= 6:
            breakdown.timeline_score = 14   # Medium term
        elif timeline <= 12:
            breakdown.timeline_score = 8    # Planning ahead
        elif timeline <= 24:
            breakdown.timeline_score = 4    # Long term
        else:
            breakdown.timeline_score = 2    # Very long term
    
    # ── 3. Payment method (0-20 points) ──────────────────────────────
    payment = qualification_data.get("payment_method", "").lower()
    
    payment_scores = {
        "cash": 20,
        "mortgage": 14,              # Pre-approved or confirmed
        "installments": 12,          # Developer payment plan
        "exploring": 6,              # Haven't decided
        "unknown": 3,
    }
    breakdown.payment_score = payment_scores.get(payment, 0)
    
    # ── 4. Location specificity (0-15 points) ────────────────────────
    location = qualification_data.get("preferred_location", "")
    
    if location:
        words = location.strip().split()
        if len(words) >= 3:
            # Very specific: "Dubai Marina Tower 1" or "Palm Jumeirah Frond B"
            breakdown.location_score = 15
        elif len(words) >= 2:
            # Specific area: "Dubai Marina", "Business Bay"
            breakdown.location_score = 13
        elif len(words) == 1 and location.lower() not in ("dubai", "abu dhabi", "sharjah", "anywhere"):
            # Single specific area: "Marina", "Downtown"
            breakdown.location_score = 10
        else:
            # General city or "anywhere"
            breakdown.location_score = 5
    
    # ── 5. Engagement quality (0-10 points) ──────────────────────────
    user_messages = [m for m in conversation_messages if m.get("role") == "user"]
    
    if user_messages:
        avg_length = sum(len(m.get("content", "")) for m in user_messages) / len(user_messages)
        message_count = len(user_messages)
        
        # Length scoring
        if avg_length > 80:
            breakdown.engagement_score = 8      # Very detailed responses
        elif avg_length > 40:
            breakdown.engagement_score = 6      # Good engagement
        elif avg_length > 15:
            breakdown.engagement_score = 4      # Brief but responsive
        else:
            breakdown.engagement_score = 2      # Minimal engagement
        
        # Bonus for asking questions (strong buy signal)
        questions_asked = sum(1 for m in user_messages if "?" in m.get("content", ""))
        if questions_asked >= 2:
            breakdown.engagement_score = min(10, breakdown.engagement_score + 2)
    
    # ── 6. Purpose clarity (0-10 points) ─────────────────────────────
    purpose = qualification_data.get("purpose", "").lower()
    
    purpose_scores = {
        "investment": 10,            # Clear financial intent
        "both": 9,                   # Investment + personal — serious buyer
        "end_use": 8,               # Moving in — clear need
        "unknown": 3,
    }
    breakdown.purpose_score = purpose_scores.get(purpose, 3)
    
    # ── Calculate raw total ──────────────────────────────────────────
    breakdown.rule_score_raw = (
        breakdown.budget_score +
        breakdown.timeline_score +
        breakdown.payment_score +
        breakdown.location_score +
        breakdown.engagement_score +
        breakdown.purpose_score
    )
    breakdown.total_score = min(100, max(0, breakdown.rule_score_raw))
    
    return breakdown


# AI adjustment prompt — sent to OpenAI after rule-based scoring
AI_SCORING_PROMPT = """
You are a lead scoring analyst for a real estate platform.

Review this buyer conversation and assess the lead's genuine purchase intent.
The rule-based system scored this lead at {rule_score}/100.

CONVERSATION TRANSCRIPT:
{transcript}

QUALIFICATION DATA COLLECTED:
{qualification_json}

Analyze these BEHAVIORAL SIGNALS and adjust the score by -10 to +10:

POSITIVE signals (increase score):
  +2 to +5: Asks about specific buildings, floors, or unit numbers
  +2 to +5: Mentions visit dates, moving timelines, or logistics
  +1 to +3: Asks about payment plans, mortgages, or transfer fees
  +1 to +3: Mentions they've visited similar properties before
  +1 to +2: Asks about rental yields or ROI numbers
  +1 to +2: References a specific agent, recommendation, or referral

NEGATIVE signals (decrease score):
  -2 to -5: Gives one-word answers consistently, seems disengaged
  -2 to -5: Says "just browsing", "not sure", "maybe later" repeatedly
  -1 to -3: Refuses to share budget or timeline
  -1 to -3: Inconsistent information (different budget in different messages)
  -1 to -2: Only responds to prompts, never initiates questions

Respond with ONLY this JSON — no other text:
{{"adjustment": <integer from -10 to +10>, "reasoning": "<one sentence explanation>"}}
"""


async def calculate_ai_adjustment(
    client: AsyncOpenAI,
    rule_score: int,
    conversation_messages: list[dict],
    qualification_data: dict,
) -> tuple[int, str]:
    """Get AI sentiment adjustment for the lead score."""
    
    transcript = "\n".join(
        f"{'Lead' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in conversation_messages
        if m["role"] in ("user", "assistant") and m.get("content")
    )
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": AI_SCORING_PROMPT.format(
                    rule_score=rule_score,
                    transcript=transcript[:3000],  # Truncate for token limit
                    qualification_json=json.dumps(qualification_data, indent=2),
                )
            }],
            temperature=0.1,           # Low temp for consistent scoring
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        adjustment = max(-10, min(10, int(result.get("adjustment", 0))))
        reasoning = result.get("reasoning", "")
        return adjustment, reasoning
        
    except Exception as e:
        logger.warning(f"AI scoring adjustment failed: {e}")
        return 0, "AI adjustment unavailable"


async def score_lead(
    client: AsyncOpenAI,
    qualification_data: dict,
    conversation_messages: list[dict],
) -> ScoreBreakdown:
    """
    Full two-pass scoring: rule-based + AI adjustment.
    Returns the complete ScoreBreakdown for storage in lead_scores table.
    """
    
    # Pass 1: Rule-based scoring
    breakdown = calculate_rule_based_score(qualification_data, conversation_messages)
    
    # Pass 2: AI sentiment adjustment
    adjustment, reasoning = await calculate_ai_adjustment(
        client, breakdown.rule_score_raw, conversation_messages, qualification_data
    )
    
    breakdown.ai_adjustment = adjustment
    breakdown.ai_reasoning = reasoning
    breakdown.total_score = min(100, max(0, breakdown.rule_score_raw + adjustment))
    
    return breakdown


# =============================================================================
# SECTION 5: PROPERTY RECOMMENDATION ENGINE
# =============================================================================

async def search_properties(
    db,                             # Database session
    agency_id: UUID,
    query_embedding: list[float],   # 1536-dim vector
    filters: dict,
) -> list[dict]:
    """
    Hybrid search: vector similarity + structured filters.
    
    Strategy:
    1. Vector similarity finds semantically relevant chunks (payment plans,
       amenities descriptions, location context)
    2. Structured filters on the properties table narrow by price, type, bedrooms
    3. Results are merged and ranked by combined relevance
    """
    
    # Step 1: Vector similarity search on knowledge base
    rag_results = await db.execute("""
        SELECT
            kbe.content_text,
            kbe.chunk_metadata,
            kbe.property_id,
            1 - (kbe.embedding <=> :query_embedding) AS similarity,
            p.name AS property_name,
            p.location,
            p.price_from,
            p.price_to,
            p.property_type,
            p.bedrooms_min,
            p.bedrooms_max,
            p.payment_plan,
            p.handover_date,
            d.name AS developer_name
        FROM knowledge_base_embeddings kbe
        JOIN properties p ON p.id = kbe.property_id
        LEFT JOIN developers d ON d.id = p.developer_id
        WHERE kbe.agency_id = :agency_id
          AND p.is_active = TRUE
          AND 1 - (kbe.embedding <=> :query_embedding) > 0.65
        ORDER BY kbe.embedding <=> :query_embedding
        LIMIT 10
    """, {
        "agency_id": str(agency_id),
        "query_embedding": str(query_embedding),
    })
    
    # Step 2: Structured property search (for recommendation matching)
    structured_results = await db.execute("""
        SELECT
            p.id, p.name, p.location, p.property_type,
            p.price_from, p.price_to, p.bedrooms_min, p.bedrooms_max,
            p.payment_plan, p.handover_date, p.currency,
            p.amenities, p.construction_status,
            d.name AS developer_name
        FROM properties p
        LEFT JOIN developers d ON d.id = p.developer_id
        WHERE p.agency_id = :agency_id
          AND p.is_active = TRUE
          AND (:property_type IS NULL OR p.property_type = :property_type)
          AND (:budget_max IS NULL OR p.price_from <= :budget_max)
          AND (:bedrooms IS NULL OR :bedrooms BETWEEN p.bedrooms_min AND p.bedrooms_max)
          AND (:location IS NULL OR LOWER(p.location) LIKE LOWER(:location_pattern))
        ORDER BY
            CASE WHEN p.is_featured THEN 0 ELSE 1 END,
            p.price_from ASC
        LIMIT 5
    """, {
        "agency_id": str(agency_id),
        "property_type": filters.get("property_type"),
        "budget_max": filters.get("budget_max"),
        "bedrooms": filters.get("bedrooms"),
        "location": filters.get("location"),
        "location_pattern": f"%{filters.get('location', '')}%",
    })
    
    return {
        "rag_chunks": rag_results,
        "structured_matches": structured_results,
    }


def format_property_context_for_prompt(search_results: dict) -> str:
    """
    Format search results into a context block that gets injected
    into the system prompt for the AI to synthesize.
    """
    
    context_parts = []
    
    # Structured matches → property cards
    if search_results.get("structured_matches"):
        context_parts.append("MATCHING PROPERTIES:")
        for i, prop in enumerate(search_results["structured_matches"][:3], 1):
            card = (
                f"\n  [{i}] {prop['name']}"
                f"\n      Developer: {prop.get('developer_name', 'N/A')}"
                f"\n      Location: {prop['location']}"
                f"\n      Type: {prop['property_type']}"
                f"\n      Bedrooms: {prop.get('bedrooms_min', '?')}-{prop.get('bedrooms_max', '?')}"
                f"\n      Price: {prop['currency']} {prop['price_from']:,.0f}"
            )
            if prop.get("price_to"):
                card += f" - {prop['price_to']:,.0f}"
            if prop.get("payment_plan"):
                card += f"\n      Payment plan: {prop['payment_plan']}"
            if prop.get("handover_date"):
                card += f"\n      Handover: {prop['handover_date']}"
            if prop.get("construction_status"):
                card += f"\n      Status: {prop['construction_status']}"
            context_parts.append(card)
    
    # RAG chunks → detailed knowledge
    if search_results.get("rag_chunks"):
        context_parts.append("\nDETAILED KNOWLEDGE FROM BROCHURES:")
        seen_chunks = set()
        for chunk in search_results["rag_chunks"][:5]:
            text = chunk["content_text"].strip()
            if text not in seen_chunks:
                seen_chunks.add(text)
                source = chunk.get("property_name", "Unknown project")
                sim = chunk.get("similarity", 0)
                context_parts.append(
                    f"\n  [From: {source} | Relevance: {sim:.0%}]"
                    f"\n  {text[:500]}"
                )
    
    if not context_parts:
        return "(No matching properties found in the knowledge base for this query.)"
    
    return "\n".join(context_parts)


# =============================================================================
# SECTION 6: CONVERSATION ENGINE (Main Orchestrator)
# =============================================================================

class ConversationEngine:
    """
    Orchestrates the full chatbot lifecycle:
    
    1. Receives incoming message
    2. Loads conversation history + state
    3. Assembles the system prompt with live context
    4. Calls OpenAI with tools
    5. Handles tool calls (property search, qualification, handoff)
    6. Returns the response
    7. Updates conversation state
    """
    
    def __init__(self, openai_client: AsyncOpenAI, db):
        self.client = openai_client
        self.db = db
    
    async def process_message(
        self,
        lead_id: UUID,
        agency_id: UUID,
        incoming_message: str,
        channel: str,
    ) -> dict:
        """
        Main entry point. Process an incoming message and return the AI response.
        
        Returns:
            {
                "response_text": str,           # The message to send back
                "tool_calls": list,             # Any tool calls made
                "qualification_complete": bool, # Whether qualification finished
                "score": ScoreBreakdown | None, # If qualification completed
                "assigned_agent_id": UUID | None,
            }
        """
        
        # ── Load conversation state ──────────────────────────────────
        conversation = await self._load_or_create_conversation(
            lead_id, agency_id, channel
        )
        
        # ── Load message history ─────────────────────────────────────
        history = await self._load_message_history(conversation["id"])
        
        # ── Build the system prompt ──────────────────────────────────
        agency = await self._load_agency(agency_id)
        qualification_data = await self._load_qualification_data(lead_id)
        
        qualification_progress = build_qualification_progress(
            qualification_data=qualification_data,
            questions_asked=conversation.get("questions_asked", []),
            turn_count=conversation.get("message_count", 0),
        )
        
        # Check if we should inject property context
        property_context = "(No property search has been triggered yet.)"
        
        system_prompt = MASTER_SYSTEM_PROMPT.format(
            agency_name=agency["name"],
            agency_specialization=agency.get("settings", {}).get("specialization", "residential and commercial real estate"),
            agency_markets=agency.get("settings", {}).get("markets", "Dubai, Abu Dhabi"),
            agency_language=agency.get("settings", {}).get("chatbot_language", "en"),
            qualification_progress=qualification_progress,
            property_context=property_context,
        )
        
        # ── Build the messages array ─────────────────────────────────
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (last 20 messages to stay within context)
        for msg in history[-20:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        
        # Add the new incoming message
        messages.append({"role": "user", "content": incoming_message})
        
        # ── Call OpenAI ──────────────────────────────────────────────
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=500,
        )
        
        assistant_message = response.choices[0].message
        result = {
            "response_text": "",
            "tool_calls": [],
            "qualification_complete": False,
            "score": None,
            "assigned_agent_id": None,
        }
        
        # ── Handle tool calls ────────────────────────────────────────
        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                
                tool_result = await self._execute_tool(
                    fn_name, fn_args, lead_id, agency_id, conversation
                )
                result["tool_calls"].append({
                    "name": fn_name,
                    "arguments": fn_args,
                    "result": tool_result,
                })
                
                if fn_name == "complete_qualification":
                    result["qualification_complete"] = True
                    result["score"] = tool_result.get("score")
                    result["assigned_agent_id"] = tool_result.get("agent_id")
                
                if fn_name == "property_search":
                    # Re-call OpenAI with property context injected
                    property_context = format_property_context_for_prompt(tool_result)
                    
                    messages.append(assistant_message.model_dump())
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": property_context,
                    })
                    
                    followup = await self.client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        tools=TOOL_DEFINITIONS,
                        temperature=0.7,
                        max_tokens=500,
                    )
                    assistant_message = followup.choices[0].message
        
        result["response_text"] = assistant_message.content or ""
        
        # ── Save messages to database ────────────────────────────────
        await self._save_message(conversation["id"], lead_id, "user", incoming_message)
        await self._save_message(
            conversation["id"], lead_id, "assistant", result["response_text"],
            token_count=response.usage.total_tokens if response.usage else None,
        )
        
        # ── Update conversation state ────────────────────────────────
        await self._update_conversation_state(conversation["id"])
        
        return result
    
    async def _execute_tool(
        self, fn_name: str, fn_args: dict,
        lead_id: UUID, agency_id: UUID, conversation: dict,
    ) -> dict:
        """Execute a tool call and return the result."""
        
        if fn_name == "property_search":
            # Generate embedding for the search query
            embedding_response = await self.client.embeddings.create(
                model="text-embedding-3-small",
                input=fn_args["query"],
            )
            query_embedding = embedding_response.data[0].embedding
            
            results = await search_properties(
                self.db, agency_id, query_embedding,
                filters={
                    "property_type": fn_args.get("property_type"),
                    "budget_max": fn_args.get("budget_max"),
                    "bedrooms": fn_args.get("bedrooms"),
                    "location": fn_args.get("location"),
                }
            )
            return results
        
        elif fn_name == "complete_qualification":
            # Save qualification data
            await self._save_qualification_data(lead_id, fn_args)
            
            # Load conversation for scoring
            history = await self._load_message_history(conversation["id"])
            
            # Score the lead
            score = await score_lead(self.client, fn_args, history)
            
            # Save score
            await self._save_lead_score(lead_id, agency_id, score)
            
            # Assign agent via round-robin
            agent_id = await self._assign_agent(
                agency_id,
                specialization=fn_args.get("preferred_location"),
            )
            
            # Schedule follow-ups
            await self._schedule_follow_ups(lead_id, agency_id)
            
            return {
                "score": score,
                "agent_id": agent_id,
                "status": "qualification_complete",
            }
        
        elif fn_name == "schedule_viewing":
            agent_id = await self._assign_agent(agency_id)
            return {
                "agent_id": agent_id,
                "property": fn_args.get("property_name"),
                "status": "viewing_requested",
            }
        
        elif fn_name == "hand_to_agent":
            agent_id = await self._assign_agent(agency_id)
            return {
                "agent_id": agent_id,
                "reason": fn_args.get("reason"),
                "status": "handed_to_agent",
            }
        
        return {"error": f"Unknown function: {fn_name}"}

    # ── Database helper methods (implemented by your DB layer) ───────
    
    async def _load_or_create_conversation(self, lead_id, agency_id, channel):
        """Load active conversation or create a new one."""
        # Implementation: query conversations table
        pass
    
    async def _load_message_history(self, conversation_id):
        """Load all messages for a conversation, ordered by created_at."""
        pass
    
    async def _load_agency(self, agency_id):
        """Load agency settings and configuration."""
        pass
    
    async def _load_qualification_data(self, lead_id):
        """Load current qualification_data JSONB from leads table."""
        pass
    
    async def _save_message(self, conversation_id, lead_id, role, content, **kwargs):
        """Insert a new message row."""
        pass
    
    async def _save_qualification_data(self, lead_id, data):
        """Update leads.qualification_data and leads.status."""
        pass
    
    async def _save_lead_score(self, lead_id, agency_id, score: ScoreBreakdown):
        """Insert into lead_scores table."""
        pass
    
    async def _assign_agent(self, agency_id, specialization=None):
        """Call the assign_next_agent PostgreSQL function."""
        pass
    
    async def _schedule_follow_ups(self, lead_id, agency_id):
        """Create follow_up rows for Day 1, 3, 7."""
        pass
    
    async def _update_conversation_state(self, conversation_id):
        """Update message_count, last_message_at, status."""
        pass


# =============================================================================
# SECTION 7: DYNAMIC FOLLOW-UP QUESTION LOGIC
# =============================================================================

DYNAMIC_FOLLOW_UP_RULES = {
    # condition → (follow_up_question_key, context)
    # These are evaluated in order; first match wins
    
    "high_budget_villa": {
        "condition": lambda q: q.get("budget_max", 0) > 5_000_000 and q.get("property_type") == "villa",
        "follow_up": "Do you have a preference for plot size? Many villa communities offer plots from 5,000 to 15,000+ sqft.",
        "targets": "specific_features",
    },
    "investment_purpose": {
        "condition": lambda q: q.get("purpose") == "investment",
        "follow_up": "Are you looking for rental yield or capital appreciation? This helps me suggest the right areas.",
        "targets": "notes",
    },
    "short_timeline_ready": {
        "condition": lambda q: q.get("timeline_months", 99) <= 3,
        "follow_up": "Since you're looking to buy soon, would you prefer ready-to-move-in properties, or are you open to off-plan with attractive payment plans?",
        "targets": "specific_features",
    },
    "installment_payment": {
        "condition": lambda q: q.get("payment_method") == "installments",
        "follow_up": "Some developers offer post-handover payment plans extending 3-5 years. Is that something you'd find helpful?",
        "targets": "notes",
    },
    "location_mentioned": {
        "condition": lambda q: q.get("preferred_location") and not q.get("specific_features"),
        "follow_up": "property_search_trigger",  # Special: triggers RAG search with current criteria
        "targets": "property_recommendation",
    },
}


def get_next_dynamic_question(qualification_data: dict) -> Optional[dict]:
    """
    Evaluate dynamic follow-up rules against current qualification data.
    Returns the first matching follow-up, or None if no rules match.
    
    This is used by the system prompt builder to suggest follow-ups,
    NOT to directly control the conversation (the AI still decides).
    """
    for rule_name, rule in DYNAMIC_FOLLOW_UP_RULES.items():
        if rule["condition"](qualification_data):
            return {
                "rule": rule_name,
                "suggestion": rule["follow_up"],
                "targets": rule["targets"],
            }
    return None
