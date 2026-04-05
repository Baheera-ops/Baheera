// src/app/(dashboard)/agents/page.tsx

"use client";

import { useEffect, useState } from "react";
import { api, Agent } from "@/lib/api";
import { Button, Modal, Input, EmptyState } from "@/components/ui";
import { Plus, UserCheck, UserX } from "lucide-react";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", specialization: "", assignment_weight: 5 });

  const load = () => api.getAgents().then(setAgents).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    await api.createAgent(form);
    setShowAdd(false);
    setForm({ name: "", email: "", phone: "", specialization: "", assignment_weight: 5 });
    load();
  };

  const toggleActive = async (agent: Agent) => {
    await api.updateAgent(agent.id, { is_active: !agent.is_active });
    load();
  };

  const toggleAvailable = async (agent: Agent) => {
    await api.updateAgent(agent.id, { is_available: !agent.is_available });
    load();
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading agents...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Agent management</h1>
          <p className="text-sm text-gray-500 mt-1">{agents.length} team members</p>
        </div>
        <Button onClick={() => setShowAdd(true)}><Plus size={16} className="mr-1.5 -ml-0.5" />Add agent</Button>
      </div>

      {agents.length === 0 ? (
        <EmptyState title="No agents yet" description="Add your first team member to start assigning leads."
          action={<Button onClick={() => setShowAdd(true)}>Add agent</Button>} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {agents.map(agent => (
            <div key={agent.id} className="bg-white border border-gray-100 rounded-xl p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-sm font-semibold text-brand-700">
                    {agent.name.charAt(0)}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">{agent.name}</p>
                    <p className="text-xs text-gray-500">{agent.specialization || "General"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {agent.is_active ? (
                    <span className="w-2 h-2 rounded-full bg-green-400" title="Active" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-gray-300" title="Inactive" />
                  )}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="text-center">
                  <p className="text-lg font-semibold text-gray-900">{agent.total_leads_assigned}</p>
                  <p className="text-xs text-gray-500">Assigned</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-semibold text-emerald-600">{agent.total_leads_converted}</p>
                  <p className="text-xs text-gray-500">Converted</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-semibold text-blue-600">{agent.active_lead_count}</p>
                  <p className="text-xs text-gray-500">Active</p>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs text-gray-500 mb-3">
                <span>Weight: {agent.assignment_weight}/10</span>
                <span>{agent.email}</span>
              </div>

              <div className="flex gap-2">
                <Button variant={agent.is_available ? "secondary" : "ghost"} size="sm" className="flex-1"
                  onClick={() => toggleAvailable(agent)}>
                  {agent.is_available ? "Available" : "On break"}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => toggleActive(agent)}>
                  {agent.is_active ? <UserCheck size={14} /> : <UserX size={14} />}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add new agent">
        <div className="space-y-4">
          <Input label="Full name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
          <Input label="Email" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
          <Input label="Phone" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} />
          <Input label="Specialization" placeholder="e.g., luxury, off-plan, commercial"
            value={form.specialization} onChange={e => setForm({ ...form, specialization: e.target.value })} />
          <Input label="Assignment weight (1-10)" type="number" min={1} max={10}
            value={form.assignment_weight} onChange={e => setForm({ ...form, assignment_weight: Number(e.target.value) })} />
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.name}>Add agent</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
