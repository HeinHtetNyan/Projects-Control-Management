"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { Plus } from "lucide-react";
import { format } from "date-fns";

const EMPTY_FORM = { project_id: "", customer_id: "", license_number: "", license_type: "lifetime", expires_days: "" };

// Days auto-filled when a timed license type is selected (user can still override)
const TYPE_DAYS: Record<string, string> = { annual: "365", "6month": "180", monthly: "30" };

export default function TokensPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [err, setErr] = useState("");

  const { data: tokens = [], isLoading } = useQuery({
    queryKey: ["tokens"],
    queryFn: () => api.get("/api/tokens").then((r) => r.data),
  });
  const { data: projects = [] } = useQuery({ queryKey: ["projects"], queryFn: () => api.get("/api/projects").then((r) => r.data) });
  const { data: customers = [] } = useQuery({ queryKey: ["customers"], queryFn: () => api.get("/api/customers").then((r) => r.data) });

  const createMut = useMutation({
    mutationFn: (body: typeof EMPTY_FORM) =>
      api.post("/api/tokens", {
        ...body,
        project_id: Number(body.project_id),
        customer_id: Number(body.customer_id),
        expires_days: body.expires_days ? Number(body.expires_days) : null,
      }),
    onSuccess: (res) => { qc.invalidateQueries({ queryKey: ["tokens"] }); setShowCreate(false); router.push(`/tokens/${res.data.id}`); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  function openCreate() {
    const year = new Date().getFullYear();
    const next = String((tokens as any[]).length + 1).padStart(4, "0");
    setErr("");
    setForm({ ...EMPTY_FORM, license_number: `SY-${year}-${next}` });
    setShowCreate(true);
  }

  const F = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  function handleTypeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const type = e.target.value;
    setForm((f) => ({ ...f, license_type: type, expires_days: TYPE_DAYS[type] ?? "" }));
  }

  return (
    <div>
      <Topbar
        title="Activation Tokens"
        description={`${(tokens as any[]).length} token${(tokens as any[]).length !== 1 ? "s" : ""}`}
        action={<button onClick={openCreate} className="btn-primary flex items-center gap-2"><Plus size={16} /> Generate Token</button>}
      />

      <div className="p-6">
        <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2f32]">
                {["License #", "Project", "Customer", "Type", "Status", "Expires", "Created", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-[#6b7680]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2f32]">
              {isLoading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-[#6b7680]">Loading…</td></tr>
              ) : (tokens as any[]).length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-[#6b7680]">No tokens yet.</td></tr>
              ) : (tokens as any[]).map((t: any) => (
                <tr key={t.id} className="hover:bg-[#22282b] cursor-pointer" onClick={() => router.push(`/tokens/${t.id}`)}>
                  <td className="px-4 py-3 text-[#e0e3e5] font-mono text-xs">{t.license_number}</td>
                  <td className="px-4 py-3 text-[#9aa3ab]">{t.project?.name}</td>
                  <td className="px-4 py-3 text-[#9aa3ab]">{t.customer?.name}</td>
                  <td className="px-4 py-3"><Badge value={t.license_type} /></td>
                  <td className="px-4 py-3"><Badge value={t.status} /></td>
                  <td className="px-4 py-3 text-[#6b7680]">{t.expires_at ? format(new Date(t.expires_at), "MMM d, yyyy") : "Never"}</td>
                  <td className="px-4 py-3 text-[#6b7680]">{format(new Date(t.created_at), "MMM d, yyyy")}</td>
                  <td className="px-4 py-3 text-blue-400 text-xs">View →</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Modal title="Generate Activation Token" open={showCreate} onClose={() => setShowCreate(false)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Project *</label>
              <select className="field" value={form.project_id} onChange={F("project_id")}>
                <option value="">Select project…</option>
                {(projects as any[]).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Customer *</label>
              <select className="field" value={form.customer_id} onChange={F("customer_id")}>
                <option value="">Select customer…</option>
                {(customers as any[]).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">License Number *</label>
            <input className="field font-mono" value={form.license_number} onChange={F("license_number")} placeholder="SY-2026-0001" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">License Type</label>
              <select className="field" value={form.license_type} onChange={handleTypeChange}>
                <option value="lifetime">lifetime</option>
                <option value="annual">annual</option>
                <option value="6month">6 months</option>
                <option value="monthly">monthly</option>
                <option value="trial">trial</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">
                Expires in (days)
                {TYPE_DAYS[form.license_type] !== undefined && (
                  <span className="ml-1 text-[#6b7680]">— auto-filled, editable</span>
                )}
              </label>
              <input
                className="field"
                type="number"
                min="1"
                value={form.expires_days}
                onChange={F("expires_days")}
                placeholder={form.license_type === "lifetime" ? "Never expires" : "Days until expiry"}
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setShowCreate(false)} className="btn-ghost">Cancel</button>
            <button
              onClick={() => createMut.mutate(form)}
              disabled={createMut.isPending || !form.project_id || !form.customer_id || !form.license_number}
              className="btn-primary"
            >
              {createMut.isPending ? "Generating…" : "Generate Token"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
