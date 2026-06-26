"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { Plus, Trash2 } from "lucide-react";
import { format } from "date-fns";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", slug: "", description: "", deep_link_scheme: "", type: "", status: "Development", version: "", import_private_key: "" });
  const [err, setErr] = useState("");

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get("/api/projects").then((r) => r.data),
  });

  const createMut = useMutation({
    mutationFn: (body: typeof form) => api.post("/api/projects", body),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setShowCreate(false);
      router.push(`/projects/${res.data.id}`);
    },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/api/projects/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  function slugify(name: string) {
    return name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
  }

  return (
    <div>
      <Topbar
        title="Projects"
        description={`${projects.length} project${projects.length !== 1 ? "s" : ""}`}
        action={
          <button onClick={() => { setForm({ name: "", slug: "", description: "", deep_link_scheme: "", type: "", status: "Development", version: "", import_private_key: "" }); setErr(""); setShowCreate(true); }} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> New Project
          </button>
        }
      />

      <div className="p-6">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((p: any) => (
              <div
                key={p.id}
                onClick={() => router.push(`/projects/${p.id}`)}
                className="bg-[#1d2022] border border-[#2a2f32] rounded-xl p-5 cursor-pointer hover:border-[#3a4147] transition-colors group"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="font-semibold text-[#e0e3e5] group-hover:text-white">{p.name}</p>
                    <p className="text-xs text-[#6b7680] font-mono mt-0.5">{p.slug}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge value={p.status || "Development"} />
                    <button
                      onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${p.name}"?`)) deleteMut.mutate(p.id); }}
                      className="opacity-0 group-hover:opacity-100 p-1.5 text-[#6b7680] hover:text-red-400 hover:bg-red-500/10 rounded transition-all"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                {p.description && <p className="text-sm text-[#9aa3ab] line-clamp-2 mb-3">{p.description}</p>}
                <div className="flex items-center justify-between text-xs text-[#6b7680]">
                  <span className="font-mono">{p.deep_link_scheme}://</span>
                  <span>{format(new Date(p.created_at), "MMM d, yyyy")}</span>
                </div>
              </div>
            ))}
            {!projects.length && (
              <p className="text-[#6b7680] text-sm col-span-3">No projects yet. Create your first one.</p>
            )}
          </div>
        )}
      </div>

      <Modal title="Create Project" open={showCreate} onClose={() => { setShowCreate(false); setErr(""); }}>
        {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Project Name *</label>
            <input className="field" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value, slug: slugify(e.target.value) })} placeholder="Repair & Sales ServiceDesk" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Slug *</label>
              <input className="field font-mono" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="repair-sales" />
            </div>
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Deep Link Scheme *</label>
              <input className="field font-mono" value={form.deep_link_scheme} onChange={(e) => setForm({ ...form, deep_link_scheme: e.target.value })} placeholder="sawyuntech" />
            </div>
          </div>
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Description</label>
            <textarea className="field resize-none" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Type</label>
              <input className="field" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} placeholder="Desktop App" />
            </div>
            <div>
              <label className="block text-xs text-[#9aa3ab] mb-1">Status</label>
              <select className="field" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option>Development</option>
                <option>Staging</option>
                <option>Production</option>
                <option>Archived</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-[#9aa3ab] mb-1">Import Private Key (optional — leave blank to auto-generate)</label>
            <textarea className="field font-mono resize-none" rows={2} value={form.import_private_key} onChange={(e) => setForm({ ...form, import_private_key: e.target.value })} placeholder="Base64-encoded Ed25519 private key" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button onClick={() => { setShowCreate(false); setErr(""); }} className="btn-ghost">Cancel</button>
            <button onClick={() => { setErr(""); createMut.mutate(form); }} disabled={createMut.isPending || !form.name || !form.slug || !form.deep_link_scheme} className="btn-primary">
              {createMut.isPending ? "Creating…" : "Create Project"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
