import { useRef, useState } from "react";
import { createPortal } from "react-dom";

const TIP_WIDTH = 210;
const TIP_EST_HEIGHT = 90;

/**
 * Wraps a trigger and shows an explanatory tooltip on hover.
 * The tooltip is rendered in a portal to document.body with position:fixed, so it
 * never gets clipped by ancestor `overflow` (e.g. a scrollable table container).
 */
export function HoverTip({
  tip,
  align = "right",
  children,
}: {
  tip: string;
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  function show() {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    let left = align === "right" ? r.right - TIP_WIDTH : r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - TIP_WIDTH - 8));
    const below = r.bottom + 6;
    const top = below + TIP_EST_HEIGHT > window.innerHeight ? Math.max(8, r.top - TIP_EST_HEIGHT) : below;
    setPos({ top, left });
  }

  return (
    <span
      ref={ref}
      onMouseEnter={show}
      onMouseLeave={() => setPos(null)}
      className="inline-flex items-center gap-1"
      style={{ cursor: "help" }}
    >
      {children}
      {pos &&
        createPortal(
          <div
            role="tooltip"
            style={{
              position: "fixed",
              top: pos.top,
              left: pos.left,
              width: TIP_WIDTH,
              padding: "6px 9px",
              borderRadius: 6,
              background: "#08080f",
              border: "1px solid rgba(0,212,255,0.2)",
              boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
              color: "#c8c8d8",
              fontSize: 10,
              lineHeight: 1.4,
              fontWeight: 400,
              textTransform: "none",
              letterSpacing: "normal",
              whiteSpace: "normal",
              textAlign: "left",
              fontFamily: "system-ui, sans-serif",
              pointerEvents: "none",
              zIndex: 9999,
            }}
          >
            {tip}
          </div>,
          document.body,
        )}
    </span>
  );
}
