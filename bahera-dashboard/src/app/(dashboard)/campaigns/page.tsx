// src/app/(dashboard)/campaigns/page.tsx

"use client";

import { useEffect, useState } from "react";
import { api, Campaign, CampaignMetrics, PaginatedResponse } from "@/lib/api";
import { Button, Modal, Input, Select, EmptyState, ScoreBadge } from "@/components/ui";
import { Plus, TrendingUp, DollarSign, Users, Target } from "lucide-react";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [metrics, setMetrics] = useState<CampaignMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", source: "meta_lead_ad", budget_total: "", currency: "AED" });

  useEffect(() => {
    Promise.all([
      api.getCampaigns({ per_page: "50" }),
      api.getCampaignComparison(),
    ]).then(([camp, met]) => {
      setCampaigns(camp.data);
      setMetrics(met);
    }).finally(() => setLoading(false));
  }, []);

  const handleCreate = async () => {
    await api.createCampaign({
      ...form,
      budget_total: form.budget_total ? Number(form.budget_total) : undefined,
    });
    setShowAdd(false);
    const camp = await api.getCampaigns({ per_page: "50" });
    setCampaigns(camp.data);
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading campaigns...</div>;

  // Aggregate totals
  const totalSpent = campaigns.reduce((s, c) => s + (c.budget_spent || 0), 0);
  const totalLeads = campaigns.reduce((s, c) => s + c.total_leads, 0);
  const totalConverted = campaigns.reduce((s, c) => s + c.converted_leads, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Campaign analytics</h1>
          <p className="text-sm text-gray-500 mt-1">{campaigns.length} campaigns tracked</p>
        </div>
        <Button onClick={() => setShowAdd(true)}><Plus size={16} className="mr-1.5 -ml-0.5" />Add campaign</Button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="text-sm text-gray-500 mb-1 flex items-center gap-1.5"><DollarSign size={14} />Total spend</div>
          <div className="text-2xl font-semibold">{totalSpent.toLocaleString()} AED</div>
        </div>
        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="text-sm text-gray-500 mb-1 flex items-center gap-1.5"><Users size={14} />Total leads</div>
          <div className="text-2xl font-semibold">{totalLeads}</div>
        </div>
        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="text-sm text-gray-500 mb-1 flex items-center gap-1.5"><Target size={14} />Conversions</div>
          <div className="text-2xl font-semibold text-emerald-600">{totalConverted}</div>
        </div>
        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="text-sm text-gray-500 mb-1 flex items-center gap-1.5"><TrendingUp size={14} />Avg cost/lead</div>
          <div className="text-2xl font-semibold">{totalLeads > 0 ? Math.round(totalSpent / totalLeads) : "—"}</div>
        </div>
      </div>

      {/* Campaign comparison table */}
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-900">Campaign performance</h3>
        </div>
        {metrics.length === 0 ? (
          <EmptyState title="No campaign data" description="Create a campaign and start generating leads." />
        ) : (
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-100">
                <th className="px-6 py-3 font-medium">Campaign</th>
                <th className="px-6 py-3 font-medium text-right">Leads</th>
                <th className="px-6 py-3 font-medium text-right">Qualified</th>
                <th className="px-6 py-3 font-medium text-right">Converted</th>
                <th className="px-6 py-3 font-medium text-right">Avg score</th>
                <th className="px-6 py-3 font-medium text-right">Cost/lead</th>
                <th className="px-6 py-3 font-medium text-right">Cost/qualified</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {metrics.map(m => (
                <tr key={m.campaign_id} className="hover:bg-gray-50/50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{m.campaign_name}</td>
                  <td className="px-6 py-4 text-sm text-right">{m.total_leads}</td>
                  <td className="px-6 py-4 text-sm text-right text-blue-600">{m.qualified_leads}</td>
                  <td className="px-6 py-4 text-sm text-right text-emerald-600">{m.converted_leads}</td>
                  <td className="px-6 py-4 text-right">{m.avg_score ? <ScoreBadge score={Math.round(m.avg_score)} /> : "—"}</td>
                  <td className="px-6 py-4 text-sm text-right">{m.cost_per_lead ? `${Math.round(m.cost_per_lead)} AED` : "—"}</td>
                  <td className="px-6 py-4 text-sm text-right">{m.cost_per_qualified ? `${Math.round(m.cost_per_qualified)} AED` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Create campaign">
        <div className="space-y-4">
          <Input label="Campaign name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
          <Select label="Source" value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} options={[
            { value: "meta_lead_ad", label: "Meta Lead Ad" }, { value: "whatsapp", label: "WhatsApp" },
            { value: "instagram_dm", label: "Instagram" }, { value: "web_widget", label: "Website" },
          ]} />
          <Input label="Budget (optional)" type="number" value={form.budget_total}
            onChange={e => setForm({ ...form, budget_total: e.target.value })} placeholder="e.g., 50000" />
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.name}>Create</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
