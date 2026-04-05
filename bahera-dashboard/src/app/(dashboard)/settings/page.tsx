// src/app/(dashboard)/settings/page.tsx

"use client";

import { useState } from "react";
import { useAuthStore } from "@/lib/store";
import { Button, Input } from "@/components/ui";
import clsx from "clsx";
import { Building2, Bot, Link2, CreditCard } from "lucide-react";

const TABS = [
  { id: "org", label: "Organization", icon: Building2 },
  { id: "chatbot", label: "Chatbot", icon: Bot },
  { id: "integrations", label: "Integrations", icon: Link2 },
  { id: "billing", label: "Billing", icon: CreditCard },
];

export default function SettingsPage() {
  const [tab, setTab] = useState("org");
  const { user } = useAuthStore();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900">Settings</h1>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-100">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={clsx(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t.id ? "border-brand-600 text-brand-700" : "border-transparent text-gray-500 hover:text-gray-700"
            )}>
            <t.icon size={16} />{t.label}
          </button>
        ))}
      </div>

      {/* Organization tab */}
      {tab === "org" && (
        <div className="bg-white border border-gray-100 rounded-xl p-6 max-w-2xl space-y-4">
          <h3 className="text-sm font-medium text-gray-900">Agency information</h3>
          <Input label="Agency name" defaultValue="My Agency" />
          <Input label="Contact email" defaultValue={user?.email} />
          <Input label="Phone" placeholder="+971 50 123 4567" />
          <Input label="Website" placeholder="https://myagency.com" />
          <div className="flex justify-end pt-2">
            <Button>Save changes</Button>
          </div>
        </div>
      )}

      {/* Chatbot tab */}
      {tab === "chatbot" && (
        <div className="bg-white border border-gray-100 rounded-xl p-6 max-w-2xl space-y-6">
          <div>
            <h3 className="text-sm font-medium text-gray-900 mb-1">Chatbot language</h3>
            <p className="text-xs text-gray-500 mb-3">The AI auto-detects the buyer's language, but this sets the default for first messages.</p>
            <select className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
              <option value="en">English</option>
              <option value="ar">Arabic</option>
              <option value="ru">Russian</option>
              <option value="fr">French</option>
              <option value="zh">Chinese</option>
            </select>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-900 mb-1">Custom greeting</h3>
            <p className="text-xs text-gray-500 mb-3">Override the default greeting message. Leave blank to use the AI-generated greeting.</p>
            <textarea className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm h-20 outline-none focus:border-brand-500"
              placeholder="Hi! Thanks for reaching out about properties in Dubai..." />
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-900 mb-1">Automated follow-ups</h3>
            <p className="text-xs text-gray-500 mb-3">Send automated WhatsApp messages after qualification.</p>
            <div className="space-y-2">
              {[1, 3, 7].map(day => (
                <label key={day} className="flex items-center gap-3">
                  <input type="checkbox" defaultChecked className="rounded border-gray-300 text-brand-600" />
                  <span className="text-sm text-gray-700">Day {day} follow-up</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-900 mb-1">Score thresholds</h3>
            <div className="grid grid-cols-3 gap-4">
              <Input label="Hot (min score)" type="number" defaultValue="80" />
              <Input label="Warm (min score)" type="number" defaultValue="60" />
              <Input label="Nurture (min score)" type="number" defaultValue="30" />
            </div>
          </div>
          <div className="flex justify-end"><Button>Save chatbot settings</Button></div>
        </div>
      )}

      {/* Integrations tab */}
      {tab === "integrations" && (
        <div className="max-w-2xl space-y-4">
          {[
            { name: "WhatsApp Business", desc: "Connect your WhatsApp Business number to receive and send messages.", status: "Not connected", color: "gray" },
            { name: "Meta Lead Ads", desc: "Automatically capture leads from Facebook and Instagram ad campaigns.", status: "Not connected", color: "gray" },
            { name: "Instagram Messaging", desc: "Respond to Instagram DMs with the AI chatbot.", status: "Not connected", color: "gray" },
          ].map(int => (
            <div key={int.name} className="bg-white border border-gray-100 rounded-xl p-5 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-gray-900">{int.name}</h3>
                <p className="text-xs text-gray-500 mt-1">{int.desc}</p>
              </div>
              <Button variant="secondary" size="sm">Connect</Button>
            </div>
          ))}
        </div>
      )}

      {/* Billing tab */}
      {tab === "billing" && (
        <div className="bg-white border border-gray-100 rounded-xl p-6 max-w-2xl">
          <h3 className="text-sm font-medium text-gray-900 mb-4">Current plan</h3>
          <div className="flex items-center justify-between p-4 bg-brand-50 rounded-lg mb-6">
            <div>
              <p className="text-sm font-medium text-brand-700">Free plan</p>
              <p className="text-xs text-brand-600">50 leads/month, 1 agent</p>
            </div>
            <Button size="sm">Upgrade</Button>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-gray-500">Leads used this month</span><span className="font-medium">12 / 50</span></div>
            <div className="flex justify-between"><span className="text-gray-500">Active agents</span><span className="font-medium">1 / 1</span></div>
            <div className="flex justify-between"><span className="text-gray-500">AI messages used</span><span className="font-medium">847</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
