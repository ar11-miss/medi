// Area chart drawn in SVG, styled like the reference "Portfolio Performance" card:
// soft pink line, fading area fill, glowing dot, dashed guide and a dark tooltip.
import { useMemo, useState } from "react";

const W = 900;
const H = 230;
const PAD = { l: 44, r: 16, t: 18, b: 30 };

function smoothPath(pts) {
  if (pts.length < 2) return "";
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] || p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${p2[0]},${p2[1]}`;
  }
  return d;
}

export default function AreaChart({ values, labels, yMax = 10, yTicks = [0, 2, 4, 6, 8, 10], tooltip }) {
  const [hover, setHover] = useState(null);
  const pts = useMemo(() => {
    const n = values.length;
    return values.map((v, i) => [
      PAD.l + (n === 1 ? (W - PAD.l - PAD.r) / 2 : (i * (W - PAD.l - PAD.r)) / (n - 1)),
      PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b),
    ]);
  }, [values, yMax]);
  const line = smoothPath(pts);
  const area = pts.length > 1 ? `${line} L${pts.at(-1)[0]},${H - PAD.b} L${pts[0][0]},${H - PAD.b} Z` : "";
  const active = hover ?? pts.length - 1;
  const ap = pts[active];

  return (
    <div className="chart-wrap" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Symptom score by day"
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const x = ((e.clientX - r.left) / r.width) * W;
          let best = 0;
          pts.forEach((p, i) => { if (Math.abs(p[0] - x) < Math.abs(pts[best][0] - x)) best = i; });
          setHover(best);
        }}>
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d3b1c9" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#d3b1c9" stopOpacity="0" />
          </linearGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        {yTicks.map((t) => {
          const y = PAD.t + (1 - t / yMax) * (H - PAD.t - PAD.b);
          return (
            <text key={t} x={PAD.l - 14} y={y + 4} textAnchor="end" fontSize="11" fill="#b9b3b9">{t}</text>
          );
        })}
        {area && <path d={area} fill="url(#area)" />}
        {line && <path d={line} fill="none" stroke="#e7c6df" strokeWidth="2" filter="url(#glow)" />}
        {labels.map((l, i) => (
          <text key={i} x={pts[i][0]} y={H - 8} textAnchor="middle" fontSize="11" fill="#b9b3b9">{l}</text>
        ))}
        {ap && (
          <g>
            <line x1={ap[0]} x2={ap[0]} y1={ap[1] + 10} y2={H - PAD.b} stroke="rgba(255,255,255,0.55)" strokeDasharray="3 4" />
            <circle cx={ap[0]} cy={ap[1]} r="13" fill="#fecff2" opacity="0.22" />
            <circle cx={ap[0]} cy={ap[1]} r="6.5" fill="#fecff2" filter="url(#glow)" />
          </g>
        )}
      </svg>
      {ap && tooltip && (
        <div className={`tooltip ${ap[0] > W * 0.82 ? "right" : ap[0] < W * 0.18 ? "left" : ""}`}
          style={{ left: `${(ap[0] / W) * 100}%`, top: `calc(${(ap[1] / H) * 100}% - 18px)` }}>
          {tooltip(active)}
        </div>
      )}
    </div>
  );
}
