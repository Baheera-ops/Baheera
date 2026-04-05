# BAHERA — Architecture Design Document

**AI-Powered Real Estate Lead Generation & Qualification Platform**
**Version:** 1.0 MVP
**Date:** April 2026

---

## 1. System Architecture Overview

BAHERA uses a **modular monolith** pattern — a single FastAPI backend organized into clean internal modules, deployed as one container. This eliminates the operational complexity of microservices while keeping the codebase organized for future separation if needed.

### Why This Stack

| Decision | Rationale |
|----------|-----------|
| **FastAPI** (Python) | AI/ML ecosystem compatibility, async by default, auto-generates API docs |
| **Supabase** (PostgreSQL + pgvector + Auth + Storage) | Replaces 4 separate services with one managed platform |
| **Next.js** on Vercel | Zero-config deployment, SSR for dashboard, API routes for BFF |
| **OpenAI API** | Best cost-to-quality for conversational AI + embeddings |
| **APScheduler** | Lightweight background jobs without Redis/Celery overhead |

### Backend Module Structure

```
bahera-api/
├── app/
│   ├── main.py                 # FastAPI app entry
│   ├── config.py               # Env vars, settings
│   ├── dependencies.py         # DB sessions, auth deps
│   ├── modules/
│   │   ├── leads/
│   │   │   ├── router.py       # Lead CRUD endpoints
│   │   │   ├── service.py      # Business logic
│   │   │   ├── models.py       # SQLAlchemy models
│   │   │   └── schemas.py      # Pydantic schemas
│   │   ├── chatbot/
│   │   │   ├── router.py       # Webhook receivers
│   │   │   ├── engine.py       # AI conversation engine
│   │   │   ├── scoring.py      # Lead scoring algorithm
│   │   │   └── prompts.py      # System prompts
│   │   ├── agents/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   └── assignment.py   # Round-robin logic
│   │   ├── campaigns/
│   │   │   ├── router.py
│   │   │   └── analytics.py    # Cost/conversion tracking
│   │   ├── properties/
│   │   │   ├── router.py
│   │   │   ├── rag.py          # Vector search + retrieval
│   │   │   └── embeddings.py   # PDF → chunks → vectors
│   │   ├── messaging/
│   │   │   ├── whatsapp.py     # WhatsApp Cloud API
│   │   │   ├── instagram.py    # IG Messaging API
│   │   │   └── followups.py    # Scheduled messages
│   │   └── webhooks/
│   │       ├── meta.py         # Meta Lead Ads webhook
│   │       └── widget.py       # Website widget events
│   ├── scheduler/
│   │   └── jobs.py             # APScheduler follow-up jobs
│   └── middleware/
│       ├── auth.py             # Supabase JWT validation
│       └── tenant.py           # Multi-tenancy filter
```

### Frontend Structure (Next.js)

```
bahera-dashboard/
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── signup/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx          # Sidebar + nav
│   │   ├── page.tsx            # Overview / KPIs
│   │   ├── leads/
│   │   │   ├── page.tsx        # Lead table + filters
│   │   │   └── [id]/page.tsx   # Lead detail + chat log
│   │   ├── agents/page.tsx     # Agent management
│   │   ├── campaigns/page.tsx  # Campaign analytics
│   │   ├── properties/page.tsx # Knowledge base upload
│   │   └── settings/page.tsx   # Org config
│   └── api/                    # BFF proxy routes
├── components/
│   ├── LeadTable.tsx
│   ├── LeadScoreBadge.tsx
│   ├── ChatTranscript.tsx
│   ├── CampaignChart.tsx
│   └── KPICard.tsx
└── lib/
    ├── supabase.ts             # Client init
    └── api.ts                  # FastAPI client
```

---

## 2. Database Schema

### Core Tables

**organizations** — Multi-tenant root entity. Each agency is one organization.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | Supabase-generated |
| name | varchar(255) | Agency name |
| plan | varchar(50) | free / starter / pro |
| whatsapp_phone_id | varchar(50) | WhatsApp Business phone ID |
| meta_ad_account_id | varchar(50) | For campaign sync |
| settings | jsonb | Chatbot language, follow-up config |
| created_at | timestamptz | |

**agents** — Team members who receive leads.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| org_id | uuid FK → organizations | |
| user_id | uuid FK → auth.users | Supabase auth link |
| name | varchar(255) | |
| email | varchar(255) | |
| phone | varchar(50) | For WhatsApp notifications |
| is_active | boolean | Controls assignment eligibility |
| assignment_weight | int | 1-10, for weighted round-robin |
| last_assigned_at | timestamptz | Used by round-robin cursor |

**campaigns** — Tracks ad campaigns and their performance.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| org_id | uuid FK | |
| name | varchar(255) | |
| source | varchar(50) | meta_ads / whatsapp / instagram / website |
| meta_campaign_id | varchar(100) | Synced from Meta |
| budget | decimal(12,2) | Campaign spend |
| start_date | date | |
| end_date | date | |
| is_active | boolean | |

**leads** — Core entity. Every inbound contact becomes a lead.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| org_id | uuid FK | |
| campaign_id | uuid FK → campaigns | Nullable |
| agent_id | uuid FK → agents | Nullable until assigned |
| name | varchar(255) | |
| phone | varchar(50) | Primary identifier |
| email | varchar(255) | |
| source | varchar(50) | meta_lead_ad / whatsapp / instagram / website |
| source_ref | varchar(255) | Ad ID, form ID, etc. |
| score | int | 0–100 |
| status | varchar(30) | new / qualifying / qualified / contacted / converted / lost |
| qualification_data | jsonb | Structured: budget, timeline, location, payment_method, property_type, purpose |
| language | varchar(10) | Detected language code |
| created_at | timestamptz | |
| qualified_at | timestamptz | When scoring completed |

**conversations** — Full chat transcript per lead.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| lead_id | uuid FK | |
| role | varchar(20) | user / assistant / system |
| message | text | |
| channel | varchar(30) | whatsapp / instagram / web_widget |
| metadata | jsonb | Message ID, delivery status |
| created_at | timestamptz | |

**properties** — Project listings uploaded by developer clients.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| org_id | uuid FK | |
| name | varchar(255) | Project name |
| developer | varchar(255) | Developer name |
| location | varchar(255) | Area / district |
| property_type | varchar(50) | apartment / villa / townhouse / office |
| bedrooms_min | int | |
| bedrooms_max | int | |
| price_from | decimal(14,2) | |
| price_to | decimal(14,2) | |
| currency | varchar(3) | AED, USD, EUR |
| handover_date | date | |
| payment_plan | text | |
| details | jsonb | Amenities, floor plans, etc. |
| is_active | boolean | |

**property_documents** — RAG knowledge base. Chunks of uploaded PDFs with embeddings.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| property_id | uuid FK | |
| file_name | varchar(255) | Original filename |
| file_url | text | Supabase Storage URL |
| chunk_index | int | Position in document |
| content_text | text | Extracted text chunk |
| embedding | vector(1536) | OpenAI text-embedding-3-small |
| created_at | timestamptz | |

**follow_ups** — Scheduled automated messages.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| lead_id | uuid FK | |
| day_number | int | 1, 3, or 7 |
| channel | varchar(30) | whatsapp / email |
| template_key | varchar(100) | Message template reference |
| status | varchar(20) | pending / sent / failed / cancelled |
| scheduled_at | timestamptz | |
| sent_at | timestamptz | |

### Indexes

```sql
CREATE INDEX idx_leads_org_status ON leads(org_id, status);
CREATE INDEX idx_leads_org_score ON leads(org_id, score DESC);
CREATE INDEX idx_leads_phone ON leads(phone);
CREATE INDEX idx_leads_campaign ON leads(campaign_id);
CREATE INDEX idx_conversations_lead ON conversations(lead_id, created_at);
CREATE INDEX idx_followups_scheduled ON follow_ups(status, scheduled_at)
  WHERE status = 'pending';
CREATE INDEX idx_property_docs_embedding ON property_documents
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

### Row-Level Security (Supabase RLS)

```sql
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Org members see own leads" ON leads
  FOR ALL USING (
    org_id IN (SELECT org_id FROM agents WHERE user_id = auth.uid())
  );
-- Same pattern for all tenant-scoped tables
```

---

## 3. API Structure

### Authentication

All API calls use Supabase JWT tokens passed as `Authorization: Bearer <token>`. The FastAPI middleware extracts the user and resolves their `org_id` for tenant isolation.

### Endpoint Map

#### Webhooks (Public — verified by signature)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/webhooks/meta/leadgen` | Meta Lead Ads instant form submissions |
| POST | `/webhooks/meta/messaging` | WhatsApp + Instagram incoming messages |
| GET | `/webhooks/meta/verify` | Meta webhook verification challenge |
| POST | `/webhooks/widget` | Website widget lead capture |

#### Leads (Authenticated)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/leads` | List leads (filterable, paginated) |
| GET | `/api/v1/leads/{id}` | Lead detail + qualification data |
| PATCH | `/api/v1/leads/{id}` | Update status, reassign agent |
| GET | `/api/v1/leads/{id}/conversations` | Full chat transcript |
| POST | `/api/v1/leads/{id}/note` | Agent adds manual note |
| GET | `/api/v1/leads/stats` | Aggregate counts by status/score |

#### Agents (Authenticated — Admin only)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/agents` | List agents in org |
| POST | `/api/v1/agents` | Invite new agent |
| PATCH | `/api/v1/agents/{id}` | Update weight, active status |
| GET | `/api/v1/agents/{id}/leads` | Agent's assigned leads |

#### Campaigns (Authenticated)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/campaigns` | List campaigns |
| POST | `/api/v1/campaigns` | Create campaign tracking entry |
| GET | `/api/v1/campaigns/{id}/analytics` | Cost per lead, conversion rate, score dist |
| POST | `/api/v1/campaigns/sync-meta` | Pull campaign data from Meta Ads API |

#### Properties & Knowledge Base (Authenticated)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/properties` | List properties |
| POST | `/api/v1/properties` | Add property listing |
| PATCH | `/api/v1/properties/{id}` | Update details |
| POST | `/api/v1/properties/{id}/upload` | Upload PDF → chunk → embed |
| DELETE | `/api/v1/properties/{id}/documents/{doc_id}` | Remove document |
| POST | `/api/v1/properties/search` | Vector similarity search (used by chatbot) |

#### Settings (Authenticated — Admin only)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/settings` | Org settings |
| PATCH | `/api/v1/settings` | Update chatbot language, follow-up config |
| POST | `/api/v1/settings/whatsapp/connect` | Configure WhatsApp Business number |

### Pagination Pattern

```json
GET /api/v1/leads?status=qualified&score_min=60&page=1&per_page=25&sort=-score

{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total": 142,
    "pages": 6
  }
}
```

---

## 4. AI Chatbot Workflow

### Conversation Engine Design

The chatbot uses **OpenAI function calling** to extract structured qualification data from natural conversation. This avoids rigid decision trees — the AI adapts to the lead's responses while systematically collecting the required signals.

### System Prompt Structure

```python
SYSTEM_PROMPT = """
You are Bahera, a friendly real estate assistant for {org_name}.
Your goal is to understand the buyer's needs through natural conversation.

RULES:
- Be warm, professional, and concise (2-3 sentences per message)
- Ask ONE question at a time
- Respond in the buyer's language
- If they ask about specific properties, use the property_search function
- Never pressure. If they're not ready, note that and close politely.
- After gathering enough info, call the complete_qualification function

QUALIFICATION TARGETS (collect all before completing):
- budget_range: Their price range (min-max in local currency)
- property_type: apartment / villa / townhouse / commercial
- preferred_location: Area or district name
- timeline: When they plan to buy (months)
- payment_method: cash / mortgage / installments
- purpose: investment / end_use / both
- bedrooms: Number of bedrooms needed (if residential)
"""
```

### Function Definitions

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "property_search",
            "description": "Search available properties matching buyer criteria",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "property_type": {"type": "string"},
                    "budget_max": {"type": "number"},
                    "bedrooms": {"type": "integer"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_qualification",
            "description": "Call when all qualification data has been collected",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget_min": {"type": "number"},
                    "budget_max": {"type": "number"},
                    "property_type": {"type": "string"},
                    "preferred_location": {"type": "string"},
                    "timeline_months": {"type": "integer"},
                    "payment_method": {"type": "string",
                        "enum": ["cash", "mortgage", "installments"]},
                    "purpose": {"type": "string",
                        "enum": ["investment", "end_use", "both"]},
                    "bedrooms": {"type": "integer"},
                    "notes": {"type": "string"}
                },
                "required": ["budget_max", "property_type",
                             "preferred_location", "timeline_months",
                             "payment_method", "purpose"]
            }
        }
    }
]
```

### RAG Property Search Pipeline

When the chatbot calls `property_search`:

1. **Query embedding**: Embed the search query using `text-embedding-3-small`
2. **Vector search**: `SELECT * FROM property_documents ORDER BY embedding <=> query_embedding LIMIT 5`
3. **Context injection**: Inject matched chunks into the next AI message as system context
4. **Response**: AI synthesizes a natural recommendation using the retrieved property data

### Conversation Flow State Machine

```
NEW → GREETING → QUALIFYING → [PROPERTY_SEARCH] → SCORING → COMPLETE
                     ↑              ↓
                     └── (loop) ────┘

States:
- NEW: Lead just arrived, no messages yet
- GREETING: First message sent, waiting for response
- QUALIFYING: Actively collecting qualification data (3-6 turns)
- PROPERTY_SEARCH: Lead asked about a property, RAG activated
- SCORING: All data collected, scoring in progress
- COMPLETE: Score assigned, agent notified
```

### Timeout & Abandonment Handling

- If lead doesn't respond within 2 hours: send a gentle nudge
- If no response after 24 hours: mark as "incomplete", score with available data
- If conversation exceeds 15 messages without completion: force-score and flag for manual review

---

## 5. Lead Scoring Algorithm

### Scoring Formula

```python
def calculate_lead_score(qualification_data: dict, conversation: list) -> int:
    score = 0

    # 1. Budget clarity (25 points)
    budget = qualification_data.get("budget_max")
    budget_min = qualification_data.get("budget_min")
    if budget and budget_min:
        score += 25  # Specific range given
    elif budget:
        score += 15  # Only max given
    else:
        score += 0   # No budget mentioned

    # 2. Timeline urgency (20 points)
    timeline = qualification_data.get("timeline_months")
    if timeline:
        if timeline <= 3:
            score += 20
        elif timeline <= 6:
            score += 14
        elif timeline <= 12:
            score += 8
        else:
            score += 3

    # 3. Payment method (20 points)
    payment = qualification_data.get("payment_method")
    payment_scores = {"cash": 20, "mortgage": 14, "installments": 10}
    score += payment_scores.get(payment, 0)

    # 4. Location specificity (15 points)
    location = qualification_data.get("preferred_location", "")
    if location:
        # More specific = higher score
        if len(location.split()) >= 2:  # "Dubai Marina" vs "Dubai"
            score += 15
        else:
            score += 8

    # 5. Engagement quality (10 points)
    user_messages = [m for m in conversation if m["role"] == "user"]
    avg_length = sum(len(m["message"]) for m in user_messages) / max(len(user_messages), 1)
    if avg_length > 50:
        score += 10  # Detailed responses
    elif avg_length > 20:
        score += 6
    else:
        score += 2

    # 6. Purpose clarity (10 points)
    purpose = qualification_data.get("purpose")
    purpose_scores = {"investment": 10, "both": 9, "end_use": 8}
    score += purpose_scores.get(purpose, 3)

    return min(score, 100)
```

### AI Confidence Adjustment

After the rule-based score, an OpenAI call reviews the full transcript and can adjust ±10 points:

```python
SCORING_PROMPT = """
Review this real estate lead conversation and assess buyer intent.
Current rule-based score: {score}/100

Adjust by -10 to +10 based on:
- Specificity of language (naming exact buildings, streets = +)
- Asking about payment plans, visit schedules, availability = +
- Vague answers, "just looking", reluctance to share info = -
- Urgency signals ("need to move", "offer expiring") = +

Return JSON: {"adjustment": <int>, "reason": "<brief explanation>"}
"""
```

---

## 6. CRM Dashboard Modules

### Module 1: Overview Dashboard

**KPI cards**: Total leads (today/week/month), average lead score, hot leads (80+), conversion rate, cost per qualified lead.

**Lead pipeline**: Kanban-style columns (New → Qualifying → Qualified → Contacted → Converted / Lost). Drag-and-drop status changes.

**Score distribution chart**: Histogram showing lead quality breakdown.

### Module 2: Lead Table

**Columns**: Name, phone, score (color-coded badge), source, status, assigned agent, created date.

**Filters**: Score range slider, status dropdown, source, date range, agent.

**Bulk actions**: Reassign agent, change status, export CSV.

### Module 3: Lead Detail

**Header**: Name, score badge, status, source, contact info, assigned agent.

**Qualification card**: Visual display of all collected data (budget, timeline, etc.).

**Chat transcript**: Full conversation with timestamps. Read-only for agents.

**Follow-up timeline**: Shows scheduled/sent follow-up messages with status.

**Agent notes**: Free-text area for manual notes.

### Module 4: Campaign Analytics

**Campaign list**: Name, source, budget, lead count, avg score, cost per lead, conversion rate.

**Drill-down**: Click campaign → see all leads from that campaign.

**Charts**: Cost per lead over time, score distribution per campaign, source comparison.

### Module 5: Properties & Knowledge Base

**Property list**: Name, location, price range, unit types, status.

**Document manager**: Upload PDFs, view processing status (pending → chunked → embedded).

**Preview**: See extracted text chunks and test search queries.

### Module 6: Settings

**Organization**: Name, logo, plan, billing.

**Team**: Invite agents, set assignment weights, activate/deactivate.

**Integrations**: WhatsApp Business connection, Meta Ads account link.

**Chatbot**: Language, custom greeting, qualification questions toggle.

---

## 7. Messaging Integrations

### WhatsApp Business Cloud API

**Setup**: Register on Meta Business Suite → Create WhatsApp Business Account → Get Phone Number ID and access token → Configure webhook URL.

**Inbound flow**:
1. WhatsApp message hits `POST /webhooks/meta/messaging`
2. Extract sender phone, message text, message type
3. Look up or create lead by phone + org
4. Route to chatbot engine
5. Send response via WhatsApp Cloud API `POST /v1/{phone_id}/messages`

**Message templates** (pre-approved by Meta):

| Template | Day | Content |
|----------|-----|---------|
| `follow_up_day1` | 1 | "Hi {name}, thanks for your interest in {property}. Our advisor {agent} will be in touch. Any questions?" |
| `follow_up_day3` | 3 | "Hi {name}, just checking in. Would you like to schedule a viewing or call with {agent}?" |
| `follow_up_day7` | 7 | "Hi {name}, we have some new options that match your criteria. Want me to share?" |

### Instagram Messaging API

Uses the same Meta webhook endpoint. Messages from Instagram DMs arrive with `messaging_product: "instagram"`. The chatbot engine handles them identically — the channel is tracked in the conversation record.

### Website Widget

A lightweight JavaScript snippet embeds a chat bubble on the client's website:

```html
<script src="https://app.bahera.ai/widget.js"
        data-org="ORG_UUID"
        data-lang="en">
</script>
```

The widget opens a chat interface that sends messages to `POST /webhooks/widget` with the org ID. Responses are pushed back via WebSocket or polling.

### Follow-Up Scheduler

APScheduler runs a job every 5 minutes:

```python
async def process_follow_ups():
    pending = await db.query(
        "SELECT * FROM follow_ups WHERE status = 'pending' "
        "AND scheduled_at <= NOW()"
    )
    for fu in pending:
        lead = await get_lead(fu.lead_id)
        if lead.status in ('lost', 'converted'):
            await mark_cancelled(fu.id)
            continue
        success = await send_whatsapp_template(
            phone=lead.phone,
            template=fu.template_key,
            params={"name": lead.name, "agent": lead.agent.name}
        )
        await update_follow_up(fu.id,
            status="sent" if success else "failed",
            sent_at=datetime.utcnow()
        )
```

---

## 8. Deployment Architecture

### Infrastructure

| Component | Service | Tier | Est. Cost/mo |
|-----------|---------|------|-------------|
| **Backend API** | Render.com (Web Service) | Starter ($7) | $7 |
| **Background Worker** | Render.com (Background Worker) | Starter ($7) | $7 |
| **Database + Auth + Storage** | Supabase | Pro ($25) | $25 |
| **Frontend** | Vercel | Pro ($20) | $20 |
| **Domain + DNS** | Cloudflare | Free | $0 |
| **AI** | OpenAI API | Pay-as-you-go | $50–200 |
| **WhatsApp** | Meta Cloud API | Per-conversation | $30–100 |

### Deployment Pipeline

```
GitHub Repo (monorepo)
├── /api          → Render auto-deploy on push to main
├── /dashboard    → Vercel auto-deploy on push to main
└── /widget       → Vercel (separate project)
```

**CI/CD**: Both Render and Vercel connect directly to GitHub. Push to `main` = production deploy. Use `develop` branch for staging.

### Environment Variables

```bash
# Backend (.env)
DATABASE_URL=postgresql://...@db.supabase.co:5432/postgres
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
OPENAI_API_KEY=sk-...
META_APP_SECRET=...
META_VERIFY_TOKEN=bahera_verify_2026
WHATSAPP_PHONE_ID=...
WHATSAPP_ACCESS_TOKEN=...
CORS_ORIGINS=https://app.bahera.ai
```

### Scaling Path

**Phase 1 (0–50 clients)**: Single Render instance + Supabase Pro. Handles ~100 concurrent chatbot sessions.

**Phase 2 (50–200 clients)**: Scale Render to Standard ($25/mo), add Redis for caching, upgrade Supabase to Team.

**Phase 3 (200+ clients)**: Consider splitting chatbot engine into a separate service, add queue (BullMQ or SQS) for webhook processing, move to dedicated PostgreSQL.

---

## 9. Security Considerations

### Authentication & Authorization

- **Supabase Auth** handles signup, login, password reset, and JWT issuance. No custom auth code needed.
- **Row-Level Security (RLS)** on all tables ensures tenants can only access their own data.
- **Role-based access**: Admin (full access), Agent (own leads + limited settings), Developer (property uploads only).
- **API middleware**: Every request validates JWT and resolves tenant context.

### Webhook Security

- **Meta webhooks**: Validate `X-Hub-Signature-256` header against `META_APP_SECRET` on every request.
- **Widget**: Rate-limit by IP (10 req/min), validate org UUID exists.

### Data Protection

- **Encryption at rest**: Supabase encrypts all data at rest (AES-256).
- **Encryption in transit**: All connections use TLS 1.2+.
- **PII handling**: Phone numbers and emails are stored as-is (needed for messaging). Consider field-level encryption for sensitive markets.
- **GDPR compliance**: Add data export endpoint (`GET /api/v1/leads/{id}/export`) and deletion endpoint (`DELETE /api/v1/leads/{id}/gdpr`).
- **Data retention**: Auto-archive leads older than 12 months. Configurable per org.

### API Security

- **Rate limiting**: 100 req/min per org for API, 30 req/min per IP for webhooks.
- **Input validation**: Pydantic schemas validate all inputs. SQL injection prevented by SQLAlchemy ORM.
- **CORS**: Restricted to `app.bahera.ai` and configured widget domains.
- **Secrets management**: All secrets in Render/Vercel environment variables, never in code.

### AI-Specific Security

- **Prompt injection defense**: System prompts include guardrails against manipulation. User messages are wrapped in clear delimiters.
- **Output filtering**: AI responses are checked for PII leakage and off-topic content before sending to leads.
- **Token limits**: Max 500 tokens per response, max 20 messages per conversation to prevent abuse.

---

## 10. Estimated Infrastructure Costs

### Monthly Cost Breakdown (MVP — up to 50 clients)

| Item | Service | Cost |
|------|---------|------|
| Backend hosting | Render Starter | $7 |
| Background worker | Render Starter | $7 |
| Database + Auth + Storage + Vectors | Supabase Pro | $25 |
| Frontend hosting | Vercel Pro | $20 |
| DNS + CDN | Cloudflare Free | $0 |
| OpenAI API (est. 50K messages/mo) | GPT-4o-mini + embeddings | $50–150 |
| WhatsApp Cloud API | Per-conversation pricing | $30–100 |
| Domain | Annual / 12 | ~$2 |
| **Total estimated** | | **$141–311/mo** |

### Cost Optimization Tips

- Use `gpt-4o-mini` for qualification conversations (80% cheaper than gpt-4o, sufficient quality for structured Q&A).
- Use `text-embedding-3-small` for vectors ($0.02/1M tokens vs $0.13 for large).
- Cache common property search results in-memory (TTL 1 hour) to reduce both DB and AI calls.
- WhatsApp: Use template messages (cheaper) for follow-ups; interactive messages only for qualification.

### Revenue Model Context

At $100–300/month per client subscription, 50 clients = $5,000–15,000/month revenue against $150–300 infrastructure cost. That's 95%+ gross margin before human costs.

---

## Appendix A: MVP Build Sequence

Recommended order for AI-assisted development:

| Week | Deliverable |
|------|-------------|
| 1 | Supabase project setup, DB schema, auth config, RLS policies |
| 2 | FastAPI skeleton, lead CRUD, webhook receivers (Meta Lead Ads) |
| 3 | AI chatbot engine with OpenAI function calling, basic scoring |
| 4 | WhatsApp integration (send/receive), follow-up scheduler |
| 5 | Next.js dashboard: lead table, lead detail, KPI cards |
| 6 | Property upload + RAG pipeline (PDF → chunks → embeddings → search) |
| 7 | Campaign analytics, agent assignment, settings page |
| 8 | Website widget, Instagram integration, polish + testing |

### Key Libraries

**Backend**: `fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `pydantic`, `openai`, `httpx`, `apscheduler`, `python-multipart`, `PyPDF2`, `tiktoken`

**Frontend**: `next`, `react`, `@supabase/supabase-js`, `tailwindcss`, `shadcn/ui`, `recharts`, `tanstack/react-query`, `zustand`

---

## Appendix B: Key Technical Decisions

| Decision | Choice | Why NOT the alternative |
|----------|--------|------------------------|
| Monolith vs Microservices | Monolith | No DevOps team, one deployment target |
| Supabase vs separate PG + Pinecone | Supabase | pgvector eliminates separate vector DB, Auth/Storage included |
| APScheduler vs Celery | APScheduler | No Redis needed, sufficient for MVP scale |
| OpenAI vs self-hosted LLM | OpenAI | Zero ML ops, best function calling support |
| Render vs AWS/GCP | Render | Git-push deploy, no IAM/VPC complexity |
| Next.js vs React SPA | Next.js | SSR for dashboard perf, Vercel integration |

---

*Document prepared for BAHERA founding team. Architecture optimized for AI-assisted development with no dedicated engineering team.*
