"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { ArrowLeft, Key, Edit3, RefreshCw, Copy, Check, RotateCw, Settings } from "lucide-react";
import { format } from "date-fns";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [showEdit, setShowEdit] = useState(false);
  const [showReimport, setShowReimport] = useState(false);
  const [showRestartSettings, setShowRestartSettings] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", description: "", type: "", status: "", version: "" });
  const [restartForm, setRestartForm] = useState({ restart_server_id: "", restart_command: "", go_live: false });
  const [privateKey, setPrivateKey] = useState("");
  const [err, setErr] = useState("");
  const [restartErr, setRestartErr] = useState("");
  const [copied, setCopied] = useState(false);

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", id],
    queryFn: () => api.get(`/api/projects/${id}`).then((r) => r.data),
  });

  const { data: tokens = [] } = useQuery({
    queryKey: ["tokens"],
    queryFn: () => api.get("/api/tokens").then((r) => r.data),
    select: (data: any[]) => data.filter((t) => t.project_id === Number(id)),
  });

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: () => api.get("/api/servers").then((r) => r.data) });

  const restartSettingsMut = useMutation({
    mutationFn: (body: typeof restartForm) => api.patch(`/api/projects/${id}/restart-settings`, {
      restart_server_id: body.restart_server_id ? Number(body.restart_server_id) : null,
      restart_command: body.restart_command,
      restart_dry_run: !body.go_live,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", id] }); setShowRestartSettings(false); },
    onError: (e) => setRestartErr(getErrorMessage(e)),
  });

  const restartMut = useMutation({
    mutationFn: () => api.post(`/api/projects/${id}/restart`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", id] }),
    onError: (e) => { alert(getErrorMessage(e)); qc.invalidateQueries({ queryKey: ["project", id] }); },
  });

  function openRestartSettings() {
    if (!project) return;
    setRestartForm({
      restart_server_id: project.restart_server_id ? String(project.restart_server_id) : "",
      restart_command: project.restart_command || "",
      go_live: !project.restart_dry_run,
    });
    setRestartErr("");
    setShowRestartSettings(true);
  }

  const updateMut = useMutation({
    mutationFn: (body: typeof editForm) => api.put(`/api/projects/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", id] }); setShowEdit(false); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const reimportMut = useMutation({
    mutationFn: () => api.post(`/api/projects/${id}/reimport-key`, { private_key: privateKey }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", id] }); setShowReimport(false); setPrivateKey(""); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  function openEdit() {
    if (!project) return;
    setEditForm({ name: project.name, description: project.description || "", type: project.type || "", status: project.status || "", version: project.version || "" });
    setErr("");
    setShowEdit(true);
  }

  function copyPublicKey() {
    if (!project) return;
    navigator.clipboard.writeText(project.public_key_b64);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (isLoading) return (
    <div className="flex justify-center py-16">
      <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!project) return <p className="p-6 text-[#9aa3ab]">Project not found.</p>;

  return (
    <div>
      <Topbar
        title={project.name}
        description={`Slug: ${project.slug}`}
        action={
          <div className="flex gap-2">
            <button onClick={() => router.back()} className="btn-ghost flex items-center gap-1.5"><ArrowLeft size={15} /> Back</button>
            <button onClick={openEdit} className="btn-ghost flex items-center gap-1.5"><Edit3 size={15} /> Edit</button>
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Info */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl p-5 space-y-4">
            <h2 className="text-sm font-semibold text-[#e0e3e5]">Project Info</h2>
            <Row label="Status" value={<Badge value={project.status || "Development"} />} />
            <Row label="Type" value={project.type || "—"} />
            <Row label="Version" value={project.version || "—"} />
            <Row label="Deep Link" value={<span className="font-mono text-xs">{project.deep_link_scheme}://</span>} />
            <Row label="Created" value={format(new Date(project.created_at), "MMM d, yyyy")} />
          </div>

          <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#e0e3e5]">Cryptographic Keys</h2>
              <button onClick={() => { setShowReimport(true); setErr(""); }} className="btn-ghost flex items-center gap-1.5 text-xs">
                <RefreshCw size={13} /> Re-import Key
              </button>
            </div>
            <div>
              <p className="text-xs text-[#6b7680] mb-1">Public Key (Ed25519)</p>
              <div className="flex items-center gap-2">
                <code className="text-xs text-[#9aa3ab] bg-[#101415] border border-[#2a2f32] rounded px-2 py-1.5 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
                  {project.public_key_b64}
                </code>
                <button onClick={copyPublicKey} className="p-2 text-[#6b7680] hover:text-[#e0e3e5] transition-colors">
                  {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Restart */}
        <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#e0e3e5]">Restart</h2>
            <button onClick={openRestartSettings} className="btn-ghost flex items-center gap-1.5 text-xs"><Settings size={13} /> Configure</button>
          </div>
          {project.restart_server_id && project.restart_command ? (
            <>
              <p className="text-xs text-[#9aa3ab] font-mono truncate" title={project.restart_command}>{project.restart_command}</p>
              <div className="flex items-center gap-2">
                <Badge value={project.restart_dry_run ? "dry_run" : "live"} />
                {project.last_restart_status && (
                  <span className="text-[11px] text-[#6b7680]">
                    last: {project.last_restart_status}{project.last_restart_at && ` · ${format(new Date(project.last_restart_at), "MMM d HH:mm")}`}
                  </span>
                )}
              </div>
              {project.last_restart_output && (
                <pre className="text-[10px] text-[#9aa3ab] bg-[#101415] border border-[#2a2f32] rounded p-2 overflow-x-auto max-h-24">{project.last_restart_output.slice(0, 500)}</pre>
              )}
              <button
                onClick={() => { if (!project.restart_dry_run && !confirm("This will restart the live service. Continue?")) return; restartMut.mutate(); }}
                disabled={restartMut.isPending}
                className="btn-primary w-full flex items-center justify-center gap-2"
              >
                <RotateCw size={14} /> {restartMut.isPending ? "Restarting…" : project.restart_dry_run ? "Dry Run Restart" : "Restart Now"}
              </button>
            </>
          ) : (
            <p className="text-xs text-[#6b7680]">No restart command configured yet.</p>
          )}
        </div>

        {/* Tokens */}
        <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-[#2a2f32] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#e0e3e5]">Recent Tokens</h2>
            <button onClick={() => router.push("/tokens")} className="text-xs text-blue-400 hover:text-blue-300">View all →</button>
          </div>
          <div className="divide-y divide-[#2a2f32]">
            {tokens.slice(0, 10).map((t: any) => (
              <div key={t.id} onClick={() => router.push(`/tokens/${t.id}`)} className="px-5 py-3 flex items-center justify-between cursor-pointer hover:bg-[#22282b]">
                <div>
                  <p className="text-sm text-[#e0e3e5]">{t.license_number}</p>
                  <p className="text-xs text-[#6b7680]">{t.customer?.name} · {t.license_type}</p>
                </div>
                <Badge value={t.status} />
              </div>
            ))}
            {!tokens.length && <p className="px-5 py-4 text-sm text-[#6b7680]">No tokens for this project.</p>}
          </div>
        </div>
      </div>

      {/* Edit Modal */}
      <Modal title="Edit Project" open={showEdit} onClose={() => setShowEdit(false)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Name *</label>
            <input className="field" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Description</label>
            <textarea className="field resize-none" rows={2} value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Type</label>
              <input className="field" value={editForm.type} onChange={(e) => setEditForm({ ...editForm, type: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Status</label>
              <select className="field" value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                <option>Development</option><option>Staging</option><option>Production</option><option>Archived</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Version</label>
              <input className="field" value={editForm.version} onChange={(e) => setEditForm({ ...editForm, version: e.target.value })} placeholder="1.0.0" />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setShowEdit(false)} className="btn-ghost">Cancel</button>
            <button onClick={() => updateMut.mutate(editForm)} disabled={updateMut.isPending} className="btn-primary">
              {updateMut.isPending ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Re-import Key Modal */}
      <Modal title="Re-import Private Key" open={showReimport} onClose={() => setShowReimport(false)}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <p className="text-sm text-[#9aa3ab]">Paste the raw Base64-encoded Ed25519 private key. The public key will be derived automatically.</p>
          <textarea className="field font-mono resize-none" rows={3} value={privateKey} onChange={(e) => setPrivateKey(e.target.value)} placeholder="Base64 private key…" />
          <div className="flex justify-end gap-3">
            <button onClick={() => setShowReimport(false)} className="btn-ghost">Cancel</button>
            <button onClick={() => reimportMut.mutate()} disabled={reimportMut.isPending || !privateKey.trim()} className="btn-primary">
              {reimportMut.isPending ? "Updating…" : "Update Key"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Restart Settings Modal */}
      <Modal title="Restart Settings" open={showRestartSettings} onClose={() => setShowRestartSettings(false)}>
        {restartErr && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{restartErr}</p>}
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Server</label>
            <select className="field" value={restartForm.restart_server_id} onChange={(e) => setRestartForm((f) => ({ ...f, restart_server_id: e.target.value }))}>
              <option value="">Select server…</option>
              {servers.map((s: any) => <option key={s.id} value={s.id}>{s.name}{!s.ssh_host ? " (no SSH configured)" : ""}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Restart Command</label>
            <textarea className="field font-mono text-xs resize-none" rows={2} value={restartForm.restart_command}
              onChange={(e) => setRestartForm((f) => ({ ...f, restart_command: e.target.value }))}
              placeholder="e.g. cd /opt/myapp && docker compose restart api" />
          </div>
          <label className="flex items-center gap-2 text-xs text-[#9aa3ab]">
            <input type="checkbox" checked={restartForm.go_live} onChange={(e) => setRestartForm((f) => ({ ...f, go_live: e.target.checked }))} />
            Go live now (unchecked = dry run, safe default — logs the command instead of running it)
          </label>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => setShowRestartSettings(false)} className="btn-ghost">Cancel</button>
            <button onClick={() => restartSettingsMut.mutate(restartForm)} disabled={restartSettingsMut.isPending} className="btn-primary">
              {restartSettingsMut.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-[#6b7680]">{label}</span>
      <span className="text-sm text-[#e0e3e5]">{value}</span>
    </div>
  );
}
