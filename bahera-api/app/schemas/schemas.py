"""
Pydantic schemas for request validation and response serialization.
Organized by domain module.
"""

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ═══════════════════════════════════════════════════════════════════════
# SHARED
# ═══════════════════════════════════════════════════════════════════════

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)

class PaginatedResponse(BaseModel):
    data: list[Any]
    pagination: dict

    @staticmethod
    def build(data: list, total: int, page: int, per_page: int) -> "PaginatedResponse":
        return PaginatedResponse(
            data=data,
            pagination={
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page,
            },
        )


# ═══════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=255)
    agency_name: str = Field(min_length=2, max_length=255)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"

class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    agency_id: Optional[UUID]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════
# LEADS
# ═══════════════════════════════════════════════════════════════════════

class LeadCreate(BaseModel):
    name: Optional[str] = None
    phone: str = Field(min_length=5, max_length=50)
    email: Optional[EmailStr] = None
    source: str = "manual"
    campaign_id: Optional[UUID] = None
    source_ref: Optional[str] = None

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    agent_id: Optional[UUID] = None
    qualification_data: Optional[dict] = None

class LeadResponse(BaseModel):
    id: UUID
    agency_id: UUID
    name: Optional[str]
    phone: str
    email: Optional[str]
    source: str
    status: str
    score: Optional[int]
    qualification_data: dict
    language: Optional[str]
    agent_id: Optional[UUID]
    campaign_id: Optional[UUID]
    created_at: datetime
    qualified_at: Optional[datetime]

    class Config:
        from_attributes = True

class LeadDetailResponse(LeadResponse):
    conversations: list["ConversationResponse"] = []
    scores: list["LeadScoreResponse"] = []
    agent: Optional["AgentResponse"] = None

class LeadScoreResponse(BaseModel):
    id: UUID
    total_score: int
    budget_score: int
    timeline_score: int
    payment_score: int
    location_score: int
    engagement_score: int
    purpose_score: int
    ai_adjustment: int
    ai_reasoning: Optional[str]
    version: int
    is_current: bool
    scored_at: datetime

    class Config:
        from_attributes = True

class LeadFilters(BaseModel):
    status: Optional[str] = None
    source: Optional[str] = None
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    agent_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# AGENTS
# ═══════════════════════════════════════════════════════════════════════

class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    specialization: Optional[str] = None
    assignment_weight: int = Field(default=5, ge=1, le=10)

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    specialization: Optional[str] = None
    assignment_weight: Optional[int] = Field(default=None, ge=1, le=10)
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None

class AgentResponse(BaseModel):
    id: UUID
    agency_id: UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    specialization: Optional[str]
    assignment_weight: int
    is_active: bool
    is_available: bool
    total_leads_assigned: int
    total_leads_converted: int
    active_lead_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════
# CAMPAIGNS
# ═══════════════════════════════════════════════════════════════════════

class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    source: str = "meta_lead_ad"
    meta_campaign_id: Optional[str] = None
    budget_total: Optional[float] = None
    currency: str = "AED"
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    budget_total: Optional[float] = None
    budget_spent: Optional[float] = None
    is_active: Optional[bool] = None
    end_date: Optional[date] = None

class CampaignResponse(BaseModel):
    id: UUID
    agency_id: UUID
    name: str
    source: str
    budget_total: Optional[float]
    budget_spent: float
    currency: str
    is_active: bool
    total_leads: int
    qualified_leads: int
    converted_leads: int
    avg_lead_score: Optional[float]
    cost_per_lead: Optional[float]
    conversion_rate: Optional[float]
    start_date: Optional[date]
    end_date: Optional[date]
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════
# CHATBOT
# ═══════════════════════════════════════════════════════════════════════

class ChatbotMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    channel: str = "web_widget"

class ChatbotResponse(BaseModel):
    response: str
    lead_id: UUID
    conversation_id: UUID
    qualification_complete: bool = False
    score: Optional[int] = None
    assigned_agent: Optional[str] = None

class ConversationResponse(BaseModel):
    id: UUID
    lead_id: UUID
    channel: str
    status: str
    message_count: int
    started_at: datetime
    last_message_at: Optional[datetime]

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    message_type: str
    created_at: datetime

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════
# WEBHOOKS
# ═══════════════════════════════════════════════════════════════════════

class MetaWebhookVerify(BaseModel):
    hub_mode: str = Field(alias="hub.mode")
    hub_challenge: str = Field(alias="hub.challenge")
    hub_verify_token: str = Field(alias="hub.verify_token")

class WidgetLeadCapture(BaseModel):
    org_id: UUID
    name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    message: str
    page_url: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════════════════════════════════════════

class AnalyticsOverview(BaseModel):
    leads_today: int
    leads_this_week: int
    leads_this_month: int
    avg_score: Optional[float]
    hot_leads: int
    conversion_rate: Optional[float]
    total_conversions: int

class CampaignAnalytics(BaseModel):
    campaign_id: UUID
    campaign_name: str
    total_leads: int
    qualified_leads: int
    converted_leads: int
    avg_score: Optional[float]
    cost_per_lead: Optional[float]
    cost_per_qualified: Optional[float]

class ScoreDistribution(BaseModel):
    hot: int      # 80-100
    warm: int     # 60-79
    nurture: int  # 30-59
    cold: int     # 0-29
    unscored: int
