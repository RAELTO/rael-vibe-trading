import { useState, useEffect } from "react";

export type Breakpoint = "mobile" | "tablet" | "desktop";

export function useWindowSize() {
  const [size, setSize] = useState(() => ({
    w: typeof window !== "undefined" ? window.innerWidth  : 1280,
    h: typeof window !== "undefined" ? window.innerHeight : 800,
  }));

  useEffect(() => {
    setSize({ w: window.innerWidth, h: window.innerHeight });
    const handler = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  const bp: Breakpoint =
    size.w < 768  ? "mobile"  :
    size.w < 1100 ? "tablet"  :
                    "desktop";

  return { ...size, bp };
}
