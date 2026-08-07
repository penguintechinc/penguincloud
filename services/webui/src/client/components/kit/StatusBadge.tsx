/**
 * StatusBadge component
 * Maps health status to visual indicator: healthy/degraded/down/unknown
 * Used in health checks, dashboards, and status displays
 */

interface StatusBadgeProps {
  status: "healthy" | "degraded" | "down" | "unknown";
  size?: "sm" | "md" | "lg";
}

const statusColorMap: Record<
  string,
  { bg: string; text: string; dot: string }
> = {
  healthy: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    dot: "bg-emerald-500",
  },
  degraded: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    dot: "bg-amber-500",
  },
  down: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    dot: "bg-red-500",
  },
  unknown: {
    bg: "bg-slate-500/10",
    text: "text-slate-400",
    dot: "bg-slate-500",
  },
};

const statusLabelMap: Record<string, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  unknown: "Unknown",
};

const sizeMap: Record<string, string> = {
  sm: "px-2 py-1 text-xs",
  md: "px-3 py-1.5 text-sm",
  lg: "px-4 py-2 text-base",
};

export default function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const colors = statusColorMap[status] || statusColorMap.unknown;
  const label = statusLabelMap[status] || "Unknown";
  const sizeClass = sizeMap[size];

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full ${colors.bg} ${sizeClass} font-medium`}
      data-testid="status-badge"
      role="status"
      aria-label={label}
    >
      <div className={`w-2 h-2 rounded-full ${colors.dot}`} />
      <span className={colors.text}>{label}</span>
    </div>
  );
}
