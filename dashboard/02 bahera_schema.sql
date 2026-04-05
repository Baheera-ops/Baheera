-- ============================================================================
-- BAHERA — Full PostgreSQL Database Schema
-- AI-Powered Real Estate Lead Generation & Qualification Platform
-- ============================================================================
-- Target: Supabase (PostgreSQL 15+ with pgvector extension)
-- Multi-tenant via agency_id + Row Level Security
-- ============================================================================

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";      -- UUID generation
CREATE EXTENSION IF NOT EXISTS "vector";          -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- Trigram index for text search


-- ============================================================================
-- CUSTOM TYPES (enums for type safety + query performance)
-- ============================================================================

CREATE TYPE user_role AS ENUM (
    'super_admin',       -- Bahera platform admin
    'agency_admin',      -- Agency owner / manager
    'agent',             -- Sales agent
    'developer_user'     -- Property developer (upload access only)
);

CREATE TYPE subscription_plan AS ENUM (
    'free',              -- Trial: 50 leads/month, 1 agent
    'starter',           -- $99/mo: 500 leads/month, 5 agents
    'professional',      -- $249/mo: 2000 leads/month, 20 agents
    'enterprise'         -- Custom
);

CREATE TYPE lead_source AS ENUM (
    'meta_lead_ad',      -- Facebook/Instagram Lead Ad form
    'whatsapp',          -- WhatsApp Business inbound
    'instagram_dm',      -- Instagram Direct Message
    'web_widget',        -- Website chat widget
    'manual',            -- Manually entered by agent
    'api'                -- Imported via API
);

CREATE TYPE lead_status AS ENUM (
    'new',               -- Just captured, no AI interaction yet
    'qualifying',        -- AI chatbot is actively qualifying
    'qualified',         -- Qualification complete, score assigned
    'contacted',         -- Agent has made first contact
    'in_progress',       -- Active deal in progress
    'converted',         -- Deal closed
    'lost',              -- Lead lost / not interested
    'archived'           -- Old lead, auto-archived
);

CREATE TYPE conversation_status AS ENUM (
    'active',            -- Ongoing conversation
    'waiting_response',  -- AI sent message, waiting for lead reply
    'qualification_complete',  -- All data collected
    'timed_out',         -- Lead stopped responding
    'handed_to_agent',   -- Transferred to human agent
    'closed'             -- Conversation ended
);

CREATE TYPE message_role AS ENUM (
    'user',              -- Message from the lead
    'assistant',         -- AI chatbot response
    'system',            -- System note (assignment, score, etc.)
    'agent'              -- Human agent message
);

CREATE TYPE message_type AS ENUM (
    'text',
    'image',
    'document',
    'location',
    'template',          -- WhatsApp template message
    'interactive',       -- WhatsApp interactive (buttons/list)
    'system_note'
);

CREATE TYPE delivery_status AS ENUM (
    'pending',
    'sent',
    'delivered',
    'read',
    'failed'
);

CREATE TYPE follow_up_status AS ENUM (
    'pending',
    'sent',
    'delivered',
    'failed',
    'cancelled',
    'skipped'            -- Skipped because lead converted or lost
);

CREATE TYPE document_processing_status AS ENUM (
    'uploaded',          -- File stored, not yet processed
    'processing',        -- Text extraction + chunking in progress
    'embedding',         -- Generating vector embeddings
    'completed',         -- Ready for RAG queries
    'failed'             -- Processing failed
);

CREATE TYPE property_type AS ENUM (
    'apartment',
    'villa',
    'townhouse',
    'penthouse',
    'studio',
    'office',
    'retail',
    'land',
    'other'
);


-- ============================================================================
-- TABLE 1: agencies
-- The multi-tenant root entity. Every other table references this.
-- ============================================================================

CREATE TABLE agencies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    plan            subscription_plan NOT NULL DEFAULT 'free',
    
    -- Contact & branding
    email           VARCHAR(255),
    phone           VARCHAR(50),
    website         VARCHAR(500),
    logo_url        TEXT,
    
    -- Integration credentials (encrypted at application layer)
    whatsapp_phone_id       VARCHAR(100),
    whatsapp_access_token   TEXT,
    meta_ad_account_id      VARCHAR(100),
    meta_page_id            VARCHAR(100),
    
    -- Configuration
    settings        JSONB NOT NULL DEFAULT '{
        "chatbot_language": "en",
        "chatbot_greeting": null,
        "follow_up_enabled": true,
        "follow_up_days": [1, 3, 7],
        "auto_assignment": true,
        "assignment_method": "round_robin",
        "qualification_questions": [
            "budget_range",
            "property_type",
            "preferred_location",
            "timeline",
            "payment_method",
            "purpose"
        ],
        "working_hours": {
            "start": "09:00",
            "end": "18:00",
            "timezone": "Asia/Dubai"
        },
        "lead_score_thresholds": {
            "hot": 80,
            "warm": 60,
            "nurture": 30
        }
    }'::jsonb,
    
    timezone        VARCHAR(50) NOT NULL DEFAULT 'Asia/Dubai',
    
    -- Usage tracking
    leads_this_month    INT NOT NULL DEFAULT 0,
    leads_monthly_limit INT NOT NULL DEFAULT 50,    -- Based on plan
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agencies_slug ON agencies(slug);
CREATE INDEX idx_agencies_plan ON agencies(plan);


-- ============================================================================
-- TABLE 2: users
-- Authentication accounts. Linked to Supabase Auth (auth.users).
-- ============================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Supabase Auth link
    auth_user_id    UUID UNIQUE,            -- References auth.users(id)
    
    -- Profile
    email           VARCHAR(255) NOT NULL UNIQUE,
    full_name       VARCHAR(255) NOT NULL,
    phone           VARCHAR(50),
    avatar_url      TEXT,
    role            user_role NOT NULL DEFAULT 'agent',
    
    -- Tenant
    agency_id       UUID REFERENCES agencies(id) ON DELETE SET NULL,
    
    -- Status
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Metadata
    last_login_at   TIMESTAMPTZ,
    login_count     INT NOT NULL DEFAULT 0,
    preferences     JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_agency ON users(agency_id) WHERE agency_id IS NOT NULL;
CREATE INDEX idx_users_auth ON users(auth_user_id) WHERE auth_user_id IS NOT NULL;
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);


-- ============================================================================
-- TABLE 3: agents
-- Sales agents who receive and work leads within an agency.
-- Separated from users because agent-specific fields (assignment weight,
-- specialization, lead stats) don't belong on the auth/user entity.
-- ============================================================================

CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    user_id         UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    
    -- Profile
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255),
    phone           VARCHAR(50),
    
    -- Agent configuration
    specialization  VARCHAR(100),           -- e.g., "luxury", "off-plan", "commercial"
    languages       VARCHAR(50)[] DEFAULT ARRAY['en']::VARCHAR(50)[],
    
    -- Assignment control
    assignment_weight   INT NOT NULL DEFAULT 5 CHECK (assignment_weight BETWEEN 1 AND 10),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    is_available        BOOLEAN NOT NULL DEFAULT TRUE,     -- Can be toggled for breaks/leave
    max_active_leads    INT NOT NULL DEFAULT 50,
    
    -- Stats (denormalized for fast dashboard queries)
    total_leads_assigned    INT NOT NULL DEFAULT 0,
    total_leads_converted   INT NOT NULL DEFAULT 0,
    active_lead_count       INT NOT NULL DEFAULT 0,
    avg_response_time_mins  DECIMAL(8,2),
    
    -- Round-robin cursor
    last_assigned_at    TIMESTAMPTZ,
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agents_agency ON agents(agency_id);
CREATE INDEX idx_agents_agency_active ON agents(agency_id, is_active, is_available)
    WHERE is_active = TRUE AND is_available = TRUE;
CREATE INDEX idx_agents_user ON agents(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_agents_round_robin ON agents(agency_id, last_assigned_at NULLS FIRST)
    WHERE is_active = TRUE AND is_available = TRUE;


-- ============================================================================
-- TABLE 4: developers
-- Property developers who partner with agencies.
-- ============================================================================

CREATE TABLE developers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Profile
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100),
    contact_name    VARCHAR(255),
    contact_email   VARCHAR(255),
    contact_phone   VARCHAR(50),
    website         VARCHAR(500),
    logo_url        TEXT,
    description     TEXT,
    
    -- Status
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(agency_id, slug)
);

CREATE INDEX idx_developers_agency ON developers(agency_id);


-- ============================================================================
-- TABLE 5: campaigns
-- Tracks advertising campaigns and their performance metrics.
-- ============================================================================

CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Campaign identity
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    source          lead_source NOT NULL,
    
    -- Meta Ads integration
    meta_campaign_id    VARCHAR(100),
    meta_adset_id       VARCHAR(100),
    meta_ad_id          VARCHAR(100),
    
    -- Budget tracking
    budget_total        DECIMAL(12,2),
    budget_spent        DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    currency            VARCHAR(3) NOT NULL DEFAULT 'AED',
    
    -- Scheduling
    start_date      DATE,
    end_date        DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Denormalized metrics (updated by triggers/cron)
    total_leads         INT NOT NULL DEFAULT 0,
    qualified_leads     INT NOT NULL DEFAULT 0,
    converted_leads     INT NOT NULL DEFAULT 0,
    avg_lead_score      DECIMAL(5,2),
    cost_per_lead       DECIMAL(10,2),
    cost_per_qualified  DECIMAL(10,2),
    conversion_rate     DECIMAL(5,4),       -- Stored as decimal: 0.0523 = 5.23%
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_campaigns_agency ON campaigns(agency_id);
CREATE INDEX idx_campaigns_agency_active ON campaigns(agency_id, is_active) WHERE is_active = TRUE;
CREATE INDEX idx_campaigns_source ON campaigns(agency_id, source);
CREATE INDEX idx_campaigns_meta ON campaigns(meta_campaign_id) WHERE meta_campaign_id IS NOT NULL;
CREATE INDEX idx_campaigns_dates ON campaigns(agency_id, start_date, end_date);


-- ============================================================================
-- TABLE 6: leads
-- The central entity. Every inbound contact becomes a lead.
-- ============================================================================

CREATE TABLE leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    agent_id        UUID REFERENCES agents(id) ON DELETE SET NULL,
    
    -- Contact info
    name            VARCHAR(255),
    phone           VARCHAR(50) NOT NULL,
    email           VARCHAR(255),
    
    -- Source tracking
    source          lead_source NOT NULL,
    source_ref      VARCHAR(500),           -- Ad ID, form ID, referral code, etc.
    utm_source      VARCHAR(255),
    utm_medium      VARCHAR(255),
    utm_campaign    VARCHAR(255),
    
    -- Qualification status
    status          lead_status NOT NULL DEFAULT 'new',
    score           INT CHECK (score BETWEEN 0 AND 100),
    score_tier      VARCHAR(20) GENERATED ALWAYS AS (
                        CASE
                            WHEN score >= 80 THEN 'hot'
                            WHEN score >= 60 THEN 'warm'
                            WHEN score >= 30 THEN 'nurture'
                            WHEN score IS NOT NULL THEN 'cold'
                            ELSE 'unscored'
                        END
                    ) STORED,
    
    -- Structured qualification data
    -- Stored as JSONB for flexibility — different agencies may ask different questions
    qualification_data  JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*  Expected shape:
        {
            "budget_min": 500000,
            "budget_max": 1500000,
            "budget_currency": "AED",
            "property_type": "apartment",
            "bedrooms": 2,
            "preferred_location": "Dubai Marina",
            "timeline_months": 3,
            "payment_method": "cash",
            "purpose": "investment",
            "nationality": "UK",
            "notes": "Interested in sea view units"
        }
    */
    
    -- AI metadata
    language                VARCHAR(10),     -- Detected language code (en, ar, ru, etc.)
    qualification_turns     INT DEFAULT 0,   -- Number of chatbot turns completed
    qualification_complete  BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Agent interaction
    agent_assigned_at       TIMESTAMPTZ,
    first_agent_response_at TIMESTAMPTZ,
    
    -- Duplicate detection
    fingerprint     VARCHAR(255),            -- Hash of phone + agency_id for dedup
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    qualified_at    TIMESTAMPTZ,
    converted_at    TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ
);

-- Primary query patterns
CREATE INDEX idx_leads_agency_status ON leads(agency_id, status);
CREATE INDEX idx_leads_agency_score ON leads(agency_id, score DESC NULLS LAST);
CREATE INDEX idx_leads_agency_created ON leads(agency_id, created_at DESC);
CREATE INDEX idx_leads_agent ON leads(agent_id) WHERE agent_id IS NOT NULL;
CREATE INDEX idx_leads_campaign ON leads(campaign_id) WHERE campaign_id IS NOT NULL;

-- Contact lookup (for incoming message matching)
CREATE INDEX idx_leads_phone_agency ON leads(phone, agency_id);
CREATE UNIQUE INDEX idx_leads_fingerprint ON leads(fingerprint) WHERE fingerprint IS NOT NULL;

-- Dashboard filter combinations
CREATE INDEX idx_leads_agency_source_status ON leads(agency_id, source, status);
CREATE INDEX idx_leads_score_tier ON leads(agency_id, score_tier);

-- JSONB qualification field queries
CREATE INDEX idx_leads_qual_budget ON leads USING gin ((qualification_data->'budget_max'));
CREATE INDEX idx_leads_qual_location ON leads USING gin ((qualification_data->'preferred_location'));
CREATE INDEX idx_leads_qual_type ON leads USING gin ((qualification_data->'property_type'));

-- Full text search on lead name/email
CREATE INDEX idx_leads_name_trgm ON leads USING gin (name gin_trgm_ops);


-- ============================================================================
-- TABLE 7: lead_scores
-- Stores the full scoring breakdown for audit trail + retraining.
-- Each scoring event creates a new row (versioned), so you can track
-- how a lead's score changed over time.
-- ============================================================================

CREATE TABLE lead_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Composite score (sum of components + AI adjustment)
    total_score     INT NOT NULL CHECK (total_score BETWEEN 0 AND 100),
    
    -- Rule-based component scores
    budget_score    INT NOT NULL DEFAULT 0 CHECK (budget_score BETWEEN 0 AND 25),
    timeline_score  INT NOT NULL DEFAULT 0 CHECK (timeline_score BETWEEN 0 AND 20),
    payment_score   INT NOT NULL DEFAULT 0 CHECK (payment_score BETWEEN 0 AND 20),
    location_score  INT NOT NULL DEFAULT 0 CHECK (location_score BETWEEN 0 AND 15),
    engagement_score INT NOT NULL DEFAULT 0 CHECK (engagement_score BETWEEN 0 AND 10),
    purpose_score   INT NOT NULL DEFAULT 0 CHECK (purpose_score BETWEEN 0 AND 10),
    
    -- AI confidence adjustment (-10 to +10)
    ai_adjustment   INT NOT NULL DEFAULT 0 CHECK (ai_adjustment BETWEEN -10 AND 10),
    ai_reasoning    TEXT,
    
    -- Scoring context
    rule_score_raw  INT NOT NULL,           -- Sum of rule-based before AI adjustment
    model_version   VARCHAR(50),            -- e.g., "gpt-4o-mini-2024-07-18"
    prompt_version  VARCHAR(20),            -- e.g., "v2.1"
    
    -- Input snapshot (for debugging / retraining)
    qualification_snapshot  JSONB,           -- Copy of qualification_data at scoring time
    conversation_length     INT,             -- Number of messages at scoring time
    
    -- Versioning
    version         INT NOT NULL DEFAULT 1,  -- Increments on re-score
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Timestamps
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lead_scores_lead ON lead_scores(lead_id);
CREATE INDEX idx_lead_scores_lead_current ON lead_scores(lead_id) WHERE is_current = TRUE;
CREATE INDEX idx_lead_scores_agency_date ON lead_scores(agency_id, scored_at DESC);
CREATE INDEX idx_lead_scores_total ON lead_scores(agency_id, total_score DESC)
    WHERE is_current = TRUE;


-- ============================================================================
-- TABLE 8: conversations
-- Groups messages into logical conversations per lead per channel.
-- A lead may have multiple conversations (e.g., WhatsApp + web widget).
-- ============================================================================

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Channel context
    channel         lead_source NOT NULL,
    channel_ref     VARCHAR(255),           -- WhatsApp thread ID, IG thread ID, etc.
    
    -- State machine
    status          conversation_status NOT NULL DEFAULT 'active',
    
    -- AI context tracking
    current_step    VARCHAR(50) DEFAULT 'greeting',  -- greeting, qualifying, property_search, scoring
    questions_asked VARCHAR(50)[] DEFAULT ARRAY[]::VARCHAR(50)[],
    
    -- Metrics
    message_count       INT NOT NULL DEFAULT 0,
    user_message_count  INT NOT NULL DEFAULT 0,
    ai_message_count    INT NOT NULL DEFAULT 0,
    total_ai_tokens     INT NOT NULL DEFAULT 0,     -- For cost tracking
    avg_response_time_s DECIMAL(8,2),               -- Avg lead response time in seconds
    
    -- Timestamps
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    timed_out_at    TIMESTAMPTZ
);

CREATE INDEX idx_conversations_lead ON conversations(lead_id);
CREATE INDEX idx_conversations_agency ON conversations(agency_id);
CREATE INDEX idx_conversations_agency_status ON conversations(agency_id, status);
CREATE INDEX idx_conversations_channel_ref ON conversations(channel_ref) WHERE channel_ref IS NOT NULL;
CREATE INDEX idx_conversations_active ON conversations(agency_id, status, last_message_at DESC)
    WHERE status IN ('active', 'waiting_response');


-- ============================================================================
-- TABLE 9: messages
-- Individual messages within a conversation. Immutable append-only log.
-- ============================================================================

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    
    -- Message content
    role            message_role NOT NULL,
    content         TEXT NOT NULL,
    message_type    message_type NOT NULL DEFAULT 'text',
    
    -- External messaging platform references
    external_msg_id VARCHAR(255),           -- WhatsApp/IG message ID
    delivery_status delivery_status DEFAULT 'pending',
    
    -- AI metadata (only for assistant messages)
    ai_model        VARCHAR(50),            -- e.g., "gpt-4o-mini"
    token_count     INT,                    -- Total tokens (prompt + completion)
    prompt_tokens   INT,
    completion_tokens INT,
    ai_latency_ms   INT,                    -- Response time in milliseconds
    
    -- Function calling (for RAG / qualification extraction)
    function_call   JSONB,                  -- {name: "property_search", arguments: {...}}
    function_result JSONB,                  -- Search results / extracted data
    
    -- Attachments (images, documents sent by lead)
    attachments     JSONB,                  -- [{url, type, caption}]
    
    -- Metadata
    metadata        JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at    TIMESTAMPTZ,
    read_at         TIMESTAMPTZ
);

-- Primary access pattern: load conversation messages in order
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at ASC);
CREATE INDEX idx_messages_lead ON messages(lead_id, created_at ASC);
CREATE INDEX idx_messages_external ON messages(external_msg_id) WHERE external_msg_id IS NOT NULL;
CREATE INDEX idx_messages_delivery ON messages(delivery_status, created_at)
    WHERE delivery_status = 'pending';


-- ============================================================================
-- TABLE 10: properties
-- Real estate listings uploaded by agencies/developers for the AI to recommend.
-- ============================================================================

CREATE TABLE properties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    developer_id    UUID REFERENCES developers(id) ON DELETE SET NULL,
    
    -- Listing details
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(200),
    description     TEXT,
    location        VARCHAR(255) NOT NULL,
    sub_location    VARCHAR(255),           -- District / community / tower
    city            VARCHAR(100),
    country         VARCHAR(100) DEFAULT 'UAE',
    
    -- Property specs
    property_type   property_type NOT NULL,
    bedrooms_min    INT,
    bedrooms_max    INT,
    bathrooms_min   INT,
    bathrooms_max   INT,
    size_sqft_min   DECIMAL(10,2),
    size_sqft_max   DECIMAL(10,2),
    
    -- Pricing
    price_from      DECIMAL(14,2) NOT NULL,
    price_to        DECIMAL(14,2),
    currency        VARCHAR(3) NOT NULL DEFAULT 'AED',
    price_per_sqft  DECIMAL(10,2),
    
    -- Payment & timeline
    payment_plan    TEXT,                    -- e.g., "60/40", "10% booking, 40% construction, 50% handover"
    handover_date   DATE,
    construction_status VARCHAR(50),         -- off_plan, under_construction, ready
    
    -- Features
    amenities       JSONB DEFAULT '[]'::jsonb,   -- ["pool", "gym", "parking", "sea_view"]
    floor_plans     JSONB DEFAULT '[]'::jsonb,   -- [{type, sqft, price, image_url}]
    images          JSONB DEFAULT '[]'::jsonb,   -- [{url, caption, order}]
    
    -- Search optimization
    tags            VARCHAR(50)[] DEFAULT ARRAY[]::VARCHAR(50)[],
    
    -- Status
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_featured     BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(agency_id, slug)
);

CREATE INDEX idx_properties_agency ON properties(agency_id);
CREATE INDEX idx_properties_agency_active ON properties(agency_id, is_active) WHERE is_active = TRUE;
CREATE INDEX idx_properties_developer ON properties(developer_id) WHERE developer_id IS NOT NULL;
CREATE INDEX idx_properties_type ON properties(agency_id, property_type) WHERE is_active = TRUE;
CREATE INDEX idx_properties_location ON properties(agency_id, location) WHERE is_active = TRUE;
CREATE INDEX idx_properties_price ON properties(agency_id, price_from, price_to) WHERE is_active = TRUE;
CREATE INDEX idx_properties_bedrooms ON properties(agency_id, bedrooms_min, bedrooms_max) WHERE is_active = TRUE;
CREATE INDEX idx_properties_tags ON properties USING gin (tags);
CREATE INDEX idx_properties_amenities ON properties USING gin (amenities);


-- ============================================================================
-- TABLE 11: documents
-- Uploaded files (PDFs, brochures, pricing sheets) for the knowledge base.
-- Tracks the processing pipeline: upload → extract → chunk → embed.
-- ============================================================================

CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    property_id     UUID REFERENCES properties(id) ON DELETE CASCADE,
    
    -- File info
    file_name       VARCHAR(500) NOT NULL,
    file_type       VARCHAR(50) NOT NULL,    -- pdf, docx, txt, csv
    storage_path    TEXT NOT NULL,            -- Supabase Storage path
    file_size_bytes BIGINT,
    
    -- Extracted content (raw, before chunking)
    extracted_text  TEXT,
    page_count      INT,
    
    -- Processing pipeline
    processing_status   document_processing_status NOT NULL DEFAULT 'uploaded',
    chunk_count         INT DEFAULT 0,
    error_message       TEXT,
    processing_attempts INT NOT NULL DEFAULT 0,
    
    -- Upload metadata
    uploaded_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Timestamps
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_agency ON documents(agency_id);
CREATE INDEX idx_documents_property ON documents(property_id) WHERE property_id IS NOT NULL;
CREATE INDEX idx_documents_status ON documents(processing_status)
    WHERE processing_status IN ('uploaded', 'processing', 'embedding');


-- ============================================================================
-- TABLE 12: knowledge_base_embeddings
-- Vector chunks for RAG retrieval. Each row is one chunk of a document
-- with its embedding vector for similarity search.
-- ============================================================================

CREATE TABLE knowledge_base_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    property_id     UUID REFERENCES properties(id) ON DELETE CASCADE,
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Chunk content
    chunk_index     INT NOT NULL,
    content_text    TEXT NOT NULL,
    content_length  INT NOT NULL,            -- Character count
    
    -- Vector embedding (OpenAI text-embedding-3-small = 1536 dimensions)
    embedding       vector(1536) NOT NULL,
    
    -- Chunk metadata for filtering
    chunk_metadata  JSONB DEFAULT '{}'::jsonb,
    /*  Expected shape:
        {
            "page_number": 3,
            "section_title": "Payment Plan",
            "content_type": "pricing",    -- pricing, features, location, general
            "language": "en"
        }
    */
    
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary RAG query: vector similarity search scoped to agency
-- Using ivfflat for fast approximate nearest neighbor search
CREATE INDEX idx_embeddings_vector ON knowledge_base_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_embeddings_agency ON knowledge_base_embeddings(agency_id);
CREATE INDEX idx_embeddings_document ON knowledge_base_embeddings(document_id);
CREATE INDEX idx_embeddings_property ON knowledge_base_embeddings(property_id)
    WHERE property_id IS NOT NULL;
CREATE INDEX idx_embeddings_agency_property ON knowledge_base_embeddings(agency_id, property_id);


-- ============================================================================
-- TABLE 13: analytics_events
-- Flexible event-sourcing table for all trackable actions.
-- Append-only design — never update, only insert.
-- ============================================================================

CREATE TABLE analytics_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Event identity
    event_type      VARCHAR(100) NOT NULL,
    event_category  VARCHAR(50) NOT NULL,
    /*
        Categories and their event types:
        
        'lead' →
            lead.created, lead.qualified, lead.scored, lead.assigned,
            lead.status_changed, lead.converted, lead.lost, lead.archived
        
        'conversation' →
            conversation.started, conversation.message_sent,
            conversation.message_received, conversation.completed,
            conversation.timed_out, conversation.handed_to_agent
        
        'campaign' →
            campaign.created, campaign.lead_attributed,
            campaign.budget_updated, campaign.paused, campaign.ended
        
        'agent' →
            agent.lead_assigned, agent.first_response,
            agent.lead_converted, agent.lead_lost
        
        'property' →
            property.recommended, property.viewed,
            property.document_uploaded, property.search_matched
        
        'system' →
            followup.sent, followup.delivered, followup.failed,
            webhook.received, webhook.error, api.rate_limited
    */
    
    -- Reference IDs (nullable — not every event has all references)
    lead_id         UUID,
    campaign_id     UUID,
    agent_id        UUID,
    property_id     UUID,
    conversation_id UUID,
    
    -- Event payload (flexible)
    event_data      JSONB NOT NULL DEFAULT '{}'::jsonb,
    /*  Examples:
        lead.scored: {"old_score": 45, "new_score": 78, "scoring_version": 2}
        lead.status_changed: {"old_status": "new", "new_status": "qualifying"}
        conversation.message_sent: {"channel": "whatsapp", "tokens": 234}
        campaign.lead_attributed: {"cost": 12.50, "ad_id": "123"}
        property.recommended: {"query": "2BR Marina", "match_score": 0.87}
    */
    
    -- Source context
    source          VARCHAR(50),             -- whatsapp, instagram, web_widget, dashboard, api, system
    session_id      VARCHAR(100),            -- Browser session or conversation session
    ip_address      INET,
    user_agent      TEXT,
    
    -- Timing
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Partitioning helper (for future table partitioning)
    occurred_date   DATE GENERATED ALWAYS AS (occurred_at::date) STORED
);

-- Time-series queries (most recent first within an agency)
CREATE INDEX idx_analytics_agency_time ON analytics_events(agency_id, occurred_at DESC);

-- Event type filtering
CREATE INDEX idx_analytics_type ON analytics_events(agency_id, event_type, occurred_at DESC);
CREATE INDEX idx_analytics_category ON analytics_events(agency_id, event_category, occurred_at DESC);

-- Entity-specific event streams
CREATE INDEX idx_analytics_lead ON analytics_events(lead_id, occurred_at DESC)
    WHERE lead_id IS NOT NULL;
CREATE INDEX idx_analytics_campaign ON analytics_events(campaign_id, occurred_at DESC)
    WHERE campaign_id IS NOT NULL;
CREATE INDEX idx_analytics_agent ON analytics_events(agent_id, occurred_at DESC)
    WHERE agent_id IS NOT NULL;

-- Date-range aggregation (for dashboards)
CREATE INDEX idx_analytics_date ON analytics_events(agency_id, occurred_date, event_type);


-- ============================================================================
-- TABLE 14: follow_ups (supporting table)
-- Scheduled automated follow-up messages.
-- ============================================================================

CREATE TABLE follow_ups (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    agency_id       UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
    
    -- Schedule
    day_number      INT NOT NULL CHECK (day_number > 0),
    channel         lead_source NOT NULL,
    template_key    VARCHAR(100) NOT NULL,
    
    -- Content
    personalized_content TEXT,               -- AI-generated personalized message
    
    -- Status
    status          follow_up_status NOT NULL DEFAULT 'pending',
    external_msg_id VARCHAR(255),            -- WhatsApp message ID after sending
    failure_reason  TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    
    -- Timestamps
    scheduled_at    TIMESTAMPTZ NOT NULL,
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_followups_pending ON follow_ups(scheduled_at ASC)
    WHERE status = 'pending';
CREATE INDEX idx_followups_lead ON follow_ups(lead_id);
CREATE INDEX idx_followups_agency ON follow_ups(agency_id);


-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_agencies_updated_at BEFORE UPDATE ON agencies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_agents_updated_at BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_campaigns_updated_at BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_leads_updated_at BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_properties_updated_at BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- Generate lead fingerprint for dedup on insert
CREATE OR REPLACE FUNCTION generate_lead_fingerprint()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fingerprint = encode(
        digest(NEW.phone || '::' || NEW.agency_id::text, 'sha256'),
        'hex'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leads_fingerprint BEFORE INSERT ON leads
    FOR EACH ROW EXECUTE FUNCTION generate_lead_fingerprint();


-- Mark old score versions when a new score is inserted
CREATE OR REPLACE FUNCTION mark_old_scores()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE lead_scores
    SET is_current = FALSE
    WHERE lead_id = NEW.lead_id
      AND id != NEW.id
      AND is_current = TRUE;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lead_scores_versioning AFTER INSERT ON lead_scores
    FOR EACH ROW EXECUTE FUNCTION mark_old_scores();


-- Update conversation metrics on new message
CREATE OR REPLACE FUNCTION update_conversation_on_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations SET
        message_count = message_count + 1,
        user_message_count = user_message_count + CASE WHEN NEW.role = 'user' THEN 1 ELSE 0 END,
        ai_message_count = ai_message_count + CASE WHEN NEW.role = 'assistant' THEN 1 ELSE 0 END,
        total_ai_tokens = total_ai_tokens + COALESCE(NEW.token_count, 0),
        last_message_at = NEW.created_at
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_messages_update_conversation AFTER INSERT ON messages
    FOR EACH ROW EXECUTE FUNCTION update_conversation_on_message();


-- Update campaign lead count on new lead
CREATE OR REPLACE FUNCTION update_campaign_lead_count()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.campaign_id IS NOT NULL THEN
        UPDATE campaigns SET
            total_leads = total_leads + 1,
            cost_per_lead = CASE
                WHEN (total_leads + 1) > 0 THEN budget_spent / (total_leads + 1)
                ELSE NULL
            END
        WHERE id = NEW.campaign_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leads_update_campaign AFTER INSERT ON leads
    FOR EACH ROW EXECUTE FUNCTION update_campaign_lead_count();


-- Increment monthly lead counter for plan enforcement
CREATE OR REPLACE FUNCTION increment_agency_lead_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE agencies
    SET leads_this_month = leads_this_month + 1
    WHERE id = NEW.agency_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leads_agency_count AFTER INSERT ON leads
    FOR EACH ROW EXECUTE FUNCTION increment_agency_lead_count();


-- ============================================================================
-- RAG SEARCH FUNCTION
-- Similarity search scoped to an agency, with optional property filter.
-- ============================================================================

CREATE OR REPLACE FUNCTION search_knowledge_base(
    p_agency_id     UUID,
    p_query_embedding vector(1536),
    p_match_count   INT DEFAULT 5,
    p_match_threshold FLOAT DEFAULT 0.7,
    p_property_id   UUID DEFAULT NULL
)
RETURNS TABLE (
    id              UUID,
    document_id     UUID,
    property_id     UUID,
    content_text    TEXT,
    chunk_metadata  JSONB,
    similarity      FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        kbe.id,
        kbe.document_id,
        kbe.property_id,
        kbe.content_text,
        kbe.chunk_metadata,
        1 - (kbe.embedding <=> p_query_embedding) AS similarity
    FROM knowledge_base_embeddings kbe
    WHERE kbe.agency_id = p_agency_id
      AND (p_property_id IS NULL OR kbe.property_id = p_property_id)
      AND 1 - (kbe.embedding <=> p_query_embedding) > p_match_threshold
    ORDER BY kbe.embedding <=> p_query_embedding
    LIMIT p_match_count;
END;
$$ LANGUAGE plpgsql STABLE;


-- ============================================================================
-- ROUND-ROBIN AGENT ASSIGNMENT FUNCTION
-- Picks the next eligible agent based on weighted round-robin.
-- ============================================================================

CREATE OR REPLACE FUNCTION assign_next_agent(
    p_agency_id UUID,
    p_specialization VARCHAR DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_agent_id UUID;
BEGIN
    SELECT id INTO v_agent_id
    FROM agents
    WHERE agency_id = p_agency_id
      AND is_active = TRUE
      AND is_available = TRUE
      AND active_lead_count < max_active_leads
      AND (p_specialization IS NULL OR specialization = p_specialization)
    ORDER BY
        last_assigned_at NULLS FIRST,       -- Never-assigned agents go first
        (total_leads_assigned::float / GREATEST(assignment_weight, 1)) ASC  -- Weight-adjusted fairness
    LIMIT 1
    FOR UPDATE SKIP LOCKED;                  -- Prevent race conditions
    
    IF v_agent_id IS NOT NULL THEN
        UPDATE agents SET
            last_assigned_at = NOW(),
            total_leads_assigned = total_leads_assigned + 1,
            active_lead_count = active_lead_count + 1
        WHERE id = v_agent_id;
    END IF;
    
    RETURN v_agent_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- MATERIALIZED VIEWS (for dashboard performance)
-- ============================================================================

-- Daily campaign performance snapshot
CREATE MATERIALIZED VIEW mv_campaign_daily_stats AS
SELECT
    c.id AS campaign_id,
    c.agency_id,
    d.date,
    COUNT(l.id) AS leads,
    COUNT(l.id) FILTER (WHERE l.score >= 60) AS qualified_leads,
    COUNT(l.id) FILTER (WHERE l.status = 'converted') AS converted_leads,
    ROUND(AVG(l.score), 1) AS avg_score,
    ROUND(
        CASE WHEN COUNT(l.id) > 0
             THEN c.budget_spent / COUNT(l.id)
             ELSE NULL END,
        2
    ) AS cost_per_lead
FROM campaigns c
CROSS JOIN generate_series(
    COALESCE(c.start_date, c.created_at::date),
    COALESCE(c.end_date, CURRENT_DATE),
    '1 day'::interval
) AS d(date)
LEFT JOIN leads l ON l.campaign_id = c.id
    AND l.created_at::date = d.date
GROUP BY c.id, c.agency_id, d.date;

CREATE UNIQUE INDEX idx_mv_campaign_daily ON mv_campaign_daily_stats(campaign_id, date);
CREATE INDEX idx_mv_campaign_agency ON mv_campaign_daily_stats(agency_id, date DESC);


-- Agency-level KPI snapshot
CREATE MATERIALIZED VIEW mv_agency_kpis AS
SELECT
    a.id AS agency_id,
    COUNT(l.id) FILTER (WHERE l.created_at >= date_trunc('month', CURRENT_DATE)) AS leads_this_month,
    COUNT(l.id) FILTER (WHERE l.created_at >= date_trunc('week', CURRENT_DATE)) AS leads_this_week,
    COUNT(l.id) FILTER (WHERE l.created_at >= CURRENT_DATE) AS leads_today,
    ROUND(AVG(l.score) FILTER (WHERE l.score IS NOT NULL), 1) AS avg_score,
    COUNT(l.id) FILTER (WHERE l.score >= 80) AS hot_leads,
    COUNT(l.id) FILTER (WHERE l.status = 'converted') AS total_conversions,
    ROUND(
        COUNT(l.id) FILTER (WHERE l.status = 'converted')::numeric /
        NULLIF(COUNT(l.id) FILTER (WHERE l.score IS NOT NULL), 0) * 100,
        2
    ) AS conversion_rate_pct
FROM agencies a
LEFT JOIN leads l ON l.agency_id = a.id
GROUP BY a.id;

CREATE UNIQUE INDEX idx_mv_agency_kpis ON mv_agency_kpis(agency_id);


-- ============================================================================
-- ROW LEVEL SECURITY (Supabase multi-tenancy)
-- ============================================================================

-- Helper: get current user's agency_id from JWT
CREATE OR REPLACE FUNCTION get_user_agency_id()
RETURNS UUID AS $$
    SELECT agency_id FROM users WHERE auth_user_id = auth.uid();
$$ LANGUAGE sql STABLE SECURITY DEFINER;


-- Enable RLS on all tenant-scoped tables
ALTER TABLE agencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE developers ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_base_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY;


-- Agency: users can see their own agency
CREATE POLICY "agency_select" ON agencies FOR SELECT
    USING (id = get_user_agency_id());

-- Users: can see colleagues in same agency
CREATE POLICY "users_select" ON users FOR SELECT
    USING (agency_id = get_user_agency_id());

-- Agents: scoped to agency
CREATE POLICY "agents_all" ON agents FOR ALL
    USING (agency_id = get_user_agency_id());

-- Developers: scoped to agency
CREATE POLICY "developers_all" ON developers FOR ALL
    USING (agency_id = get_user_agency_id());

-- Campaigns: scoped to agency
CREATE POLICY "campaigns_all" ON campaigns FOR ALL
    USING (agency_id = get_user_agency_id());

-- Leads: scoped to agency (agents see only their assigned leads via app logic)
CREATE POLICY "leads_all" ON leads FOR ALL
    USING (agency_id = get_user_agency_id());

-- Lead scores: scoped to agency
CREATE POLICY "lead_scores_all" ON lead_scores FOR ALL
    USING (agency_id = get_user_agency_id());

-- Conversations: scoped to agency
CREATE POLICY "conversations_all" ON conversations FOR ALL
    USING (agency_id = get_user_agency_id());

-- Messages: scoped via conversation's lead
CREATE POLICY "messages_select" ON messages FOR SELECT
    USING (lead_id IN (SELECT id FROM leads WHERE agency_id = get_user_agency_id()));

-- Properties: scoped to agency
CREATE POLICY "properties_all" ON properties FOR ALL
    USING (agency_id = get_user_agency_id());

-- Documents: scoped to agency
CREATE POLICY "documents_all" ON documents FOR ALL
    USING (agency_id = get_user_agency_id());

-- Embeddings: scoped to agency
CREATE POLICY "embeddings_select" ON knowledge_base_embeddings FOR SELECT
    USING (agency_id = get_user_agency_id());

-- Analytics: scoped to agency
CREATE POLICY "analytics_select" ON analytics_events FOR SELECT
    USING (agency_id = get_user_agency_id());

-- Follow-ups: scoped to agency
CREATE POLICY "followups_all" ON follow_ups FOR ALL
    USING (agency_id = get_user_agency_id());


-- Service role bypass (for backend API using service key)
-- Supabase service_role key bypasses RLS by default, so the FastAPI backend
-- can access all data. No additional policy needed.


-- ============================================================================
-- CRON JOBS (via pg_cron or application scheduler)
-- ============================================================================

-- Reset monthly lead counter on 1st of each month
-- In Supabase, schedule via Dashboard > Database > Cron Jobs:
--   SELECT cron.schedule('reset-monthly-leads', '0 0 1 * *',
--     $$ UPDATE agencies SET leads_this_month = 0 $$);

-- Refresh materialized views every 15 minutes
-- SELECT cron.schedule('refresh-campaign-stats', '*/15 * * * *',
--     $$ REFRESH MATERIALIZED VIEW CONCURRENTLY mv_campaign_daily_stats $$);
-- SELECT cron.schedule('refresh-agency-kpis', '*/15 * * * *',
--     $$ REFRESH MATERIALIZED VIEW CONCURRENTLY mv_agency_kpis $$);

-- Auto-archive old leads (older than 6 months, not converted)
-- SELECT cron.schedule('archive-old-leads', '0 3 * * 0',
--     $$ UPDATE leads SET status = 'archived', archived_at = NOW()
--        WHERE status NOT IN ('converted', 'archived')
--        AND created_at < NOW() - INTERVAL '6 months' $$);
