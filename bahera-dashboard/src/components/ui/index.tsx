// src/components/ui/index.tsx — All shared UI components

"use client";

import { ReactNode, useState } from "react";
import clsx from "clsx";

// ═══════════════════════════════════════════════════════════════════
// KPI Card — Metric display for dashboard
// ═══════════════════════════════════════════════════════════════════

export function KPICard({ label, value, change, icon }: {
  label: string; value: string | number; change?: string; icon?: ReactNode;
}) {
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-500">{label}</span>
        {icon && <span className="text-gray-400">{icon}</span>}
      </div>
      <div className="text-2xl font-semibold text-gray-900">{value}</div>
      {change && (
        <span className={clsx("text-xs mt-1 inline-block", change.startsWith("+") ? "text-green-600" : "text-red-500")}>
          {change} vs last period
        </span>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Score Badge — Color-coded lead score display
// ═══════════════════════════════════════════════════════════════════

export function ScoreBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">Unscored</span>;
  }

  const tier = score >= 80 ? "hot" : score >= 60 ? "warm" : score >= 30 ? "nurture" : "cold";
  const styles = {
    hot:     "bg-emerald-50 text-emerald-700 border-emerald-200",
    warm:    "bg-blue-50 text-blue-700 border-blue-200",
    nurture: "bg-amber-50 text-amber-700 border-amber-200",
    cold:    "bg-gray-50 text-gray-500 border-gray-200",
  };

  return (
    <span className={clsx("inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border", styles[tier])}>
      <span className={clsx("w-1.5 h-1.5 rounded-full", {
        "bg-emerald-500": tier === "hot", "bg-blue-500": tier === "warm",
        "bg-amber-500": tier === "nurture", "bg-gray-400": tier === "cold",
      })} />
      {score}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Status Badge — Lead status display
// ═══════════════════════════════════════════════════════════════════

export function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    new:          "bg-purple-50 text-purple-700",
    qualifying:   "bg-blue-50 text-blue-700",
    qualified:    "bg-emerald-50 text-emerald-700",
    contacted:    "bg-cyan-50 text-cyan-700",
    in_progress:  "bg-amber-50 text-amber-700",
    converted:    "bg-green-50 text-green-700",
    lost:         "bg-red-50 text-red-600",
    archived:     "bg-gray-50 text-gray-500",
  };

  return (
    <span className={clsx("inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium capitalize", styles[status] || styles.new)}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Source Badge — Lead source channel indicator
// ═══════════════════════════════════════════════════════════════════

export function SourceBadge({ source }: { source: string }) {
  const labels: Record<string, string> = {
    meta_lead_ad: "Meta Ad",  whatsapp: "WhatsApp",
    instagram_dm: "Instagram", web_widget: "Website",
    manual: "Manual", api: "API",
  };
  return <span className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded">{labels[source] || source}</span>;
}

// ═══════════════════════════════════════════════════════════════════
// Chat Bubble — Message display for conversation transcript
// ═══════════════════════════════════════════════════════════════════

export function ChatBubble({ role, content, timestamp }: {
  role: string; content: string; timestamp: string;
}) {
  const isUser = role === "user";
  return (
    <div className={clsx("flex mb-3", isUser ? "justify-end" : "justify-start")}>
      <div className={clsx(
        "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
        isUser ? "bg-brand-600 text-white rounded-br-md" : "bg-gray-100 text-gray-800 rounded-bl-md"
      )}>
        <p className="whitespace-pre-wrap">{content}</p>
        <p className={clsx("text-[10px] mt-1", isUser ? "text-brand-200" : "text-gray-400")}>
          {new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Modal — Reusable modal dialog
// ═══════════════════════════════════════════════════════════════════

export function Modal({ open, onClose, title, children, size = "md" }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; size?: "sm" | "md" | "lg";
}) {
  if (!open) return null;
  const widths = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl" };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className={clsx("relative bg-white rounded-2xl shadow-xl w-full", widths[size])}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>
        <div className="px-6 py-4">{children}</div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Empty State — Friendly placeholder when no data
// ═══════════════════════════════════════════════════════════════════

export function EmptyState({ title, description, action }: {
  title: string; description: string; action?: ReactNode;
}) {
  return (
    <div className="text-center py-12 px-6">
      <div className="w-12 h-12 rounded-full bg-gray-100 mx-auto mb-4 flex items-center justify-center">
        <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
      </div>
      <h3 className="text-sm font-medium text-gray-900 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 mb-4">{description}</p>
      {action}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Pagination — Page navigation controls
// ═══════════════════════════════════════════════════════════════════

export function Pagination({ page, pages, total, onPageChange }: {
  page: number; pages: number; total: number; onPageChange: (p: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
      <span className="text-sm text-gray-500">{total} results</span>
      <div className="flex gap-1">
        <button onClick={() => onPageChange(page - 1)} disabled={page <= 1}
          className="px-3 py-1 text-sm rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
          Prev
        </button>
        <span className="px-3 py-1 text-sm text-gray-600">
          {page} / {pages}
        </span>
        <button onClick={() => onPageChange(page + 1)} disabled={page >= pages}
          className="px-3 py-1 text-sm rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
          Next
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Button — Consistent button styling
// ═══════════════════════════════════════════════════════════════════

export function Button({ children, variant = "primary", size = "md", className = "", ...props }: {
  children: ReactNode; variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md"; className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const styles = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-sm",
    secondary: "bg-white text-gray-700 border border-gray-200 hover:bg-gray-50",
    ghost: "text-gray-600 hover:bg-gray-100",
    danger: "bg-red-600 text-white hover:bg-red-700",
  };
  const sizes = { sm: "px-3 py-1.5 text-sm", md: "px-4 py-2 text-sm" };

  return (
    <button className={clsx("rounded-lg font-medium transition-colors disabled:opacity-50", styles[variant], sizes[size], className)} {...props}>
      {children}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Input — Form input with label
// ═══════════════════════════════════════════════════════════════════

export function Input({ label, error, ...props }: { label?: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      {label && <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>}
      <input className={clsx(
        "w-full px-3 py-2 border rounded-lg text-sm transition-colors outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500",
        error ? "border-red-300" : "border-gray-200"
      )} {...props} />
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Select — Dropdown select with label
// ═══════════════════════════════════════════════════════════════════

export function Select({ label, options, ...props }: {
  label?: string; options: { value: string; label: string }[];
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div>
      {label && <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>}
      <select className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500" {...props}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
