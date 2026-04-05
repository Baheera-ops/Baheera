// src/app/(dashboard)/properties/page.tsx

"use client";

import { useEffect, useState, useRef } from "react";
import { api, Property, Document as Doc } from "@/lib/api";
import { Button, Modal, Input, Select, EmptyState } from "@/components/ui";
import { Plus, Upload, FileText, Check, Loader2, Trash2 } from "lucide-react";

export default function PropertiesPage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [selectedProp, setSelectedProp] = useState<Property | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({
    name: "", location: "", property_type: "apartment", price_from: "", price_to: "", currency: "AED", payment_plan: "",
  });

  const load = () => api.getProperties().then(setProperties).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    await api.createProperty({ ...form, price_from: Number(form.price_from), price_to: form.price_to ? Number(form.price_to) : undefined });
    setShowAdd(false);
    setForm({ name: "", location: "", property_type: "apartment", price_from: "", price_to: "", currency: "AED", payment_plan: "" });
    load();
  };

  const openDocs = async (prop: Property) => {
    setSelectedProp(prop);
    const d = await api.getPropertyDocuments(prop.id);
    setDocs(d);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedProp) return;
    setUploading(true);
    await api.uploadDocument(selectedProp.id, file);
    const d = await api.getPropertyDocuments(selectedProp.id);
    setDocs(d);
    setUploading(false);
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <Check size={14} className="text-green-500" />;
      case "processing": case "embedding": return <Loader2 size={14} className="text-blue-500 animate-spin" />;
      case "failed": return <span className="text-xs text-red-500">Failed</span>;
      default: return <span className="text-xs text-gray-400">Pending</span>;
    }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-400">Loading properties...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Property database</h1>
          <p className="text-sm text-gray-500 mt-1">{properties.length} listings</p>
        </div>
        <Button onClick={() => setShowAdd(true)}><Plus size={16} className="mr-1.5" />Add property</Button>
      </div>

      {properties.length === 0 ? (
        <EmptyState title="No properties" description="Add your first property listing to enable AI recommendations."
          action={<Button onClick={() => setShowAdd(true)}>Add property</Button>} />
      ) : (
        <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-100">
                <th className="px-6 py-3 font-medium">Property</th>
                <th className="px-6 py-3 font-medium">Location</th>
                <th className="px-6 py-3 font-medium">Type</th>
                <th className="px-6 py-3 font-medium">Price range</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium text-right">Docs</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {properties.map(prop => (
                <tr key={prop.id} className="hover:bg-gray-50/50 cursor-pointer" onClick={() => openDocs(prop)}>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{prop.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{prop.location}</td>
                  <td className="px-6 py-4 text-sm text-gray-600 capitalize">{prop.property_type}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {prop.currency} {Number(prop.price_from).toLocaleString()}
                    {prop.price_to && ` — ${Number(prop.price_to).toLocaleString()}`}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${prop.is_active ? "bg-green-50 text-green-700" : "bg-gray-50 text-gray-500"}`}>
                      {prop.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); openDocs(prop); }}>
                      <FileText size={14} className="mr-1" />Manage
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add property modal */}
      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add property" size="lg">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Property name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required className="col-span-2" />
          <Input label="Location" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} required />
          <Select label="Type" value={form.property_type} onChange={e => setForm({ ...form, property_type: e.target.value })} options={[
            { value: "apartment", label: "Apartment" }, { value: "villa", label: "Villa" },
            { value: "townhouse", label: "Townhouse" }, { value: "penthouse", label: "Penthouse" },
            { value: "studio", label: "Studio" }, { value: "office", label: "Office" },
          ]} />
          <Input label="Price from" type="number" value={form.price_from} onChange={e => setForm({ ...form, price_from: e.target.value })} required />
          <Input label="Price to" type="number" value={form.price_to} onChange={e => setForm({ ...form, price_to: e.target.value })} />
          <Input label="Payment plan" value={form.payment_plan} onChange={e => setForm({ ...form, payment_plan: e.target.value })} placeholder="e.g., 60/40" className="col-span-2" />
        </div>
        <div className="flex justify-end gap-3 pt-4">
          <Button variant="secondary" onClick={() => setShowAdd(false)}>Cancel</Button>
          <Button onClick={handleCreate} disabled={!form.name || !form.location || !form.price_from}>Create</Button>
        </div>
      </Modal>

      {/* Document management modal */}
      <Modal open={!!selectedProp} onClose={() => setSelectedProp(null)} title={`Documents — ${selectedProp?.name}`} size="lg">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <input ref={fileRef} type="file" accept=".pdf,.txt,.csv" className="hidden" onChange={handleUpload} />
            <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Upload size={14} className="mr-1.5" />}
              {uploading ? "Uploading..." : "Upload PDF"}
            </Button>
            <span className="text-xs text-gray-400">PDF, TXT, or CSV files for the AI knowledge base</span>
          </div>

          {docs.length === 0 ? (
            <div className="text-center py-8 text-sm text-gray-400">No documents uploaded yet</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {docs.map(doc => (
                <div key={doc.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <FileText size={18} className="text-gray-400" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">{doc.file_name}</p>
                      <p className="text-xs text-gray-400">{doc.chunk_count} chunks embedded</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {statusIcon(doc.processing_status)}
                    <span className="text-xs text-gray-400">
                      {new Date(doc.uploaded_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
