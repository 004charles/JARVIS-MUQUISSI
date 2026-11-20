import { Bell, CheckCheck } from "lucide-react";
import type { NotificationItem } from "../types/api";

interface NotificationsPopoverProps {
  open: boolean;
  unreadCount: number;
  items: NotificationItem[];
  onToggle: () => void;
  onMarkAllRead: () => void;
}

export function NotificationsPopover({
  open,
  unreadCount,
  items,
  onToggle,
  onMarkAllRead,
}: NotificationsPopoverProps) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        title="Notificações do sistema"
        className="relative flex h-8 w-8 items-center justify-center rounded-full border border-cyan-500/30 bg-slate-900/70 text-cyan-200 transition hover:border-cyan-400"
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 font-mono text-[9px] font-bold text-white">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 rounded-2xl border border-cyan-500/30 bg-slate-950/90 p-3 text-xs shadow-[0_0_32px_rgba(6,182,212,0.2)] backdrop-blur-xl">
          <div className="mb-2 flex items-center justify-between border-b border-cyan-500/15 pb-2">
            <span className="font-mono text-[11px] uppercase tracking-wider text-cyan-300">
              Notificações ({unreadCount})
            </span>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={onMarkAllRead}
                className="flex items-center gap-1 font-mono text-[10px] text-cyan-300 hover:text-cyan-100"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Marcar lidas
              </button>
            )}
          </div>

          <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {items.length === 0 ? (
              <p className="py-2 text-center text-slate-400">Sem notificações registadas.</p>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  className={`rounded-xl border px-3 py-2 ${
                    n.severity === "critical"
                      ? "border-rose-500/35 bg-rose-950/35"
                      : n.severity === "warning"
                        ? "border-amber-500/35 bg-amber-950/30"
                        : "border-cyan-500/20 bg-slate-900/60"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-100">{n.title}</span>
                    {!n.read && (
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] text-slate-300">{n.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
