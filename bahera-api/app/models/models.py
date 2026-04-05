"""
SQLAlchemy ORM models — mirrors the PostgreSQL schema exactly.
Uses mapped_column for modern SQLAlchemy 2.0 style.
"""

import enum
from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ─── Enums ───────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    AGENCY_ADMIN = "agency_admin"
    AGENT = "agent"
    DEVELOPER_USER = "developer_user"

class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"

class LeadSource(str, enum.Enum):
    META_LEAD_AD = "meta_lead_ad"
    WHATSAPP = "whatsapp"
    INSTAGRAM_DM = "instagram_dm"
    WEB_WIDGET = "web_widget"
    MANUAL = "manual"
    API = "api"

class LeadStatus(str, enum.Enum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    IN_PROGRESS = "in_progress"
    CONVERTED = "converted"
    LOST = "lost"
    ARCHIVED = "archived"

class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    WAITING_RESPONSE = "waiting_response"
    QUALIFICATION_COMPLETE = "qualification_complete"
    TIMED_OUT = "timed_out"
    HANDED_TO_AGENT = "handed_to_agent"
    CLOSED = "closed"

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"

class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"

class FollowUpStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


# ─── Models ──────────────────────────────────────────────────────────

class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), default=SubscriptionPlan.FREE
    )
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(Text)
    whatsapp_phone_id: Mapped[Optional[str]] = mapped_column(String(100))
    whatsapp_access_token: Mapped[Optional[str]] = mapped_column(Text)
    meta_ad_account_id: Mapped[Optional[str]] = mapped_column(String(100))
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Dubai")
    leads_this_month: Mapped[int] = mapped_column(Integer, default=0)
    leads_monthly_limit: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="agency")
    agents: Mapped[list["Agent"]] = relationship(back_populates="agency")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="agency")
    leads: Mapped[list["Lead"]] = relationship(back_populates="agency")


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    auth_user_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.AGENT)
    agency_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agencies.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    login_count: Mapped[int] = mapped_column(Integer, default=0)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agency: Mapped[Optional["Agency"]] = relationship(back_populates="users")
    agent_profile: Mapped[Optional["Agent"]] = relationship(back_populates="user", uselist=False)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    specialization: Mapped[Optional[str]] = mapped_column(String(100))
    languages: Mapped[Optional[list]] = mapped_column(ARRAY(String(50)), default=["en"])
    assignment_weight: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    max_active_leads: Mapped[int] = mapped_column(Integer, default=50)
    total_leads_assigned: Mapped[int] = mapped_column(Integer, default=0)
    total_leads_converted: Mapped[int] = mapped_column(Integer, default=0)
    active_lead_count: Mapped[int] = mapped_column(Integer, default=0)
    last_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agency: Mapped["Agency"] = relationship(back_populates="agents")
    user: Mapped[Optional["User"]] = relationship(back_populates="agent_profile")
    assigned_leads: Mapped[list["Lead"]] = relationship(back_populates="agent")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[LeadSource] = mapped_column(Enum(LeadSource, name="lead_source"), nullable=False)
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(100))
    budget_total: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    budget_spent: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_leads: Mapped[int] = mapped_column(Integer, default=0)
    qualified_leads: Mapped[int] = mapped_column(Integer, default=0)
    converted_leads: Mapped[int] = mapped_column(Integer, default=0)
    avg_lead_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    cost_per_lead: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    conversion_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agency: Mapped["Agency"] = relationship(back_populates="campaigns")
    leads: Mapped[list["Lead"]] = relationship(back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    agent_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    source: Mapped[LeadSource] = mapped_column(Enum(LeadSource, name="lead_source"), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status"), default=LeadStatus.NEW
    )
    score: Mapped[Optional[int]] = mapped_column(Integer)
    qualification_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    language: Mapped[Optional[str]] = mapped_column(String(10))
    qualification_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    qualified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    agency: Mapped["Agency"] = relationship(back_populates="leads")
    campaign: Mapped[Optional["Campaign"]] = relationship(back_populates="leads")
    agent: Mapped[Optional["Agent"]] = relationship(back_populates="assigned_leads")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="lead")
    scores: Mapped[list["LeadScore"]] = relationship(back_populates="lead")
    follow_ups: Mapped[list["FollowUp"]] = relationship(back_populates="lead")

    __table_args__ = (
        Index("idx_leads_agency_status", "agency_id", "status"),
        Index("idx_leads_phone_agency", "phone", "agency_id"),
    )


class LeadScore(Base):
    __tablename__ = "lead_scores"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_score: Mapped[int] = mapped_column(Integer, default=0)
    timeline_score: Mapped[int] = mapped_column(Integer, default=0)
    payment_score: Mapped[int] = mapped_column(Integer, default=0)
    location_score: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    purpose_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_adjustment: Mapped[int] = mapped_column(Integer, default=0)
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    rule_score_raw: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="scores")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[LeadSource] = mapped_column(Enum(LeadSource, name="lead_source"), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"), default=ConversationStatus.ACTIVE
    )
    current_step: Mapped[str] = mapped_column(String(50), default="greeting")
    questions_asked: Mapped[Optional[list]] = mapped_column(ARRAY(String(50)), default=[])
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    total_ai_tokens: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    lead: Mapped["Lead"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text")
    external_msg_id: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending")
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    function_call: Mapped[Optional[dict]] = mapped_column(JSONB)
    function_result: Mapped[Optional[dict]] = mapped_column(JSONB)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_messages_conversation", "conversation_id", "created_at"),
    )


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    developer_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    bedrooms_min: Mapped[Optional[int]] = mapped_column(Integer)
    bedrooms_max: Mapped[Optional[int]] = mapped_column(Integer)
    price_from: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    price_to: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    payment_plan: Mapped[Optional[str]] = mapped_column(Text)
    handover_date: Mapped[Optional[date]] = mapped_column(Date)
    amenities: Mapped[dict] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    processing_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_processing_status"), default=DocumentStatus.UPLOADED
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class KnowledgeBaseEmbedding(Base):
    __tablename__ = "knowledge_base_embeddings"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=False)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_category: Mapped[str] = mapped_column(String(50), nullable=False)
    lead_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True))
    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True))
    agent_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True))
    event_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_analytics_agency_time", "agency_id", "occurred_at"),
        Index("idx_analytics_type", "agency_id", "event_type", "occurred_at"),
    )


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agency_id: Mapped[UUID] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[LeadSource] = mapped_column(Enum(LeadSource, name="lead_source"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[FollowUpStatus] = mapped_column(
        Enum(FollowUpStatus, name="follow_up_status"), default=FollowUpStatus.PENDING
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="follow_ups")
