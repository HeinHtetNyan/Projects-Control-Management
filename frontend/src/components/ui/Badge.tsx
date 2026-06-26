import clsx from "clsx";

const VARIANTS: Record<string, string> = {
  active: "bg-green-500/10 text-green-400 border-green-500/20",
  running: "bg-green-500/10 text-green-400 border-green-500/20",
  success: "bg-green-500/10 text-green-400 border-green-500/20",
  online: "bg-green-500/10 text-green-400 border-green-500/20",
  pending: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  used: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  lifetime: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  annual: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  "6month": "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  monthly: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  trial: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  revoked: "bg-red-500/10 text-red-400 border-red-500/20",
  expired: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  suspended: "bg-red-500/10 text-red-400 border-red-500/20",
  blocked: "bg-red-500/10 text-red-400 border-red-500/20",
  stopped: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  maintenance: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  inactive: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  Development: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  Production: "bg-green-500/10 text-green-400 border-green-500/20",
  Archived: "bg-slate-500/10 text-slate-400 border-slate-500/20",
};

export default function Badge({ value }: { value: string }) {
  const cls = VARIANTS[value] ?? "bg-[#2a2f32] text-[#9aa3ab] border-[#3a4147]";
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border", cls)}>
      {value}
    </span>
  );
}
