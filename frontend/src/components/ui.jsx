// Small shared pieces.
export const LEVEL = {
  green: { color: "#5fbf8a", label: "Green", text: "Minor. Can be managed at home." },
  yellow: { color: "#e3c46d", label: "Yellow", text: "See a doctor within 1–3 days." },
  orange: { color: "#e39a5b", label: "Orange", text: "See a doctor today." },
  red: { color: "#e0605e", label: "Red", text: "Emergency. Call 108 / 112 now." },
};

export function LevelBadge({ level }) {
  const l = LEVEL[level] || { color: "#a9a6a9", label: level || "—" };
  return (
    <span className="level">
      <i style={{ background: l.color, boxShadow: `0 0 10px ${l.color}` }} />
      {l.label}
    </span>
  );
}

export function Typing() {
  return (
    <span className="typing">
      <span />
      <span />
      <span />
    </span>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return <div className="notice error">⚠️ {error}</div>;
}

export function Emergency() {
  return (
    <div className="card" style={{ border: "1px solid rgba(224,96,94,0.55)" }}>
      <div className="card-title">
        <h3>🚑 This could be an emergency</h3>
        <LevelBadge level="red" />
      </div>
      <p className="small muted" style={{ marginTop: 0 }}>
        Call an ambulance or go to the nearest hospital emergency department now. Don't take any medicine on your own.
      </p>
      <div className="actions">
        <a className="btn-glow" href="tel:108">Call 108 (ambulance)</a>
        <a className="pill-outline" href="tel:112">Call 112</a>
      </div>
    </div>
  );
}
