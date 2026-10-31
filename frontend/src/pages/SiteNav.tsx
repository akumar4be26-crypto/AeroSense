import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

export const NAV_SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "weather", label: "Weather" },
  { id: "outlook", label: "Outlook" },
  { id: "model", label: "Our model" },
  { id: "travel", label: "Safe travel" },
  { id: "diversions", label: "Diversions" },
  { id: "map", label: "Map" },
  { id: "advice", label: "Advice" },
  { id: "simulator", label: "Simulator" },
] as const;

interface Props {
  mode: string;
  live: boolean;
  onRefresh: () => void;
}

export default function SiteNav({ mode, live, onRefresh }: Props) {
  const [active, setActive] = useState<string>(NAV_SECTIONS[0].id);
  const lockUntil = useRef(0); // a clicked link wins while the page scrolls to it

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      if (performance.now() < lockUntil.current) return;
      const threshold = window.innerHeight * 0.3;
      const passed = NAV_SECTIONS.flatMap((s) => {
        const el = document.getElementById(s.id);
        return el && el.getBoundingClientRect().top <= threshold ? [{ id: s.id, top: el.offsetTop }] : [];
      });
      if (!passed.length) return setActive(NAV_SECTIONS[0].id);
      // Sections sharing a grid row have near-equal offsets; the earlier one in nav order wins.
      const deepest = Math.max(...passed.map((p) => p.top));
      setActive(passed.find((p) => deepest - p.top < 40)!.id);
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <nav className="site-nav glass" aria-label="Sections">
      <a className="brand" href="#overview" aria-label="AERIS, back to top"><strong>AERIS</strong></a>
      <ul className="nav-links">
        {NAV_SECTIONS.map((s) => (
          <li key={s.id}>
            <a href={`#${s.id}`} onClick={() => { lockUntil.current = performance.now() + 1000; setActive(s.id); }} aria-current={active === s.id ? "true" : undefined}>{s.label}</a>
          </li>
        ))}
      </ul>
      <div className="nav-end">
        <span className={`connection-pill ${live ? "is-live" : ""}`}><span className="live-dot" /> {mode} data</span>
        <button className="icon-button" type="button" onClick={onRefresh} aria-label="Refresh environmental data">
          <RefreshCw size={16} />
        </button>
      </div>
    </nav>
  );
}
