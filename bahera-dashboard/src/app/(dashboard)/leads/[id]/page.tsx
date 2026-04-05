// src/app/(dashboard)/leads/[id]/page.tsx — Full lead detail

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, LeadDetail, Message } from "@/lib/api";
import { ScoreBadge, StatusBadge, SourceBadge, ChatBubble, Button, Select } from "@/components/ui";
import { ArrowLeft, Phone, Mail, MapPin, Calendar, Banknote, Home, Clock } from "lucide-react";

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getLead(id).then(async (data) => {
      setLead(data);
      if (data.conversations.length > 0) {
        const msgs = await api.getConversationMessages(id, data.conversations[0].id);
        setMessages(msgs);
      }
    }).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading lead...</div>;
  if (!lead) return <div className="text-center py-12 text-gray-500">Lead not found</div>;

  const q = lead.qualification_data || {};
  const currentScore = lead.scores?.find(s => s.is_current);

  const handleStatusChange = async (newStatus: string) => {
    await api.updateLead(id, { status: newStatus });
    setLead({ ...lead, status: newStatus });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900">{lead.name || lead.phone}</h1>
            <ScoreBadge score={lead.score} />
            <StatusBadge status={lead.status} />
          </div>
          <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
            <span className="flex items-center gap-1"><Phone size={13} />{lead.phone}</span>
            {lead.email && <span className="flex items-center gap-1"><Mail size={13} />{lead.email}</span>}
            <SourceBadge source={lead.source} />
          </div>
        </div>
        <Select value={lead.status} onChange={e => handleStatusChange(e.target.value)} options={[
          { value: "new", label: "New" }, { value: "qualifying", label: "Qualifying" },
          { value: "qualified", label: "Qualified" }, { value: "contacted", label: "Contacted" },
          { value: "in_progress", label: "In progress" }, { value: "converted", label: "Converted" },
          { value: "lost", label: "Lost" },
        ]} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Qualification + Score */}
        <div className="space-y-6">
          {/* Qualification data card */}
          <div className="bg-white border border-gray-100 rounded-xl p-6">
            <h3 className="text-sm font-medium text-gray-900 mb-4">Qualification data</h3>
            <div className="space-y-3">
              {[
                { icon: Banknote, label: "Budget", value: q.budget_max ? `${Number(q.budget_max).toLocaleString()} ${q.budget_currency || "AED"}` : null },
                { icon: Home, label: "Property type", value: q.property_type },
                { icon: MapPin, label: "Location", value: q.preferred_location },
                { icon: Calendar, label: "Timeline", value: q.timeline_months ? `${q.timeline_months} months` : null },
                { icon: Banknote, label: "Payment", value: q.payment_method },
                { icon: Home, label: "Purpose", value: q.purpose },
                { icon: Home, label: "Bedrooms", value: q.bedrooms },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="flex items-start gap-3">
                  <Icon size={16} className="text-gray-400 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-xs text-gray-500">{label}</span>
                    <p className="text-sm font-medium text-gray-900">{value || "—"}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Score breakdown card */}
          {currentScore && (
            <div className="bg-white border border-gray-100 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-gray-900">Score breakdown</h3>
                <span className="text-2xl font-bold text-gray-900">{currentScore.total_score}</span>
              </div>
              <div className="space-y-2.5">
                {[
                  { label: "Budget clarity", score: currentScore.budget_score, max: 25 },
                  { label: "Timeline urgency", score: currentScore.timeline_score, max: 20 },
                  { label: "Payment method", score: currentScore.payment_score, max: 20 },
                  { label: "Location specificity", score: currentScore.location_score, max: 15 },
                  { label: "Engagement quality", score: currentScore.engagement_score, max: 10 },
                  { label: "Purpose clarity", score: currentScore.purpose_score, max: 10 },
                ].map(({ label, score, max }) => (
                  <div key={label}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-500">{label}</span>
                      <span className="font-medium text-gray-700">{score}/{max}</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-brand-500 rounded-full" style={{ width: `${(score / max) * 100}%` }} />
                    </div>
                  </div>
                ))}
                {currentScore.ai_adjustment !== 0 && (
                  <div className="pt-2 mt-2 border-t border-gray-100">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-500">AI adjustment</span>
                      <span className={`font-medium ${currentScore.ai_adjustment > 0 ? "text-green-600" : "text-red-500"}`}>
                        {currentScore.ai_adjustment > 0 ? "+" : ""}{currentScore.ai_adjustment}
                      </span>
                    </div>
                    {currentScore.ai_reasoning && (
                      <p className="text-xs text-gray-400 mt-1 italic">{currentScore.ai_reasoning}</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Agent card */}
          {lead.agent && (
            <div className="bg-white border border-gray-100 rounded-xl p-6">
              <h3 className="text-sm font-medium text-gray-900 mb-3">Assigned agent</h3>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-sm font-medium text-brand-700">
                  {lead.agent.name.charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900">{lead.agent.name}</p>
                  <p className="text-xs text-gray-500">{lead.agent.specialization || "General"}</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right column: Conversation transcript */}
        <div className="lg:col-span-2">
          <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-900">
                Conversation
                {lead.conversations.length > 0 && (
                  <span className="text-gray-400 font-normal ml-2">
                    {lead.conversations[0].message_count} messages via {lead.conversations[0].channel.replace(/_/g, " ")}
                  </span>
                )}
              </h3>
              {lead.conversations.length > 0 && (
                <span className="text-xs text-gray-400">
                  Started {new Date(lead.conversations[0].started_at).toLocaleDateString()}
                </span>
              )}
            </div>

            <div className="p-6 max-h-[600px] overflow-y-auto">
              {messages.length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">
                  No conversation yet
                </div>
              ) : (
                messages.map(msg => (
                  <ChatBubble key={msg.id} role={msg.role} content={msg.content} timestamp={msg.created_at} />
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
