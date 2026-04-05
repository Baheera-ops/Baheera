// src/app/(dashboard)/layout.tsx — Main dashboard shell with sidebar

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import clsx from "clsx";
import { useAuthStore } from "@/lib/store";
import {
  LayoutDashboard, Users, Inbox, BarChart3, Building2, Bot,
  Settings, LogOut, Megaphone, ChevronRight,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/",            label: "Overview",    icon: LayoutDashboard },
  { href: "/leads",       label: "Lead inbox",  icon: Inbox },
  { href: "/agents",      label: "Agents",      icon: Users },
  { href: "/campaigns",   label: "Campaigns",   icon: Megaphone },
  { href: "/properties",  label: "Properties",  icon: Building2 },
  { href: "/ai-training", label: "AI training",  icon: Bot },
  { href: "/settings",    label: "Settings",    icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, user, logout, hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
    if (!isAuthenticated) router.push("/login");
  }, [isAuthenticated]);

  if (!isAuthenticated) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Sidebar ────────────────────────────────────────────── */}
      <aside className="w-60 bg-white border-r border-gray-100 flex flex-col shrink-0">
        {/* Brand */}
        <div className="h-16 flex items-center px-6 border-b border-gray-100">
          <span className="text-xl font-bold text-brand-600 tracking-tight">Bahera</span>
          <span className="ml-1.5 text-[10px] bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded-full font-medium">AI</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link key={href} href={href}
                className={clsx(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                )}>
                <Icon size={18} strokeWidth={isActive ? 2 : 1.5} />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="p-3 border-t border-gray-100">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-sm font-medium text-brand-700">
              {user?.full_name?.charAt(0) || "U"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{user?.full_name}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email}</p>
            </div>
            <button onClick={logout} className="text-gray-400 hover:text-red-500 transition-colors" title="Logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main Content ───────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {/* Top header bar */}
        <header className="h-16 bg-white border-b border-gray-100 flex items-center px-8 sticky top-0 z-10">
          <nav className="flex items-center text-sm text-gray-500">
            <Link href="/" className="hover:text-gray-700">Dashboard</Link>
            {pathname !== "/" && (
              <>
                <ChevronRight size={14} className="mx-2 text-gray-300" />
                <span className="text-gray-900 font-medium capitalize">
                  {pathname.split("/").filter(Boolean)[0]?.replace(/-/g, " ")}
                </span>
              </>
            )}
          </nav>
        </header>

        {/* Page content */}
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
