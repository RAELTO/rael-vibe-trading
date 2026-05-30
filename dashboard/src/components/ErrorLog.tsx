import { AlertTriangle } from "lucide-react";
import { Panel } from "./Panel";

interface ErrorLogProps {
  errors: { message: string; ts: string }[];
}

export function ErrorLog({ errors }: ErrorLogProps) {
  if (errors.length === 0) return null;

  return (
    <Panel title="System Errors">
      <div>
        {errors.map((e, i) => (
          <div
            key={i}
            className="flex items-start gap-2.5 px-4 py-2.5"
            style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
          >
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: "#f05060" }} />
            <div className="flex-1 min-w-0">
              <p className="text-xs leading-snug break-words" style={{ color: "rgba(240,80,96,0.8)" }}>
                {e.message}
              </p>
              <p className="text-[10px] mt-0.5 font-mono" style={{ color: "#44445a" }}>
                {new Date(e.ts).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
