interface HardStopBannerProps {
  message: string;
}

export function HardStopBanner({ message }: HardStopBannerProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.88)", backdropFilter: "blur(12px)" }}
    >
      <div
        className="max-w-lg w-full mx-4 rounded-2xl p-8 shadow-2xl"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(240,80,96,0.5)",
          boxShadow: "0 0 60px rgba(240,80,96,0.15), 0 25px 50px rgba(0,0,0,0.5)",
        }}
      >
        <div className="flex flex-col items-center gap-5 text-center">
          {/* Icon */}
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center"
            style={{ background: "rgba(240,80,96,0.1)", border: "1px solid rgba(240,80,96,0.3)" }}
          >
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L2 19.5H22L12 2Z"
                stroke="#f05060"
                strokeWidth="1.5"
                fill="rgba(240,80,96,0.1)"
              />
              <path d="M12 9V13M12 16.5V17" stroke="#f05060" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>

          <div>
            <h2
              className="text-xl font-bold mb-1"
              style={{ color: "#f05060", fontFamily: "'Space Grotesk', sans-serif" }}
            >
              HARD STOP
            </h2>
            <p className="text-sm" style={{ color: "#8888aa" }}>Límite de pérdida alcanzado</p>
          </div>

          <p
            className="text-sm leading-relaxed rounded-lg px-4 py-3 text-left"
            style={{
              color: "#e8e8f0",
              background: "rgba(240,80,96,0.06)",
              border: "1px solid rgba(240,80,96,0.2)",
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "12px",
            }}
          >
            {message}
          </p>

          <div
            className="w-full pt-4 space-y-2 text-xs"
            style={{ borderTop: "1px solid rgba(255,255,255,0.06)", color: "#8888aa" }}
          >
            <p className="font-semibold" style={{ color: "#e8e8f0" }}>Para reiniciar el sistema:</p>
            <ol className="text-left space-y-1.5 list-decimal list-inside" style={{ color: "#8888aa" }}>
              <li>
                Ve a <span style={{ color: "#00d4ff" }}>demo.binance.com → Futures</span>
              </li>
              <li>
                Busca <span style={{ color: "#e8e8f0" }}>Reset Assets</span> en configuración demo
              </li>
              <li>
                Reinicia:{" "}
                <code
                  className="rounded px-1.5 py-0.5"
                  style={{ background: "rgba(255,255,255,0.06)", color: "#00d4ff" }}
                >
                  python core/orchestrator.py
                </code>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
