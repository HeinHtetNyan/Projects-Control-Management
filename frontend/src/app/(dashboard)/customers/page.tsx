"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "@/lib/api";
import Topbar from "@/components/layout/Topbar";
import Badge from "@/components/ui/Badge";
import Modal from "@/components/ui/Modal";
import { Plus, Edit3, Trash2 } from "lucide-react";
import { format } from "date-fns";

const EMPTY = { name: "", company_name: "", email: "", phone: "", country: "", notes: "", status: "active" };

export default function CustomersPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editCustomer, setEditCustomer] = useState<any>(null);
  const [form, setForm] = useState(EMPTY);
  const [err, setErr] = useState("");

  const { data: customers = [], isLoading } = useQuery({
    queryKey: ["customers"],
    queryFn: () => api.get("/api/customers").then((r) => r.data),
  });

  const createMut = useMutation({
    mutationFn: (body: typeof EMPTY) => api.post("/api/customers", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["customers"] }); setShowCreate(false); setForm(EMPTY); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: typeof EMPTY }) => api.put(`/api/customers/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["customers"] }); setEditCustomer(null); },
    onError: (e) => setErr(getErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/api/customers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["customers"] }),
  });

  function openEdit(c: any) {
    setForm({ name: c.name, company_name: c.company_name || "", email: c.email || "", phone: c.phone || "", country: c.country || "", notes: c.notes || "", status: c.status });
    setErr(""); setEditCustomer(c);
  }

  const F = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div>
      <Topbar
        title="Customers"
        description={`${customers.length} customer${customers.length !== 1 ? "s" : ""}`}
        action={<button onClick={() => { setForm(EMPTY); setErr(""); setShowCreate(true); }} className="btn-primary flex items-center gap-2"><Plus size={16} /> Add Customer</button>}
      />

      <div className="p-6">
        <div className="bg-[#1d2022] border border-[#2a2f32] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2f32]">
                {["Name", "Company", "Email", "Phone", "Country", "Status", "Created", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-medium text-[#6b7680]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2f32]">
              {isLoading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-[#6b7680]">Loading…</td></tr>
              ) : customers.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-[#6b7680]">No customers yet.</td></tr>
              ) : customers.map((c: any) => (
                <tr key={c.id} className="hover:bg-[#22282b]">
                  <td className="px-4 py-3 text-[#e0e3e5] font-medium">{c.name}</td>
                  <td className="px-4 py-3 text-[#9aa3ab]">{c.company_name || "—"}</td>
                  <td className="px-4 py-3 text-[#9aa3ab]">{c.email || "—"}</td>
                  <td className="px-4 py-3 text-[#9aa3ab]">{c.phone || "—"}</td>
                  <td className="px-4 py-3 text-[#9aa3ab]">{c.country || "—"}</td>
                  <td className="px-4 py-3"><Badge value={c.status} /></td>
                  <td className="px-4 py-3 text-[#6b7680]">{format(new Date(c.created_at), "MMM d, yyyy")}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button onClick={() => openEdit(c)} className="btn-ghost p-1.5"><Edit3 size={14} /></button>
                      <button onClick={() => { if (confirm(`Delete "${c.name}"?`)) deleteMut.mutate(c.id); }} className="btn-danger p-1.5"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create / Edit Modal */}
      {[{ show: showCreate, title: "Add Customer", onClose: () => setShowCreate(false), onSubmit: () => createMut.mutate(form), pending: createMut.isPending, btnLabel: "Add Customer" },
        { show: !!editCustomer, title: "Edit Customer", onClose: () => setEditCustomer(null), onSubmit: () => updateMut.mutate({ id: editCustomer.id, body: form }), pending: updateMut.isPending, btnLabel: "Save Changes" },
      ].map(({ show, title, onClose, onSubmit, pending, btnLabel }) => (
        <Modal key={title} title={title} open={show} onClose={onClose}>
          {err && <p className="mb-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{err}</p>}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Name *</label><input className="field" value={form.name} onChange={F("name")} /></div>
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Company</label><input className="field" value={form.company_name} onChange={F("company_name")} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Email <span className="text-[#6b7680]">(optional)</span></label><input className="field" type="email" value={form.email} onChange={F("email")} /></div>
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Phone <span className="text-[#6b7680]">(optional)</span></label><input className="field" value={form.phone} onChange={F("phone")} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Country <span className="text-[#6b7680]">(optional)</span></label><input className="field" value={form.country} onChange={F("country")} /></div>
              <div><label className="block text-xs text-[#9aa3ab] mb-1">Status</label>
                <select className="field" value={form.status} onChange={F("status")}><option value="active">active</option><option value="inactive">inactive</option></select>
              </div>
            </div>
            <div><label className="block text-xs text-[#9aa3ab] mb-1">Notes</label><textarea className="field resize-none" rows={2} value={form.notes} onChange={F("notes")} /></div>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={onClose} className="btn-ghost">Cancel</button>
              <button onClick={onSubmit} disabled={pending || !form.name} className="btn-primary">{pending ? "Saving…" : btnLabel}</button>
            </div>
          </div>
        </Modal>
      ))}
    </div>
  );
}
