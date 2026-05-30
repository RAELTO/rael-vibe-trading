export type MobileTab = "overview" | "position" | "intel" | "pipeline";

const TABS: { id: MobileTab; label: string; icon: React.ReactNode }[] = [
  {
    id: "overview",
    label: "OVERVIEW",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="2" y="2" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.9" />
        <rect x="10" y="2" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.5" />
        <rect x="2" y="10" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.5" />
        <rect x="10" y="10" width="6" height="6" rx="1.5" fill="currentColor" opacity="0.5" />
      </svg>
    ),
  },
  {
    id: "position",
    label: "POSITION",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M9 2L15 6V12L9 16L3 12V6L9 2Z" stroke="currentColor" strokeWidth="1.5" fill="none" />
        <circle cx="9" cy="9" r="2" fill="currentColor" opacity="0.8" />
      </svg>
    ),
  },
  {
    id: "intel",
    label: "INTEL",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
        <path d="M6 9h6M9 6v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "pipeline",
    label: "PIPELINE",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <circle cx="4"  cy="5"  r="2" fill="currentColor" opacity="0.7" />
        <circle cx="14" cy="5"  r="2" fill="currentColor" opacity="0.7" />
        <circle cx="9"  cy="13" r="2" fill="currentColor" />
        <path d="M4 7v2l5 2M14 7v2l-5 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
    ),
  },
];

interface MobileTabBarProps {
  active: MobileTab;
  onChange: (tab: MobileTab) => void;
}

export function MobileTabBar({ active, onChange }: MobileTabBarProps) {
  return (
    <div style={{
      display: "flex",
      alignItems: "stretch",
      borderTop: "1px solid rgba(255,255,255,0.07)",
      background: "rgba(3,3,10,0.97)",
      backdropFilter: "blur(20px)",
      flexShrink: 0,
      height: 60,
      position: "sticky",
      bottom: 0,
      zIndex: 20,
    }}>
      {TABS.map(tab => {
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 3,
              background: "none",
              border: "none",
              cursor: "pointer",
              color: isActive ? "#00d4ff" : "#44445a",
              transition: "color 0.2s",
              position: "relative",
            }}
          >
            {isActive && (
              <div style={{
                position: "absolute",
                top: 0,
                left: "20%",
                right: "20%",
                height: 2,
                background: "#00d4ff",
                borderRadius: "0 0 2px 2px",
                boxShadow: "0 0 6px #00d4ff",
              }} />
            )}
            {tab.icon}
            <span style={{
              fontSize: 9,
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
              letterSpacing: "0.5px",
            }}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
