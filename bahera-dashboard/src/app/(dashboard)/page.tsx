// src/app/(dashboard)/page.tsx — Overview dashboard

"use client";

import { useEffect, useState } from "react";
import { api, OverviewStats, ScoreDistribution, Lead } from "@/lib/api";
import { KPICard, ScoreBadge, StatusBadge, SourceBadge } from "@/components/ui";
import { Users, TrendingUp, Flame, Target } from "lucide-react";
import Link from "next/link";

export default function OverviewPage() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [scoreDist, setScoreDist] = useState<ScoreDistribution | null>(null);
  const [recentLeads, setRecentLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getOverview(),
      api.getScoreDistribution(),
      api.getLeads({ per_page: "8", sort: "-created_at" }),
    ]).then(([overview, dist, leads]) => {
      setStats(overview);
      setScoreDist(dist);
      setRecentLeads(leads.data);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading dashboard...</div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Lead performance overview</p>
      </div>

      {/* KPI Grid */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard label="Leads today" value={stats.leads_today}
            icon={<Users size={18} />} />
          <KPICard label="This month" value={stats.leads_this_month}
            icon={<TrendingUp size={18} />} />
          <KPICard label="Hot leads" value={stats.hot_leads}
            icon={<Flame size={18} />} />
          <KPICard label="Conversion rate" value={stats.conversion_rate ? `${stats.conversion_rate}%` : "—"}
            icon={<Target size={18} />} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Score Distribution */}
        {scoreDist && (
          <div className="bg-white border border-gray-100 rounded-xl p-6">
            <h3 className="text-sm font-medium text-gray-900 mb-4">Score distribution</h3>
            <div className="space-y-3">
              {[
                { label: "Hot (80-100)", count: scoreDist.hot, color: "bg-emerald-500", total: Object.values(scoreDist).reduce((a, b) => a + b, 0) },
                { label: "Warm (60-79)", count: scoreDist.warm, color: "bg-blue-500", total: Object.values(scoreDist).reduce((a, b) => a + b, 0) },
                { label: "Nurture (30-59)", count: scoreDist.nurture, color: "bg-amber-500", total: Object.values(scoreDist).reduce((a, b) => a + b, 0) },
                { label: "Cold (0-29)", count: scoreDist.cold, color: "bg-gray-300", total: Object.values(scoreDist).reduce((a, b) => a + b, 0) },
              ].map(({ label, count, color, total }) => (
                <div key={label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600">{label}</span>
                    <span className="font-medium text-gray-900">{count}</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${color}`}
                      style={{ width: `${total > 0 ? (count / total) * 100 : 0}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Average Score */}
        <div className="bg-white border border-gray-100 rounded-xl p-6 flex flex-col items-center justify-center">
          <span className="text-sm text-gray-500 mb-2">Average lead score</span>
          <span className="text-5xl font-bold text-gray-900">{stats?.avg_score ?? "—"}</span>
          <span className="text-sm text-gray-400 mt-1">out of 100</span>
          <div className="mt-4 text-sm text-gray-500">
            {stats?.total_conversions || 0} total conversions
          </div>
        </div>

        {/* Quick stats */}
        <div className="bg-white border border-gray-100 rounded-xl p-6">
          <h3 className="text-sm font-medium text-gray-900 mb-4">This week</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">New leads</span>
              <span className="text-lg font-semibold">{stats?.leads_this_week || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Hot leads</span>
              <span className="text-lg font-semibold text-emerald-600">{stats?.hot_leads || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Conversions</span>
              <span className="text-lg font-semibold text-brand-600">{stats?.total_conversions || 0}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Leads Table */}
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-900">Recent leads</h3>
          <Link href="/leads" className="text-sm text-brand-600 hover:text-brand-700 font-medium">View all</Link>
        </div>
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-6 py-3 font-medium">Name</th>
              <th className="px-6 py-3 font-medium">Source</th>
              <th className="px-6 py-3 font-medium">Score</th>
              <th className="px-6 py-3 font-medium">Status</th>
              <th className="px-6 py-3 font-medium">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {recentLeads.map(lead => (
              <tr key={lead.id} className="hover:bg-gray-50/50 transition-colors">
                <td className="px-6 py-3">
                  <Link href={`/leads/${lead.id}`} className="text-sm font-medium text-gray-900 hover:text-brand-600">
                    {lead.name || lead.phone}
                  </Link>
                  <p className="text-xs text-gray-400">{lead.phone}</p>
                </td>
                <td className="px-6 py-3"><SourceBadge source={lead.source} /></td>
                <td className="px-6 py-3"><ScoreBadge score={lead.score} /></td>
                <td className="px-6 py-3"><StatusBadge status={lead.status} /></td>
                <td className="px-6 py-3 text-xs text-gray-500">
                  {new Date(lead.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
