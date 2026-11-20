import { ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { apiClient } from "../services/api";
import type { PendingApprovalItem } from "../types/api";

interface ApprovalBannerProps {
  approvals: PendingApprovalItem[];
  onResolved: (approvalId: string, feedbackMessage: string) => void;
}

export function ApprovalBanner({ approvals, onResolved }: ApprovalBannerProps) {
  const [busyId, setBusyId] = useState<string | null>(null);

  if (approvals.length === 0) return null;

  const current = approvals[0];

  const handleApprove = async () => {
    setBusyId(current.approval_id);
    try {
      const res = await apiClient.approveAction(current.approval_id);
      onResolved(
        current.approval_id,
        res.status === "executed"
          ? `Ação '${res.tool}' autorizada e executada com sucesso.`
          : `Ação '${res.tool}' terminou com aviso: ${res.message}`,
      );
    } catch (err) {
      onResolved(
        current.approval_id,
        err instanceof Error ? err.message : "Erro ao aprovar ação.",
      );
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async () => {
    setBusyId(current.approval_id);
    try {
      await apiClient.rejectAction(current.approval_id);
      onResolved(
        current.approval_id,
        `Ação '${current.tool}' em '${current.target}' foi recusada.`,
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="z-20 mx-auto mb-2 w-full max-w-3xl rounded-2xl border border-amber-400/50 bg-amber-950/70 p-3.5 text-xs text-amber-100 backdrop-blur-md shadow-[0_0_24px_rgba(251,191,36,0.18)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-amber-200">
              Confirmação Necessária (Nível {current.permission_level}) · {current.tool}
            </p>
            <p className="mt-0.5 text-slate-200">
              Alvo: <code className="text-cyan-200">{current.target}</code> — {current.description}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busyId === current.approval_id}
            onClick={() => void handleReject()}
            className="flex items-center gap-1 rounded-xl border border-rose-400/45 bg-rose-500/15 px-3 py-1.5 font-mono text-[11px] text-rose-200 hover:bg-rose-500/25 disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            Recusar
          </button>
          <button
            type="button"
            disabled={busyId === current.approval_id}
            onClick={() => void handleApprove()}
            className="flex items-center gap-1 rounded-xl border border-emerald-400/55 bg-emerald-500/20 px-3 py-1.5 font-mono text-[11px] text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-50"
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            Autorizar
          </button>
        </div>
      </div>
    </div>
  );
}
