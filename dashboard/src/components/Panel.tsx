import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
  accentColor?: string;
}

export function Panel({ title, children, className = "", action, accentColor }: PanelProps) {
  return (
    <section
      className={`glass-panel rounded-xl flex flex-col overflow-hidden animate-flow-in ${className}`}
      style={accentColor ? { boxShadow: `0 0 0 1px ${accentColor}40, 0 4px 24px ${accentColor}10` } : undefined}
    >
      <header
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <h2
          className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "#8888aa" }}
        >
          {title}
        </h2>
        {action}
      </header>
      <div className="flex-1 overflow-auto">{children}</div>
    </section>
  );
}
