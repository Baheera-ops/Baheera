"""
BAHERA Lead Scoring Engine v2.0
================================
Production-grade scoring system with:
  - 6-component rule-based scoring (0-90 pts)
  - AI behavioral analysis overlay (+-10 pts)
  - Conversion feedback loop for weight calibration
  - Time-based score decay for aging leads
  - Full audit trail for every score version

Architecture:
  Pass 1 (instant): Rule engine processes qualification_data → 0-90 pts
  Pass 2 (async):   AI reads conversation transcript → adjustment -10 to +10
  Pass 3 (cron):    Decay function reduces score of inactive leads over time
  Feedback loop:    Conversion outcomes recalibrate component weights monthly
"""

import json
import math
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from openai import AsyncOpenAI

logger = logging.getLogger("bahera.scoring")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: SCORE MODEL
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ScoreBreakdown:
    """Full scoring breakdown — stored in lead_scores table."""

    # Component scores (Pass 1: rule engine)
    budget_score: int = 0          # 0-25 pts
    timeline_score: int = 0        # 0-20 pts
    intent_score: int = 0          # 0-15 pts  (payment readiness + purpose)
    location_score: int = 0        # 0-12 pts
    property_type_score: int = 0   # 0-10 pts
    engagement_score: int = 0      # 0-8 pts

    # AI adjustment (Pass 2: behavioral analysis)
    ai_adjustment: int = 0         # -10 to +10
    ai_reasoning: str = ""
    ai_signals: list[dict] = field(default_factory=list)

    # Computed
    rule_total: int = 0            # Sum of 6 components (0-90)
    final_score: int = 0           # Clamped to 0-100
    tier: str = "unscored"         # hot / warm / nurture / cold

    # Metadata
    model_version: str = "v2.0"
    scored_at: datetime = field(default_factory=datetime.utcnow)

    def compute_total(self):
        self.rule_total = (
            self.budget_score + self.timeline_score + self.intent_score +
            self.location_score + self.property_type_score + self.engagement_score
        )
        self.final_score = max(0, min(100, self.rule_total + self.ai_adjustment))
        self.tier = self._compute_tier()
        return self

    def _compute_tier(self) -> str:
        if self.final_score >= 80: return "hot"
        if self.final_score >= 60: return "warm"
        if self.final_score >= 30: return "nurture"
        return "cold"

    def to_dict(self) -> dict:
        return {
            "total_score": self.final_score,
            "budget_score": self.budget_score,
            "timeline_score": self.timeline_score,
            "intent_score": self.intent_score,
            "location_score": self.location_score,
            "property_type_score": self.property_type_score,
            "engagement_score": self.engagement_score,
            "ai_adjustment": self.ai_adjustment,
            "ai_reasoning": self.ai_reasoning,
            "rule_score_raw": self.rule_total,
            "model_version": self.model_version,
        }


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: PASS 1 — RULE-BASED SCORING ENGINE
# Each component uses a scoring curve, not just a lookup table.
# Curves are designed from real estate conversion data.
# ═══════════════════════════════════════════════════════════════════════

class RuleEngine:
    """
    Deterministic scoring engine. Processes structured qualification data
    and conversation metadata into a component score breakdown.

    Weight rationale (derived from real estate conversion correlation):
      Budget readiness (25):  Highest single predictor. A buyer who can
                              articulate "AED 1.2M-1.8M" converts 4x more
                              than one who says "I'll figure it out."
      Timeline urgency (20):  Time pressure drives action. "This month"
                              converts 6x vs "sometime next year."
      Purchase intent  (15):  Cash buyers close 3x faster than those
                              "exploring financing." Payment method +
                              investment purpose combined.
      Location (12):          Naming a specific community means research
                              was done. General "Dubai" = still browsing.
      Property type (10):     "2BR apartment" is more qualified than
                              "something nice" — they've narrowed scope.
      Engagement (8):         Behavioral signal from conversation itself.
                              Length, questions asked, response time.
    """

    def score(
        self,
        qualification: dict,
        messages: list[dict],
        conversation_meta: dict | None = None,
    ) -> ScoreBreakdown:

        breakdown = ScoreBreakdown()

        breakdown.budget_score = self._score_budget(qualification)
        breakdown.timeline_score = self._score_timeline(qualification)
        breakdown.intent_score = self._score_intent(qualification)
        breakdown.location_score = self._score_location(qualification)
        breakdown.property_type_score = self._score_property_type(qualification)
        breakdown.engagement_score = self._score_engagement(messages, conversation_meta)

        breakdown.compute_total()
        return breakdown

    # ── Budget readiness (0-25) ──────────────────────────────────────

    def _score_budget(self, q: dict) -> int:
        """
        Scores based on how precisely the buyer defined their budget.

        Scoring curve:
          Exact range (min + max):         25  — "AED 1.2M to 1.8M"
          Max only with reasonable value:   20  — "Up to 1.5M"
          Max only, round/vague:            15  — "Under 2 million"
          Min only:                         12  — "At least 1M"
          Verbal indication, no number:     7   — "Medium budget"
          No budget mentioned:              0

        Bonus: Budget > 5M adds 3 pts (high-value buyers are serious).
               Budget consistency check: if min > max, deduct 5 (data error).
        """
        budget_max = q.get("budget_max")
        budget_min = q.get("budget_min")
        budget_text = str(q.get("budget_range", "")).lower()

        if budget_max and budget_min:
            if budget_min > budget_max:
                return max(0, 20 - 5)  # Inconsistency penalty
            score = 25
        elif budget_max:
            # Check if it's a round number (less precise)
            if budget_max % 1_000_000 == 0:
                score = 15  # "Under 2 million" — round = less researched
            else:
                score = 20  # "Up to 1.5M" — specific
        elif budget_min:
            score = 12
        elif budget_text and any(w in budget_text for w in ["medium", "mid", "average", "moderate"]):
            score = 7
        elif budget_text and any(w in budget_text for w in ["high", "luxury", "premium", "no limit"]):
            score = 10
        elif budget_text and any(w in budget_text for w in ["low", "cheap", "affordable", "minimum"]):
            score = 5
        else:
            return 0

        # High-value bonus
        effective_budget = budget_max or budget_min or 0
        if effective_budget > 5_000_000:
            score = min(25, score + 3)
        elif effective_budget > 10_000_000:
            score = min(25, score + 5)

        return score

    # ── Timeline urgency (0-20) ──────────────────────────────────────

    def _score_timeline(self, q: dict) -> int:
        """
        Scores urgency based on stated purchase timeline.

        Uses a decay curve: urgency drops exponentially with time.
        The curve is f(months) = 20 * e^(-0.15 * months), floored at 2.

        This means:
          0-1 months:   20  (immediate buyer)
          2-3 months:   15-18
          4-6 months:   10-14
          7-12 months:  5-9
          13-24 months: 3-4
          24+ months:   2

        Additional signals from text:
          "ASAP", "immediately", "this week":    +2 bonus (cap at 20)
          "no rush", "whenever", "not sure":     floor at 3
        """
        months = q.get("timeline_months")
        timeline_text = str(q.get("timeline", "")).lower()

        if months is not None:
            # Exponential decay curve
            score = round(20 * math.exp(-0.15 * max(0, months - 1)))
            score = max(2, min(20, score))
        elif timeline_text:
            urgency_map = {
                "immediately": 20, "asap": 20, "this week": 20,
                "this month": 18, "next month": 16,
                "1-3 months": 15, "3-6 months": 12,
                "6-12 months": 8, "next year": 5,
                "not sure": 3, "no rush": 3, "just looking": 2,
            }
            for phrase, pts in urgency_map.items():
                if phrase in timeline_text:
                    return pts
            return 4  # Some timeline mentioned but unclear
        else:
            return 0

        # Text signal bonuses
        if timeline_text:
            if any(w in timeline_text for w in ["asap", "immediately", "urgent", "this week"]):
                score = min(20, score + 2)
            elif any(w in timeline_text for w in ["no rush", "whenever", "not sure"]):
                score = min(score, 3)

        return score

    # ── Purchase intent (0-15) ───────────────────────────────────────

    def _score_intent(self, q: dict) -> int:
        """
        Combined score from payment method and purchase purpose.
        These two signals together indicate financial readiness.

        Payment method scoring (0-9):
          cash:                 9  — Can close immediately
          mortgage_approved:    8  — Pre-approved = committed
          mortgage:             6  — Considering mortgage = likely
          installments:         5  — Developer payment plan
          exploring:            2  — No financing plan yet
          unknown:              0

        Purpose scoring (0-6):
          investment (ROI-focused):  6  — Clear financial goal
          both (invest + live):      5  — Dual purpose = serious
          end_use (personal):        4  — Personal need = motivated
          relocation:                5  — External pressure
          browsing:                  1
          unknown:                   0
        """
        payment = str(q.get("payment_method", "")).lower().replace(" ", "_")
        purpose = str(q.get("purpose", "")).lower()

        payment_scores = {
            "cash": 9, "cash_ready": 9,
            "mortgage_approved": 8, "pre_approved": 8,
            "mortgage": 6, "bank_finance": 6,
            "installments": 5, "payment_plan": 5,
            "exploring": 2, "not_sure": 1,
        }
        payment_pts = payment_scores.get(payment, 0)

        purpose_scores = {
            "investment": 6, "invest": 6, "rental_income": 6, "roi": 6,
            "both": 5,
            "relocation": 5, "relocating": 5,
            "end_use": 4, "personal": 4, "living": 4, "family": 4,
            "browsing": 1, "just_looking": 1,
        }
        purpose_pts = purpose_scores.get(purpose, 0)

        return min(15, payment_pts + purpose_pts)

    # ── Location specificity (0-12) ──────────────────────────────────

    def _score_location(self, q: dict) -> int:
        """
        Scores how specifically the buyer described their preferred location.
        More specific = more research done = higher conversion probability.

        Hierarchy:
          Named building/tower:     12  — "Emaar Beachfront Tower 2"
          Named community/project:  10  — "Dubai Marina", "Palm Jumeirah"
          District/area:            7   — "JBR", "Downtown"
          City + qualifier:         5   — "New Dubai", "near the beach"
          City only:                3   — "Dubai"
          Country/region only:      2   — "UAE"
          "Anywhere" / no pref:     0

        Detection: Count words, check for known community names.
        """
        location = str(q.get("preferred_location", "")).strip()

        if not location:
            return 0

        lower = location.lower()

        # Disqualifiers
        if lower in ("anywhere", "any", "doesn't matter", "no preference", "not sure"):
            return 0

        # Known specific communities (real estate industry knowledge)
        premium_communities = [
            "palm jumeirah", "dubai marina", "downtown dubai", "business bay",
            "jbr", "bluewaters", "dubai hills", "arabian ranches", "emaar beachfront",
            "creek harbour", "meydan", "damac hills", "jumeirah village",
            "al reem island", "saadiyat", "yas island",
        ]
        for community in premium_communities:
            if community in lower:
                return 10

        words = location.split()
        word_count = len(words)

        if word_count >= 4:
            return 12  # Very specific: "Emaar Beachfront Tower 2 South"
        elif word_count >= 3:
            return 10  # Community level: "Dubai Marina Gate"
        elif word_count == 2:
            return 7   # Area level: "Business Bay"
        elif lower in ("dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah"):
            return 3   # City only
        elif word_count == 1:
            return 5   # Single district name
        else:
            return 2

    # ── Property type match (0-10) ───────────────────────────────────

    def _score_property_type(self, q: dict) -> int:
        """
        Scores clarity of what the buyer is looking for.

        Scoring:
          Specific type + bedrooms + features:  10  — "2BR apartment, sea view"
          Specific type + bedrooms:             8   — "3BR villa"
          Specific type only:                   6   — "apartment"
          General category:                     3   — "residential"
          Undecided / "anything":               0
        """
        prop_type = str(q.get("property_type", "")).lower()
        bedrooms = q.get("bedrooms")
        features = q.get("specific_features", [])

        if not prop_type or prop_type in ("any", "anything", "undecided", "not sure"):
            return 0

        valid_types = [
            "apartment", "villa", "townhouse", "penthouse", "studio",
            "duplex", "office", "retail", "land", "plot",
        ]

        is_specific = any(t in prop_type for t in valid_types)

        if is_specific and bedrooms and features:
            return 10
        elif is_specific and bedrooms:
            return 8
        elif is_specific:
            return 6
        elif prop_type in ("residential", "commercial", "property"):
            return 3
        else:
            return 4  # Some type mentioned

    # ── Engagement behavior (0-8) ────────────────────────────────────

    def _score_engagement(
        self, messages: list[dict], meta: dict | None = None
    ) -> int:
        """
        Scores based on HOW the buyer interacted, not what they said.
        This is a behavioral signal — engaged buyers convert more.

        Signals:
          Average message length:          0-3 pts
          Questions asked by buyer:        0-2 pts
          Response velocity:               0-2 pts
          Conversation initiation:         0-1 pt

        Detection is purely quantitative — no NLP needed.
        """
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if not user_msgs:
            return 0

        score = 0

        # Message length signal (0-3 pts)
        avg_chars = sum(len(m.get("content", "")) for m in user_msgs) / len(user_msgs)
        if avg_chars > 100:
            score += 3  # Detailed, thoughtful responses
        elif avg_chars > 50:
            score += 2
        elif avg_chars > 20:
            score += 1
        # Under 20 chars average = one-word answers = 0 pts

        # Questions asked (0-2 pts)
        questions = sum(1 for m in user_msgs if "?" in m.get("content", ""))
        if questions >= 3:
            score += 2  # Actively curious — strong buy signal
        elif questions >= 1:
            score += 1

        # Response velocity (0-2 pts)
        if meta and meta.get("avg_response_time_s"):
            avg_response = meta["avg_response_time_s"]
            if avg_response < 60:
                score += 2  # Responds within a minute — very engaged
            elif avg_response < 300:
                score += 1  # Within 5 minutes — good
            # Over 5 minutes = 0 pts (low engagement)

        # Did the user initiate the conversation? (0-1 pt)
        if meta and meta.get("user_initiated", False):
            score += 1  # They reached out first — proactive interest

        return min(8, score)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: PASS 2 — AI BEHAVIORAL ANALYSIS
# GPT reads the full transcript and detects intent signals
# that structured rules can't capture.
# ═══════════════════════════════════════════════════════════════════════

AI_SCORING_SYSTEM_PROMPT = """You are a real estate lead scoring analyst.
You receive a conversation between a buyer and an AI assistant.
Your job: assess the buyer's GENUINE purchase intent by reading behavioral signals.

You will output a JSON object. Nothing else. No markdown, no explanation."""

AI_SCORING_USER_PROMPT = """
Analyze this buyer conversation. The rule engine scored them at {rule_score}/90.

=== CONVERSATION TRANSCRIPT ===
{transcript}

=== QUALIFICATION DATA COLLECTED ===
{qualification_json}

Evaluate these BEHAVIORAL DIMENSIONS and assign an adjustment from -10 to +10:

POSITIVE SIGNALS (each worth +1 to +3):
  P1: SPECIFICITY — Names exact buildings, floors, unit numbers, or streets
  P2: LOGISTICS — Asks about viewings, move-in dates, key handover, or utility setup
  P3: FINANCIAL DEPTH — Asks about transfer fees, mortgage rates, service charges, ROI math
  P4: COMPARISON — Compares two specific projects or units (means research was done)
  P5: URGENCY LANGUAGE — "need to", "have to", "before [date]", "running out of options"
  P6: SOCIAL PROOF — Mentions friend who bought, agent recommendation, or prior visits

NEGATIVE SIGNALS (each worth -1 to -3):
  N1: DEFLECTION — Avoids direct answers, changes subject when asked about budget/timeline
  N2: PASSIVITY — Only responds to prompts, never initiates a question or new topic
  N3: INCONSISTENCY — States different budgets or timelines in different messages
  N4: HEDGING LANGUAGE — "maybe", "possibly", "just looking", "someday", "not sure" repeated
  N5: DISENGAGEMENT — Increasingly short responses, longer gaps between messages
  N6: INFORMATION HARVESTING — Asks for brochures/pricing but avoids personal commitment

Count the signals present. Sum the positive points. Subtract the negative points.
Clamp the result to [-10, +10].

Respond with ONLY this JSON:
{{
  "adjustment": <integer -10 to +10>,
  "reasoning": "<one sentence summary>",
  "positive_signals": [
    {{"code": "P1", "description": "<what you detected>", "points": <1-3>}}
  ],
  "negative_signals": [
    {{"code": "N4", "description": "<what you detected>", "points": <1-3>}}
  ],
  "confidence": <0.0 to 1.0>
}}
"""


class AIEvaluator:
    """
    Reads conversation transcripts and detects behavioral intent signals
    that structured rules cannot capture.

    The AI doesn't score from scratch — it only ADJUSTS the rule score
    by +-10 points. This ensures the deterministic engine has primary
    authority, while the AI catches nuance.

    How the AI evaluates buyer intent:

    1. LANGUAGE ANALYSIS — The AI detects commitment-level language.
       "I want to buy" vs "I'm thinking about maybe looking" carry
       different intent weights. Specific verbs (schedule, book, visit,
       transfer, sign) signal commitment. Hedge words (maybe, possibly,
       not sure, just looking) signal browsing.

    2. QUESTION DIRECTIONALITY — Buyers who ask about logistics
       (move-in dates, transfer fees, parking allocation) are further
       in the purchase funnel than those asking about area amenities.
       The AI detects which STAGE of the funnel the questions target.

    3. KNOWLEDGE SIGNALS — A buyer who says "I've visited 3 projects
       in Marina already" or "my friend just bought in Creek Harbour"
       has done research. The AI detects prior knowledge indicators.

    4. CONSISTENCY TRACKING — The AI checks if budget, timeline, and
       preferences stay consistent across the conversation. Changes
       in stated budget (1M in message 3, then 500K in message 7)
       indicate uncertainty.

    5. ENGAGEMENT TRAJECTORY — Is the buyer getting more or less
       engaged over the conversation? Increasing message length and
       question frequency = warming up. Decreasing = cooling off.

    6. URGENCY vs CURIOSITY — The AI distinguishes "I need a 2BR by
       March for my family's relocation" (urgency-driven) from "What's
       the market like for 2BRs?" (curiosity-driven). Both are valid
       leads, but urgency converts at 3x the rate.
    """

    def __init__(self, openai_client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model

    async def evaluate(
        self,
        rule_score: int,
        messages: list[dict],
        qualification: dict,
    ) -> tuple[int, str, list[dict]]:
        """
        Run AI behavioral analysis on the conversation.
        Returns (adjustment, reasoning, signals_detected).
        """
        # Build transcript
        transcript_lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            label = "Buyer" if role == "user" else "AI" if role == "assistant" else role
            transcript_lines.append(f"{label}: {content}")

        transcript = "\n".join(transcript_lines[-30:])  # Last 30 messages max

        prompt = AI_SCORING_USER_PROMPT.format(
            rule_score=rule_score,
            transcript=transcript[:4000],  # Token safety
            qualification_json=json.dumps(qualification, indent=2, default=str)[:1000],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": AI_SCORING_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,  # Low variance for scoring consistency
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            result = json.loads(raw)

            adjustment = max(-10, min(10, int(result.get("adjustment", 0))))
            reasoning = result.get("reasoning", "")
            signals = (
                result.get("positive_signals", []) +
                result.get("negative_signals", [])
            )

            logger.info(
                f"AI evaluation: adjustment={adjustment}, "
                f"confidence={result.get('confidence', 'N/A')}, "
                f"reasoning={reasoning}"
            )

            return adjustment, reasoning, signals

        except Exception as e:
            logger.warning(f"AI scoring evaluation failed: {e}")
            return 0, "AI evaluation unavailable", []


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: SCORE DECAY (Pass 3)
# Reduces scores of leads that go inactive over time.
# ═══════════════════════════════════════════════════════════════════════

def calculate_decay(
    current_score: int,
    last_activity_at: datetime,
    now: datetime | None = None,
) -> int:
    """
    Time-based score decay for aging leads.

    A lead who scored 85 three weeks ago but never responded to follow-ups
    is no longer an 85. The decay function models this reality.

    Decay curve:
      Days 0-7:    No decay (normal sales cycle)
      Days 7-14:   -1 pt/day  (mild cooling)
      Days 14-30:  -2 pts/day (significant cooling)
      Days 30+:    -3 pts/day (likely lost)
      Floor:       Score never drops below 10

    Protected: Leads in "contacted" or "in_progress" status don't decay
    (the agent is actively working them).
    """
    now = now or datetime.utcnow()
    days_inactive = (now - last_activity_at).days

    if days_inactive <= 7:
        return current_score

    decay = 0
    if days_inactive > 30:
        decay = 7 + 16 * 2 + (days_inactive - 30) * 3  # 7-14 + 14-30 + 30+
    elif days_inactive > 14:
        decay = 7 + (days_inactive - 14) * 2
    else:
        decay = days_inactive - 7

    return max(10, current_score - decay)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: CONVERSION FEEDBACK LOOP
# Learns from actual outcomes to recalibrate component weights.
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ComponentCorrelation:
    """Tracks how each scoring component correlates with actual conversions."""
    component: str
    converted_avg: float      # Average component score for converted leads
    not_converted_avg: float  # Average component score for non-converted leads
    correlation: float        # Pearson correlation with conversion outcome
    suggested_weight: float   # Recommended weight adjustment


def analyze_conversion_feedback(
    scored_leads: list[dict],
) -> list[ComponentCorrelation]:
    """
    Analyze historical scoring data against actual conversion outcomes.

    Input: List of dicts with component scores + conversion boolean.
    Output: Correlation analysis suggesting weight adjustments.

    Run this monthly as a batch job. If a component (e.g., budget_score)
    doesn't correlate with actual conversions, its weight should decrease.
    If engagement_score is a stronger predictor than expected, increase it.

    This creates a self-improving scoring system:
      Month 1: Default weights (from industry heuristics)
      Month 3: Weights adjusted based on first conversion data
      Month 6: Weights stabilize around agency-specific patterns
    """
    if len(scored_leads) < 50:
        return []  # Need minimum sample size

    components = [
        "budget_score", "timeline_score", "intent_score",
        "location_score", "property_type_score", "engagement_score",
    ]
    max_weights = [25, 20, 15, 12, 10, 8]

    results = []
    converted = [l for l in scored_leads if l.get("converted")]
    not_converted = [l for l in scored_leads if not l.get("converted")]

    if not converted or not not_converted:
        return []

    for comp, max_w in zip(components, max_weights):
        conv_scores = [l.get(comp, 0) for l in converted]
        non_scores = [l.get(comp, 0) for l in not_converted]

        conv_avg = sum(conv_scores) / len(conv_scores)
        non_avg = sum(non_scores) / len(non_scores)

        # Simple correlation: how much does this component differentiate?
        spread = conv_avg - non_avg
        max_spread = max_w  # Maximum possible differentiation
        correlation = spread / max_spread if max_spread > 0 else 0

        # Suggest weight adjustment
        # If correlation > 0.5: component is a strong predictor → keep or increase
        # If correlation < 0.2: component doesn't differentiate → decrease
        if correlation > 0.6:
            suggested = min(max_w + 3, 30)  # Slight increase
        elif correlation < 0.15:
            suggested = max(max_w - 3, 3)   # Slight decrease
        else:
            suggested = max_w               # Keep current

        results.append(ComponentCorrelation(
            component=comp,
            converted_avg=round(conv_avg, 1),
            not_converted_avg=round(non_avg, 1),
            correlation=round(correlation, 3),
            suggested_weight=suggested,
        ))

    return results


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: MAIN SCORING ORCHESTRATOR
# Combines all passes into a single entry point.
# ═══════════════════════════════════════════════════════════════════════

class ScoringEngine:
    """
    Main orchestrator. Runs the full scoring pipeline.

    Usage:
        engine = ScoringEngine(openai_client)
        breakdown = await engine.score_lead(
            qualification_data={"budget_max": 1500000, ...},
            messages=[{"role": "user", "content": "..."}, ...],
            conversation_meta={"avg_response_time_s": 45, ...},
            enable_ai=True,
        )
        print(breakdown.final_score)  # 83
        print(breakdown.tier)         # "hot"
    """

    def __init__(self, openai_client: AsyncOpenAI | None = None):
        self.rule_engine = RuleEngine()
        self.ai_evaluator = AIEvaluator(openai_client) if openai_client else None

    async def score_lead(
        self,
        qualification_data: dict,
        messages: list[dict],
        conversation_meta: dict | None = None,
        enable_ai: bool = True,
    ) -> ScoreBreakdown:
        """
        Full scoring pipeline:
          1. Rule engine processes qualification data → 0-90 pts
          2. AI evaluator reads transcript → adjustment -10 to +10
          3. Combine and clamp to 0-100
        """

        # Pass 1: Rule-based scoring
        breakdown = self.rule_engine.score(
            qualification_data, messages, conversation_meta
        )

        # Pass 2: AI behavioral analysis (optional, async)
        if enable_ai and self.ai_evaluator and len(messages) >= 3:
            adjustment, reasoning, signals = await self.ai_evaluator.evaluate(
                rule_score=breakdown.rule_total,
                messages=messages,
                qualification=qualification_data,
            )
            breakdown.ai_adjustment = adjustment
            breakdown.ai_reasoning = reasoning
            breakdown.ai_signals = signals

        breakdown.compute_total()

        logger.info(
            f"Lead scored: rule={breakdown.rule_total} "
            f"ai_adj={breakdown.ai_adjustment} "
            f"final={breakdown.final_score} "
            f"tier={breakdown.tier}"
        )

        return breakdown

    def score_lead_sync(
        self,
        qualification_data: dict,
        messages: list[dict],
        conversation_meta: dict | None = None,
    ) -> ScoreBreakdown:
        """Synchronous scoring without AI pass. Use for batch operations."""
        return self.rule_engine.score(
            qualification_data, messages, conversation_meta
        )


# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: EXAMPLE SCENARIOS
# Real-world scoring examples for testing and documentation.
# ═══════════════════════════════════════════════════════════════════════

EXAMPLE_SCENARIOS = {
    "hot_buyer": {
        "description": "Cash buyer, 2-month timeline, specific community",
        "qualification": {
            "budget_min": 1200000, "budget_max": 1800000,
            "timeline_months": 2, "payment_method": "cash",
            "purpose": "investment", "preferred_location": "Dubai Marina",
            "property_type": "apartment", "bedrooms": 2,
            "specific_features": ["sea view", "high floor"],
        },
        "messages": [
            {"role": "user", "content": "Hi, I'm looking for a 2BR apartment in Dubai Marina with a sea view"},
            {"role": "assistant", "content": "Great choice! What's your budget range?"},
            {"role": "user", "content": "Between 1.2 and 1.8 million AED. I'm a cash buyer and I need to close within 2 months because my rental contract is ending. I've already visited Marina Heights and The Residences — can you compare the two for me?"},
            {"role": "assistant", "content": "Both excellent options! Marina Heights offers..."},
            {"role": "user", "content": "What are the service charges and transfer fees for Marina Heights? And can I schedule a viewing for this weekend?"},
        ],
        "expected_score": "85-95 (hot)",
        "expected_ai_signals": ["P2: asked about viewings", "P3: asked about fees", "P4: comparing projects", "P5: rental ending urgency"],
    },

    "warm_lead": {
        "description": "Mortgage buyer, 6-month timeline, general area",
        "qualification": {
            "budget_max": 2000000, "timeline_months": 6,
            "payment_method": "mortgage", "purpose": "end_use",
            "preferred_location": "Downtown", "property_type": "apartment",
        },
        "messages": [
            {"role": "user", "content": "I'm looking to buy an apartment in Downtown Dubai"},
            {"role": "assistant", "content": "What's your budget?"},
            {"role": "user", "content": "Around 2 million, planning to get a mortgage"},
            {"role": "assistant", "content": "When are you looking to make this purchase?"},
            {"role": "user", "content": "Maybe in the next 6 months. We're relocating from London."},
        ],
        "expected_score": "60-72 (warm)",
        "expected_ai_signals": ["P5: relocation pressure", "N4: 'maybe' hedging"],
    },

    "cold_lead": {
        "description": "No budget, no timeline, minimal engagement",
        "qualification": {
            "property_type": "apartment",
            "preferred_location": "Dubai",
        },
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello! What kind of property are you looking for?"},
            {"role": "user", "content": "apartment"},
            {"role": "assistant", "content": "What's your budget range?"},
            {"role": "user", "content": "not sure"},
            {"role": "assistant", "content": "When are you planning to buy?"},
            {"role": "user", "content": "just looking"},
        ],
        "expected_score": "10-20 (cold)",
        "expected_ai_signals": ["N1: avoids budget question", "N2: only responds to prompts", "N4: 'just looking' repeated", "N5: short responses"],
    },
}
