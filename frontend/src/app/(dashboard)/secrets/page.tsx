"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { Plus, Eye, EyeOff, RefreshCw, Trash2, History, Server as ServerIcon } from "lucide-react";
import { format } from "date-fns";

const EMPTY = {
  name: "", category: "API_KEY", value: "", project_id: "", environment: "", description: "",
  rotation_mode: "manual", rotation_interval_days: "",
};

export default function SecretsPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [showRotate, setShowRotate] = useState<number | null>(null);
  const [revealed, setRevealed] = useState<{ id: number; value: string } | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [newValue, setNewValue] = useState("");
  const [err, setErr] = useState("");

  const { data: secrets = [], isLoading } = useQuery({ queryKey: ["secrets"], queryFn: () => api.get("/api/secrets").then((r) => r.data) });
  const { data: projects = [] } = useQuery({ queryKey: ["projects"], queryFn: () => api.get("/api/projects").then((r) => r.data) });

  const createMut = useMutation({
    mutationFn: (body: typeof EMPTY) => api.post("/api/secrets", {
      ...body,
      project_id: body.project_id ? Number(body.project_id) : null,
      rotation_interval_days: body.rotation_interval_days ? Number(body.rotation_interval_days) : null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["secrets"] }); setShowCreate(false); setForm(EMPTY); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const revealMut = useMutation({
    mutationFn: (id: number) => api.post(`/api/secrets/${id}/reveal`),
    onSuccess: (res) => setRevealed({ id: res.data.id, value: res.data.value }),
    onError: (e) => alert(getErrorMessage(e)),
  });

  const rotateMut = useMutation({
    mutationFn: ({ id, value }: { id: number; value: string }) => api.post(`/api/secrets/${id}/rotate`, { new_value: value || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["secrets"] }); setShowRotate(null); setNewValue(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/api/secrets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secrets"] }),
    onError: (e) => alert(getErrorMessage(e)),
  });

  const F = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const rotatingSecret = secrets.find((s: any) => s.id === showRotate);

  return (
    <div>
      <Topbar title="Secrets Vault" description={`${secrets.length} secret${secrets.length !== 1 ? "s" : ""}`}
        action={<button onClick={() => { setForm(EMPTY); setErr(""); setShowCreate(true); }} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Secret</button>}
      />
      <div className="p-6">
        <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2f32]">
                {["Name", "Category", "Project", "Environment", "Created By", "Rotated", "Rotation", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-[#6b7680]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2f32]">
              {isLoading ? <tr><td colSpan={8} className="px-4 py-8 text-center text-[#6b7680]">Loading…</td></tr>
                : secrets.length === 0 ? <tr><td colSpan={8} className="px-4 py-8 text-center text-[#6b7680]">No secrets yet.</td></tr>
                : secrets.map((s: any) => (
                  <tr key={s.id} className="hover:bg-[#22282b]">
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-[#e0e3e5] font-medium">{s.name}</p>
                        {revealed?.id === s.id ? (
                          <code className="text-xs text-green-400 font-mono break-all">{revealed!.value}</code>
                        ) : (
                          <p className="text-xs text-[#6b7680] font-mono">••••••••</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3"><Badge value={s.category} /></td>
                    <td className="px-4 py-3 text-[#9aa3ab]">{s.project?.name || "Global"}</td>
                    <td className="px-4 py-3 text-[#9aa3ab]">{s.environment || "—"}</td>
                    <td className="px-4 py-3 text-[#9aa3ab]">{s.created_by || "—"}</td>
                    <td className="px-4 py-3 text-[#6b7680]">{s.rotated_at ? format(new Date(s.rotated_at), "MMM d") : "—"}</td>
                    <td className="px-4 py-3">
                      <Badge value={s.rotation_mode || "manual"} />
                      {s.next_rotation_at && <p className="text-[10px] text-[#6b7680] mt-0.5">next {format(new Date(s.next_rotation_at), "MMM d")}</p>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => revealed?.id === s.id ? setRevealed(null) : revealMut.mutate(s.id)} className="btn-ghost p-1.5" title="Reveal">
                          {revealed?.id === s.id ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                        <button onClick={() => router.push(`/secrets/${s.id}/targets`)} className="btn-ghost p-1.5" title="VPS Targets"><ServerIcon size={14} /></button>
                        <button onClick={() => { setShowRotate(s.id); setNewValue(""); setErr(""); }} className="btn-ghost p-1.5" title="Rotate"><RefreshCw size={14} /></button>
                        <button onClick={() => router.push(`/secrets/${s.id}/versions`)} className="btn-ghost p-1.5" title="History"><History size={14} /></button>
                        <button onClick={() => { if (confirm(`Delete "${s.name}"?`)) deleteMut.mutate(s.id); }} className="btn-danger p-1.5"><Trash2 size={14} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create Secret Modal */}
      <Modal title="Add Secret" open={showCreate} onClose={() => setShowCreate(false)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Name *</label><input className="field" value={form.name} onChange={F("name")} placeholder="DATABASE_URL" /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Category</label>
              <select className="field" value={form.category} onChange={F("category")}>
                {["API_KEY", "DATABASE", "CREDENTIAL", "CERTIFICATE", "TOKEN", "SSH_KEY", "OTHER"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div><label className="block text-xs text-[#9aa3ab] mb-1">Value *</label><textarea className="field font-mono resize-none" rows={3} value={form.value} onChange={F("value")} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Project</label>
              <select className="field" value={form.project_id} onChange={F("project_id")}>
                <option value="">Global</option>
                {projects.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Environment</label>
              <select className="field" value={form.environment} onChange={F("environment")}>
                <option value="">—</option><option>development</option><option>staging</option><option>production</option><option>global</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Rotation</label>
              <select className="field" value={form.rotation_mode} onChange={F("rotation_mode")}>
                <option value="manual">Manual only</option>
                <option value="auto">Auto (generate + push to VPS)</option>
                <option value="reminder">Reminder only</option>
              </select>
            </div>
            {form.rotation_mode !== "manual" && (
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Interval (days)</label>
                <input type="number" min={1} className="field" value={form.rotation_interval_days} onChange={F("rotation_interval_days")} placeholder="e.g. 7 or 30" />
              </div>
            )}
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setShowCreate(false)} className="btn-ghost">Cancel</button>
            <button onClick={() => createMut.mutate(form)} disabled={createMut.isPending || !form.name || !form.value} className="btn-primary">{createMut.isPending ? "Saving…" : "Store Secret"}</button>
          </div>
        </div>
      </Modal>

      {/* Rotate Modal */}
      <Modal title="Rotate Secret" open={showRotate !== null} onClose={() => setShowRotate(null)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <p className="text-sm text-[#9aa3ab]">The current value will be saved to version history before being replaced.</p>
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">New Value {rotatingSecret?.rotation_mode !== "auto" && "*"}</label>
            <textarea className="field font-mono resize-none" rows={3} value={newValue} onChange={(e) => setNewValue(e.target.value)}
              placeholder={rotatingSecret?.rotation_mode === "auto" ? "Leave blank to auto-generate a new random value" : ""} />
          </div>
          <div className="flex justify-end gap-3">
            <button onClick={() => setShowRotate(null)} className="btn-ghost">Cancel</button>
            <button onClick={() => showRotate !== null && rotateMut.mutate({ id: showRotate, value: newValue })}
              disabled={rotateMut.isPending || (!newValue.trim() && rotatingSecret?.rotation_mode !== "auto")} className="btn-primary">
              {rotateMut.isPending ? "Rotating…" : "Rotate"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
