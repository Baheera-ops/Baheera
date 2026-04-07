import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --- Python enums mirror PostgreSQL enums (create_type=False) ---


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


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    LOCATION = "location"
    TEMPLATE = "template"
    INTERACTIVE = "interactive"
    SYSTEM_NOTE = "system_note"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class FollowUpStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class DocumentProcessingStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class PropertyType(str, enum.Enum):
    APARTMENT = "apartment"
    VILLA = "villa"
    TOWNHOUSE = "townhouse"
    PENTHOUSE = "penthouse"
    STUDIO = "studio"
    OFFICE = "office"
    RETAIL = "retail"
    LAND = "land"
    OTHER = "other"


def _enum(etype: type[enum.Enum], name: str):
    return Enum(
        etype,
        name=name,
        values_callable=lambda x: [e.value for e in x],
        native_enum=True,
        create_type=False,
    )


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[SubscriptionPlan] = mapped_column(_enum(SubscriptionPlan, "subscription_plan"), default=SubscriptionPlan.FREE)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(Text)
    whatsapp_phone_id: Mapped[Optional[str]] = mapped_column(String(100))
    whatsapp_access_token: Mapped[Optional[str]] = mapped_column(Text)
    meta_ad_account_id: Mapped[Optional[str]] = mapped_column(String(100))
    meta_page_id: Mapped[Optional[str]] = mapped_column(String(100))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Dubai")
    leads_this_month: Mapped[int] = mapped_column(Integer, default=0)
    leads_monthly_limit: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auth_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), default=UserRole.AGENT)
    agency_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    login_count: Mapped[int] = mapped_column(Integer, default=0)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    specialization: Mapped[Optional[str]] = mapped_column(String(100))
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), server_default=text("ARRAY['en']::character varying(50)[]")
    )
    assignment_weight: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    max_active_leads: Mapped[int] = mapped_column(Integer, default=50)
    total_leads_assigned: Mapped[int] = mapped_column(Integer, default=0)
    total_leads_converted: Mapped[int] = mapped_column(Integer, default=0)
    active_lead_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time_mins: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    last_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(100))
    contact_name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("agency_id", "slug", name="uq_developers_agency_slug"),)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[LeadSource] = mapped_column(_enum(LeadSource, "lead_source"), nullable=False)
    meta_campaign_id: Mapped[Optional[str]] = mapped_column(String(100))
    meta_adset_id: Mapped[Optional[str]] = mapped_column(String(100))
    meta_ad_id: Mapped[Optional[str]] = mapped_column(String(100))
    budget_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    budget_spent: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_leads: Mapped[int] = mapped_column(Integer, default=0)
    qualified_leads: Mapped[int] = mapped_column(Integer, default=0)
    converted_leads: Mapped[int] = mapped_column(Integer, default=0)
    avg_lead_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    cost_per_lead: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    cost_per_qualified: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    conversion_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"))
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    source: Mapped[LeadSource] = mapped_column(_enum(LeadSource, "lead_source"), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(500))
    utm_source: Mapped[Optional[str]] = mapped_column(String(255))
    utm_medium: Mapped[Optional[str]] = mapped_column(String(255))
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[LeadStatus] = mapped_column(_enum(LeadStatus, "lead_status"), default=LeadStatus.NEW)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    qualification_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    language: Mapped[Optional[str]] = mapped_column(String(10))
    qualification_turns: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    qualification_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_agent_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    qualified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class LeadScore(Base):
    __tablename__ = "lead_scores"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
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
    prompt_version: Mapped[Optional[str]] = mapped_column(String(20))
    qualification_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    conversation_length: Mapped[Optional[int]] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[LeadSource] = mapped_column(_enum(LeadSource, "lead_source"), nullable=False)
    channel_ref: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[ConversationStatus] = mapped_column(
        _enum(ConversationStatus, "conversation_status"), default=ConversationStatus.ACTIVE
    )
    current_step: Mapped[Optional[str]] = mapped_column(String(50), default="greeting")
    questions_asked: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), server_default=text("ARRAY[]::character varying(50)[]")
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    user_message_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_message_count: Mapped[int] = mapped_column(Integer, default=0)
    total_ai_tokens: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time_s: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timed_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    lead_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(_enum(MessageType, "message_type"), default=MessageType.TEXT)
    external_msg_id: Mapped[Optional[str]] = mapped_column(String(255))
    delivery_status: Mapped[Optional[DeliveryStatus]] = mapped_column(_enum(DeliveryStatus, "delivery_status"))
    ai_model: Mapped[Optional[str]] = mapped_column(String(50))
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    ai_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    function_call: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    function_result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    attachments: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    developer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("developers.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    sub_location: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(100), default="UAE")
    property_type: Mapped[PropertyType] = mapped_column(_enum(PropertyType, "property_type"), nullable=False)
    bedrooms_min: Mapped[Optional[int]] = mapped_column(Integer)
    bedrooms_max: Mapped[Optional[int]] = mapped_column(Integer)
    bathrooms_min: Mapped[Optional[int]] = mapped_column(Integer)
    bathrooms_max: Mapped[Optional[int]] = mapped_column(Integer)
    size_sqft_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    size_sqft_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    price_from: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    price_to: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    price_per_sqft: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    payment_plan: Mapped[Optional[str]] = mapped_column(Text)
    handover_date: Mapped[Optional[date]] = mapped_column(Date)
    construction_status: Mapped[Optional[str]] = mapped_column(String(50))
    amenities: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    floor_plans: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    images: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), server_default=text("ARRAY[]::character varying(50)[]"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("agency_id", "slug", name="uq_properties_agency_slug"),)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"))
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        _enum(DocumentProcessingStatus, "document_processing_status"), default=DocumentProcessingStatus.UPLOADED
    )
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeBaseEmbedding(Base):
    __tablename__ = "knowledge_base_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"))
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_category: Mapped[str] = mapped_column(String(50), nullable=False)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source: Mapped[Optional[str]] = mapped_column(String(50))
    session_id: Mapped[Optional[str]] = mapped_column(String(100))
    ip_address: Mapped[Optional[Any]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    agency_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[LeadSource] = mapped_column(_enum(LeadSource, "lead_source"), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    personalized_content: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[FollowUpStatus] = mapped_column(_enum(FollowUpStatus, "follow_up_status"), default=FollowUpStatus.PENDING)
    external_msg_id: Mapped[Optional[str]] = mapped_column(String(255))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
