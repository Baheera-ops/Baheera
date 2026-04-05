// src/app/(auth)/signup/page.tsx

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/store";
import { Button, Input } from "@/components/ui";

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuthStore();
  const [form, setForm] = useState({ email: "", password: "", fullName: "", agencyName: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await signup(form.email, form.password, form.fullName, form.agencyName);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Signup failed");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-brand-600 tracking-tight">Bahera</h1>
          <p className="text-sm text-gray-500 mt-2">Create your agency account</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input label="Full name" value={form.fullName}
              onChange={e => setForm({ ...form, fullName: e.target.value })}
              placeholder="Your name" required autoFocus />
            <Input label="Agency name" value={form.agencyName}
              onChange={e => setForm({ ...form, agencyName: e.target.value })}
              placeholder="Your real estate agency" required />
            <Input label="Email" type="email" value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
              placeholder="you@agency.com" required />
            <Input label="Password" type="password" value={form.password}
              onChange={e => setForm({ ...form, password: e.target.value })}
              placeholder="Min 8 characters" required />

            {error && (
              <div className="bg-red-50 text-red-600 text-sm px-3 py-2 rounded-lg">{error}</div>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Creating account..." : "Create account"}
            </Button>
          </form>
        </div>

        <p className="text-center text-sm text-gray-500 mt-6">
          Already have an account?{" "}
          <Link href="/login" className="text-brand-600 hover:text-brand-700 font-medium">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
