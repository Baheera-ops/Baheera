// src/app/(dashboard)/leads/page.tsx — Lead inbox with filters

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Lead, PaginatedResponse } from "@/lib/api";
import { ScoreBadge, StatusBadge, SourceBadge, Button, Pagination, EmptyState, Input } from "@/components/ui";
import { Search, SlidersHorizontal, Plus, Download } from "lucide-react";

const STATUS_OPTIONS = ["all", "new", "qualifying", "qualified", "contacted", "in_progress", "converted", "lost"];
const SOURCE_OPTIONS = ["all", "meta_lead_ad", "whatsapp", "instagram_dm", "web_widget", "manual"];

export default function LeadsPage() {
  const [data, setData] = useState<PaginatedResponse<Lead> | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [sortBy, setSortBy] = useState("-created_at");

  const fetchLeads = () => {
    setLoading(true);
    const params: Record<string, string> = {
      page: String(page), per_page: "20", sort: sortBy,
    };
    if (search) params.search = search;
    if (statusFilter !== "all") params.status = statusFilter;
    if (sourceFilter !== "all") params.source = sourceFilter;

    api.getLeads(params).then(setData).finally(() => setLoading(false));
  };

  useEffect(() => { fetchLeads(); }, [page, statusFilter, sourceFilter, sortBy]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchLeads();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Lead inbox</h1>
          <p className="text-sm text-gray-500 mt-1">
            {data?.pagination.total || 0} total leads
          </p>
        </div>
        <Button variant="primary">
          <Plus size={16} className="mr-1.5 -ml-0.5" />Add lead
        </Button>
      </div>

      {/* Filters bar */}
      <div className="bg-white border border-gray-100 rounded-xl p-4">
        <div className="flex flex-wrap gap-3 items-center">
          <form onSubmit={handleSearch} className="relative flex-1 min-w-[200px]">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input type="text" placeholder="Search by name, phone, email..."
              value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20" />
          </form>

          <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
            {STATUS_OPTIONS.map(s => (
              <option key={s} value={s}>{s === "all" ? "All statuses" : s.replace(/_/g, " ")}</option>
            ))}
          </select>

          <select value={sourceFilter} onChange={e => { setSourceFilter(e.target.value); setPage(1); }}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
            {SOURCE_OPTIONS.map(s => (
              <option key={s} value={s}>{s === "all" ? "All sources" : s.replace(/_/g, " ")}</option>
            ))}
          </select>

          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
            <option value="-created_at">Newest first</option>
            <option value="created_at">Oldest first</option>
            <option value="-score">Highest score</option>
            <option value="score">Lowest score</option>
          </select>
        </div>
      </div>

      {/* Leads table */}
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-gray-400">Loading leads...</div>
        ) : !data?.data.length ? (
          <EmptyState title="No leads found" description="Adjust your filters or wait for new leads to come in." />
        ) : (
          <>
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-100">
                  <th className="px-6 py-3 font-medium">Lead</th>
                  <th className="px-6 py-3 font-medium">Source</th>
                  <th className="px-6 py-3 font-medium">Score</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium">Qualification</th>
                  <th className="px-6 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {data.data.map(lead => (
                  <tr key={lead.id} className="hover:bg-gray-50/50 transition-colors group">
                    <td className="px-6 py-4">
                      <Link href={`/leads/${lead.id}`} className="block">
                        <span className="text-sm font-medium text-gray-900 group-hover:text-brand-600 transition-colors">
                          {lead.name || "Unknown"}
                        </span>
                        <span className="block text-xs text-gray-400 mt-0.5">{lead.phone}</span>
                        {lead.email && <span className="block text-xs text-gray-400">{lead.email}</span>}
                      </Link>
                    </td>
                    <td className="px-6 py-4"><SourceBadge source={lead.source} /></td>
                    <td className="px-6 py-4"><ScoreBadge score={lead.score} /></td>
                    <td className="px-6 py-4"><StatusBadge status={lead.status} /></td>
                    <td className="px-6 py-4">
                      {lead.qualification_data?.budget_max && (
                        <span className="text-xs text-gray-500">
                          Budget: {Number(lead.qualification_data.budget_max).toLocaleString()} {lead.qualification_data.budget_currency || "AED"}
                        </span>
                      )}
                      {lead.qualification_data?.preferred_location && (
                        <span className="block text-xs text-gray-400">{lead.qualification_data.preferred_location}</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs text-gray-500">
                      {new Date(lead.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.pagination && (
              <Pagination page={data.pagination.page} pages={data.pagination.pages}
                total={data.pagination.total} onPageChange={setPage} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
