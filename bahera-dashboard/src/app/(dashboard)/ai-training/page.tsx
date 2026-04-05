// src/app/(dashboard)/ai-training/page.tsx

"use client";

import { useState } from "react";
import { api, KBResult } from "@/lib/api";
import { Button, Input, EmptyState } from "@/components/ui";
import { Search, Bot, BookOpen, Zap } from "lucide-react";

export default function AITrainingPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KBResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setHasSearched(true);
    try {
      const res = await api.searchKnowledgeBase(query);
      setResults(res);
    } catch {
      setResults([]);
    }
    setSearching(false);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">AI chatbot training</h1>
        <p className="text-sm text-gray-500 mt-1">Manage your knowledge base and test the AI's understanding</p>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-purple-50 flex items-center justify-center"><BookOpen size={18} className="text-purple-600" /></div>
            <h3 className="text-sm font-medium text-gray-900">Knowledge base</h3>
          </div>
          <p className="text-sm text-gray-500">Upload property brochures, pricing sheets, and project details. The AI uses these to answer buyer questions accurately.</p>
          <p className="text-xs text-gray-400 mt-3">Manage documents in Properties &rarr; Documents</p>
        </div>

        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center"><Bot size={18} className="text-blue-600" /></div>
            <h3 className="text-sm font-medium text-gray-900">Qualification flow</h3>
          </div>
          <p className="text-sm text-gray-500">The AI collects 6 data points through natural conversation: budget, property type, location, timeline, payment method, and purpose.</p>
          <p className="text-xs text-gray-400 mt-3">Configurable in Settings &rarr; Chatbot</p>
        </div>

        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center"><Zap size={18} className="text-amber-600" /></div>
            <h3 className="text-sm font-medium text-gray-900">Lead scoring</h3>
          </div>
          <p className="text-sm text-gray-500">Each lead receives a 0-100 score based on qualification responses and conversation engagement, with an AI sentiment adjustment of up to 10 points.</p>
          <p className="text-xs text-gray-400 mt-3">Score thresholds: Hot 80+, Warm 60+, Nurture 30+</p>
        </div>
      </div>

      {/* Knowledge base tester */}
      <div className="bg-white border border-gray-100 rounded-xl p-6">
        <h3 className="text-sm font-medium text-gray-900 mb-1">Test knowledge base</h3>
        <p className="text-sm text-gray-500 mb-4">Search your uploaded documents to verify the AI can find the right information.</p>

        <form onSubmit={handleSearch} className="flex gap-3 mb-6">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input type="text" value={query} onChange={e => setQuery(e.target.value)}
              placeholder='Try: "What is the payment plan for Marina Heights?" or "2BR apartments under 1.5M"'
              className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20" />
          </div>
          <Button type="submit" disabled={searching || !query.trim()}>
            {searching ? "Searching..." : "Search"}
          </Button>
        </form>

        {/* Results */}
        {hasSearched && results.length === 0 && !searching && (
          <div className="text-center py-8">
            <p className="text-sm text-gray-500">No matching documents found.</p>
            <p className="text-xs text-gray-400 mt-1">Upload property PDFs in the Properties section to populate the knowledge base.</p>
          </div>
        )}

        {results.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 mb-2">{results.length} relevant chunks found</p>
            {results.map((r, i) => (
              <div key={i} className="border border-gray-100 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-900">{r.property_name}</span>
                  <span className="text-xs text-gray-400">{r.location} &middot; {Math.round(r.similarity * 100)}% match</span>
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">{r.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
