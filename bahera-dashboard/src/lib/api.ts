// src/lib/api.ts — Typed API client for the FastAPI backend

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || `API error ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
  }

  // Auth
  signup(data: { email: string; password: string; full_name: string; agency_name: string }) {
    return this.request<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify(data) });
  }
  login(data: { email: string; password: string }) {
    return this.request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) });
  }
  getProfile() {
    return this.request<User>("/auth/me");
  }

  // Leads
  getLeads(params?: Record<string, string>) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request<PaginatedResponse<Lead>>(`/leads${qs}`);
  }
  getLead(id: string) {
    return this.request<LeadDetail>(`/leads/${id}`);
  }
  createLead(data: Partial<Lead>) {
    return this.request<Lead>("/leads", { method: "POST", body: JSON.stringify(data) });
  }
  updateLead(id: string, data: Partial<Lead>) {
    return this.request<Lead>(`/leads/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }
  getLeadConversations(id: string) {
    return this.request<Conversation[]>(`/leads/${id}/conversations`);
  }
  getConversationMessages(leadId: string, convId: string) {
    return this.request<Message[]>(`/leads/${leadId}/conversations/${convId}/messages`);
  }
  getLeadStats() {
    return this.request<Record<string, number>>("/leads/stats/overview");
  }

  // Chatbot
  sendMessage(leadId: string, message: string, channel = "web_widget") {
    return this.request<ChatbotResponse>(`/chatbot/${leadId}/message`, {
      method: "POST", body: JSON.stringify({ message, channel }),
    });
  }

  // Agents
  getAgents() {
    return this.request<Agent[]>("/agents");
  }
  createAgent(data: Partial<Agent>) {
    return this.request<Agent>("/agents", { method: "POST", body: JSON.stringify(data) });
  }
  updateAgent(id: string, data: Partial<Agent>) {
    return this.request<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }
  getAgentStats(id: string) {
    return this.request<AgentStats>(`/agents/${id}/stats`);
  }
  getAgentLeads(id: string) {
    return this.request<Lead[]>(`/agents/${id}/leads`);
  }

  // Campaigns
  getCampaigns(params?: Record<string, string>) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request<PaginatedResponse<Campaign>>(`/campaigns${qs}`);
  }
  createCampaign(data: Partial<Campaign>) {
    return this.request<Campaign>("/campaigns", { method: "POST", body: JSON.stringify(data) });
  }
  updateCampaign(id: string, data: Partial<Campaign>) {
    return this.request<Campaign>(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }
  getCampaignAnalytics(id: string) {
    return this.request<CampaignDetail>(`/campaigns/${id}/analytics`);
  }

  // Properties
  getProperties(params?: Record<string, string>) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request<Property[]>(`/properties${qs}`);
  }
  createProperty(data: Partial<Property>) {
    return this.request<Property>("/properties", { method: "POST", body: JSON.stringify(data) });
  }
  updateProperty(id: string, data: Partial<Property>) {
    return this.request<Property>(`/properties/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }
  getPropertyDocuments(id: string) {
    return this.request<Document[]>(`/properties/${id}/documents`);
  }
  uploadDocument(propertyId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/properties/${propertyId}/upload`, {
      method: "POST", body: form,
      headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
    }).then(r => r.json());
  }
  searchKnowledgeBase(query: string) {
    return this.request<KBResult[]>(`/properties/search?query=${encodeURIComponent(query)}`);
  }

  // Analytics
  getOverview() {
    return this.request<OverviewStats>("/analytics/overview");
  }
  getScoreDistribution() {
    return this.request<ScoreDistribution>("/analytics/score-distribution");
  }
  getCampaignComparison() {
    return this.request<CampaignMetrics[]>("/analytics/campaigns");
  }
}

export const api = new ApiClient();

// ─── TypeScript interfaces ────────────────────────────────────────

export interface AuthResponse { access_token: string; user: User }
export interface User { id: string; email: string; full_name: string; role: string; agency_id: string; is_active: boolean; created_at: string }
export interface PaginatedResponse<T> { data: T[]; pagination: { page: number; per_page: number; total: number; pages: number } }
export interface Lead { id: string; agency_id: string; name: string | null; phone: string; email: string | null; source: string; status: string; score: number | null; qualification_data: Record<string, any>; language: string | null; agent_id: string | null; campaign_id: string | null; created_at: string; qualified_at: string | null }
export interface LeadDetail extends Lead { conversations: Conversation[]; scores: LeadScore[]; agent: Agent | null }
export interface LeadScore { id: string; total_score: number; budget_score: number; timeline_score: number; payment_score: number; location_score: number; engagement_score: number; purpose_score: number; ai_adjustment: number; ai_reasoning: string | null; version: number; is_current: boolean; scored_at: string }
export interface Conversation { id: string; lead_id: string; channel: string; status: string; message_count: number; started_at: string; last_message_at: string | null }
export interface Message { id: string; role: string; content: string; message_type: string; created_at: string }
export interface ChatbotResponse { response: string; lead_id: string; conversation_id: string; qualification_complete: boolean; score: number | null; assigned_agent: string | null }
export interface Agent { id: string; agency_id: string; name: string; email: string | null; phone: string | null; specialization: string | null; assignment_weight: number; is_active: boolean; is_available: boolean; total_leads_assigned: number; total_leads_converted: number; active_lead_count: number; created_at: string }
export interface AgentStats { total_leads: number; converted: number; active: number; avg_lead_score: number | null; conversion_rate: number }
export interface Campaign { id: string; agency_id: string; name: string; source: string; budget_total: number | null; budget_spent: number; currency: string; is_active: boolean; total_leads: number; qualified_leads: number; converted_leads: number; avg_lead_score: number | null; cost_per_lead: number | null; conversion_rate: number | null; start_date: string | null; end_date: string | null; created_at: string }
export interface CampaignDetail { campaign: Campaign; score_distribution: ScoreDistribution }
export interface CampaignMetrics { campaign_id: string; campaign_name: string; total_leads: number; qualified_leads: number; converted_leads: number; avg_score: number | null; cost_per_lead: number | null; cost_per_qualified: number | null }
export interface Property { id: string; agency_id: string; name: string; location: string; property_type: string; bedrooms_min: number | null; bedrooms_max: number | null; price_from: number; price_to: number | null; currency: string; payment_plan: string | null; amenities: string[]; is_active: boolean; created_at: string }
export interface Document { id: string; file_name: string; file_type: string; processing_status: string; chunk_count: number; uploaded_at: string }
export interface KBResult { content: string; property_name: string; location: string; similarity: number; metadata: Record<string, any> }
export interface OverviewStats { leads_today: number; leads_this_week: number; leads_this_month: number; avg_score: number | null; hot_leads: number; total_conversions: number; conversion_rate: number | null }
export interface ScoreDistribution { hot: number; warm: number; nurture: number; cold: number; unscored: number }
