"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { Plus, Trash2, Pencil, PlugZap } from "lucide-react";

const EMPTY = {
  name: "", provider: "", ip_address: "", cpu: "", ram: "", storage: "", operating_system: "", purpose: "", status: "running", notes: "",
  ssh_host: "", ssh_port: "22", ssh_username: "", ssh_key_secret_id: "", default_env_path: ".env",
};

export default function ServersPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [err, setErr] = useState("");

  const { data: servers = [], isLoading } = useQuery({
    queryKey: ["servers"],
    queryFn: () => api.get("/api/servers").then((r) => r.data),
  });
  const { data: secrets = [] } = useQuery({ queryKey: ["secrets"], queryFn: () => api.get("/api/secrets").then((r) => r.data) });
  const sshKeySecrets = secrets.filter((s: any) => s.category === "SSH_KEY" || s.category === "SSH Key");

  const toBody = (f: typeof EMPTY) => ({
    ...f,
    ssh_port: f.ssh_port ? Number(f.ssh_port) : 22,
    ssh_key_secret_id: f.ssh_key_secret_id ? Number(f.ssh_key_secret_id) : null,
  });

  const createMut = useMutation({
    mutationFn: (body: typeof EMPTY) => api.post("/api/servers", toBody(body)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); setShowCreate(false); setForm(EMPTY); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: typeof EMPTY }) => api.patch(`/api/servers/${id}`, toBody(body)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["servers"] }); setEditId(null); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const updateStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => api.patch(`/api/servers/${id}/status`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["servers"] }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/api/servers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["servers"] }),
    onError: (e) => alert(getErrorMessage(e)),
  });

  const testMut = useMutation({
    mutationFn: (id: number) => api.post(`/api/servers/${id}/test-ssh`),
    onSuccess: () => alert("Connection OK"),
    onError: (e) => alert(getErrorMessage(e)),
  });

  const F = (setter: typeof setForm) => (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setter((f) => ({ ...f, [k]: e.target.value }));

  const openEdit = (s: any) => {
    setForm({
      name: s.name || "", provider: s.provider || "", ip_address: s.ip_address || "", cpu: s.cpu || "",
      ram: s.ram || "", storage: s.storage || "", operating_system: s.operating_system || "", purpose: s.purpose || "",
      status: s.status || "running", notes: s.notes || "",
      ssh_host: s.ssh_host || "", ssh_port: String(s.ssh_port || 22), ssh_username: s.ssh_username || "",
      ssh_key_secret_id: s.ssh_key_secret_id ? String(s.ssh_key_secret_id) : "", default_env_path: s.default_env_path || ".env",
    });
    setErr("");
    setEditId(s.id);
  };

  const renderSshFields = (f: typeof EMPTY, setter: typeof setForm) => (
    <div className="pt-2 border-t border-[#2a2f32] space-y-3">
      <p className="text-xs text-[#9aa3ab] font-medium">SSH Access (optional — needed for VPS .env sync)</p>
      <div className="grid grid-cols-2 gap-3">
        <input className="field font-mono text-xs" value={f.ssh_host} onChange={F(setter)("ssh_host")} placeholder="Host, e.g. 203.0.113.5" />
        <input className="field font-mono text-xs" type="number" value={f.ssh_port} onChange={F(setter)("ssh_port")} placeholder="Port" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <input className="field font-mono text-xs" value={f.ssh_username} onChange={F(setter)("ssh_username")} placeholder="SSH username" />
        <select className="field text-xs" value={f.ssh_key_secret_id} onChange={F(setter)("ssh_key_secret_id")}>
          <option value="">SSH key secret…</option>
          {sshKeySecrets.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <input className="field font-mono text-xs" value={f.default_env_path} onChange={F(setter)("default_env_path")} placeholder="Default .env path" />
    </div>
  );

  return (
    <div>
      <Topbar title="Servers" description={`${servers.length} server${servers.length !== 1 ? "s" : ""}`}
        action={<button onClick={() => { setForm(EMPTY); setErr(""); setShowCreate(true); }} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Server</button>}
      />
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {isLoading ? (
            <div className="flex justify-center py-16 col-span-3"><div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" /></div>
          ) : servers.length === 0 ? (
            <p className="text-[#6b7680] text-sm">No servers yet.</p>
          ) : servers.map((s: any) => (
            <div key={s.id} className="bg-[#1d2022] border border-[#2a2f32] rounded-xl p-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="font-semibold text-[#e0e3e5]">{s.name}</p>
                  <p className="text-xs text-[#6b7680] font-mono">{s.ip_address || "No IP"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge value={s.status} />
                  <button onClick={() => openEdit(s)} className="p-1.5 text-[#6b7680] hover:text-[#e0e3e5] hover:bg-white/5 rounded transition-colors"><Pencil size={14} /></button>
                  {s.ssh_host && (
                    <button onClick={() => testMut.mutate(s.id)} className="p-1.5 text-[#6b7680] hover:text-green-400 hover:bg-green-500/10 rounded transition-colors" title="Test SSH">
                      <PlugZap size={14} />
                    </button>
                  )}
                  <button onClick={() => { if (confirm(`Delete "${s.name}"?`)) deleteMut.mutate(s.id); }} className="p-1.5 text-[#6b7680] hover:text-red-400 hover:bg-red-500/10 rounded transition-colors">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <div className="space-y-1 text-xs text-[#9aa3ab] mb-4">
                {s.provider && <p>Provider: {s.provider}</p>}
                {s.cpu && <p>CPU: {s.cpu}</p>}
                {s.ram && <p>RAM: {s.ram}</p>}
                {s.purpose && <p>Purpose: {s.purpose}</p>}
                {s.ssh_host && <p className="font-mono">SSH: {s.ssh_username}@{s.ssh_host}:{s.ssh_port}</p>}
              </div>
              <select
                className="field text-xs"
                value={s.status}
                onChange={(e) => updateStatusMut.mutate({ id: s.id, status: e.target.value })}
              >
                <option value="running">running</option>
                <option value="stopped">stopped</option>
                <option value="maintenance">maintenance</option>
              </select>
            </div>
          ))}
        </div>
      </div>

      <Modal title="Add Server" open={showCreate} onClose={() => setShowCreate(false)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Name *</label><input className="field" value={form.name} onChange={F(setForm)("name")} /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Provider</label><input className="field" value={form.provider} onChange={F(setForm)("provider")} placeholder="Hetzner, AWS…" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">IP Address</label><input className="field font-mono" value={form.ip_address} onChange={F(setForm)("ip_address")} /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Status</label>
              <select className="field" value={form.status} onChange={F(setForm)("status")}><option value="running">running</option><option value="stopped">stopped</option><option value="maintenance">maintenance</option></select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">CPU</label><input className="field" value={form.cpu} onChange={F(setForm)("cpu")} placeholder="4 vCPU" /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">RAM</label><input className="field" value={form.ram} onChange={F(setForm)("ram")} placeholder="8 GB" /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Storage</label><input className="field" value={form.storage} onChange={F(setForm)("storage")} placeholder="80 GB SSD" /></div>
          </div>
          <div><label className="block text-xs text-[#9aa3ab] mb-1">Purpose</label><input className="field" value={form.purpose} onChange={F(setForm)("purpose")} placeholder="License activation server" /></div>
          {renderSshFields(form, setForm)}
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setShowCreate(false)} className="btn-ghost">Cancel</button>
            <button onClick={() => createMut.mutate(form)} disabled={createMut.isPending || !form.name} className="btn-primary">{createMut.isPending ? "Adding…" : "Add Server"}</button>
          </div>
        </div>
      </Modal>

      <Modal title="Edit Server" open={editId !== null} onClose={() => setEditId(null)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Name *</label><input className="field" value={form.name} onChange={F(setForm)("name")} /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Provider</label><input className="field" value={form.provider} onChange={F(setForm)("provider")} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">IP Address</label><input className="field font-mono" value={form.ip_address} onChange={F(setForm)("ip_address")} /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">OS</label><input className="field" value={form.operating_system} onChange={F(setForm)("operating_system")} /></div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><label className="block text-xs text-[#9aa3ab] mb-1">CPU</label><input className="field" value={form.cpu} onChange={F(setForm)("cpu")} /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">RAM</label><input className="field" value={form.ram} onChange={F(setForm)("ram")} /></div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Storage</label><input className="field" value={form.storage} onChange={F(setForm)("storage")} /></div>
          </div>
          <div><label className="block text-xs text-[#9aa3ab] mb-1">Notes</label><textarea className="field resize-none" rows={2} value={form.notes} onChange={F(setForm)("notes")} /></div>
          {renderSshFields(form, setForm)}
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setEditId(null)} className="btn-ghost">Cancel</button>
            <button onClick={() => editId !== null && updateMut.mutate({ id: editId, body: form })} disabled={updateMut.isPending || !form.name} className="btn-primary">{updateMut.isPending ? "Saving…" : "Save Changes"}</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
