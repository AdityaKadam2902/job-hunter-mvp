const DIMENSIONS = [
  { key: "similarity", label: "SIM" },
  { key: "keyword", label: "SKL" },
  { key: "seniority", label: "LVL" },
  { key: "domain", label: "DOM" },
  { key: "ai_fit", label: "AI" },
];

export default function SignalBars({ breakdown }) {
  return (
    <div className="signal-bars" title="Similarity · Skills · Level fit · Domain fit · AI-specificity">
      {DIMENSIONS.map((d) => {
        const value = breakdown[d.key] ?? 0;
        return (
          <div className="signal-bar-track" key={d.key}>
            <div className="signal-bar-fill" style={{ height: `${Math.max(6, value * 100)}%` }} />
            <span className="signal-bar-label">{d.label}</span>
          </div>
        );
      })}
    </div>
  );
}