"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { ArrowLeft, Plus, Trash2, Send, PlugZap } from "lucide-react";
import { format } from "date-fns";

const EMPTY = { server_id: "", remote_path: "", remote_key: "", go_live: false };

export default function VpsTargetsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [err, setErr] = useState("");

  const { data: targets = [], isLoading } = useQuery({
    queryKey: ["vps-targets", id],
    queryFn: () => api.get("/api/vps-targets", { params: { secret_id: id } }).then((r) => r.data),
  });
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: () => api.get("/api/servers").then((r) => r.data) });

  const createMut = useMutation({
    mutationFn: (body: typeof EMPTY) => api.post("/api/vps-targets", {
      secret_id: Number(id),
      server_id: Number(body.server_id),
      remote_path: body.remote_path,
      remote_key: body.remote_key,
      dry_run: !body.go_live,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["vps-targets", id] }); setShowAdd(false); setForm(EMPTY); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (tid: number) => api.delete(`/api/vps-targets/${tid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vps-targets", id] }),
  });

  const pushMut = useMutation({
    mutationFn: (tid: number) => api.post(`/api/vps-targets/${tid}/push`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vps-targets", id] }),
    onError: (e) => alert(getErrorMessage(e)),
  });

  const testMut = useMutation({
    mutationFn: (tid: number) => api.post(`/api/vps-targets/${tid}/test`),
    onSuccess: () => alert("Connection OK"),
    onError: (e) => alert(getErrorMessage(e)),
  });

  return (
    <div>
      <Topbar title="VPS Sync Targets"
        action={
          <div className="flex items-center gap-2">
            <button onClick={() => { setForm(EMPTY); setErr(""); setShowAdd(true); }} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Target</button>
            <button onClick={() => router.back()} className="btn-ghost flex items-center gap-1.5"><ArrowLeft size={15} /> Back</button>
          </div>
        }
      />
      <div className="p-6">
        <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2f32]">
                {["Server", "Remote Path", "Key", "Mode", "Last Sync", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-[#6b7680]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2f32]">
              {isLoading ? <tr><td colSpan={6} className="px-4 py-8 text-center text-[#6b7680]">Loading…</td></tr>
                : targets.length === 0 ? <tr><td colSpan={6} className="px-4 py-8 text-center text-[#6b7680]">No VPS targets yet — pushes for this secret only happen once you add one.</td></tr>
                : targets.map((t: any) => {
                  const server = servers.find((s: any) => s.id === t.server_id);
                  return (
                    <tr key={t.id} className="hover:bg-[#22282b]">
                      <td className="px-4 py-3 text-[#e0e3e5] font-medium">{server?.name || `Server #${t.server_id}`}</td>
                      <td className="px-4 py-3 text-[#9aa3ab] font-mono text-xs">{t.remote_path || server?.default_env_path || ".env"}</td>
                      <td className="px-4 py-3 text-[#9aa3ab] font-mono text-xs">{t.remote_key || "(secret name)"}</td>
                      <td className="px-4 py-3">
                        <Badge value={t.dry_run ? "dry_run" : "live"} />
                      </td>
                      <td className="px-4 py-3 text-[#6b7680] text-xs">
                        {t.last_sync_status ? (
                          <>
                            <Badge value={t.last_sync_status} />
                            {t.last_synced_at && <span className="ml-1">{format(new Date(t.last_synced_at), "MMM d HH:mm")}</span>}
                            {t.last_sync_error && <p className="text-red-400 mt-1 max-w-[240px] truncate" title={t.last_sync_error}>{t.last_sync_error}</p>}
                          </>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button onClick={() => testMut.mutate(t.id)} className="btn-ghost p-1.5" title="Test connection"><PlugZap size={14} /></button>
                          <button onClick={() => pushMut.mutate(t.id)} className="btn-ghost p-1.5" title="Push now"><Send size={14} /></button>
                          <button onClick={() => { if (confirm("Remove this VPS target?")) deleteMut.mutate(t.id); }} className="btn-danger p-1.5"><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>

      <Modal title="Add VPS Target" open={showAdd} onClose={() => setShowAdd(false)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Server *</label>
            <select className="field" value={form.server_id} onChange={(e) => setForm((f) => ({ ...f, server_id: e.target.value }))}>
              <option value="">Select server…</option>
              {servers.map((s: any) => <option key={s.id} value={s.id}>{s.name}{!s.ssh_host ? " (no SSH configured)" : ""}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Remote Path</label>
              <input className="field font-mono text-xs" value={form.remote_path} onChange={(e) => setForm((f) => ({ ...f, remote_path: e.target.value }))} placeholder="default: server's" />
            </div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Key Name</label>
              <input className="field font-mono text-xs" value={form.remote_key} onChange={(e) => setForm((f) => ({ ...f, remote_key: e.target.value }))} placeholder="default: secret name" />
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-[#9aa3ab]">
            <input type="checkbox" checked={form.go_live} onChange={(e) => setForm((f) => ({ ...f, go_live: e.target.checked }))} />
            Go live now (unchecked = dry run, safe default — logs intent only)
          </label>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setShowAdd(false)} className="btn-ghost">Cancel</button>
            <button onClick={() => createMut.mutate(form)} disabled={createMut.isPending || !form.server_id} className="btn-primary">{createMut.isPending ? "Adding…" : "Add Target"}</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
