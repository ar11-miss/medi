import { useState } from "react";
import { ArrowUpRight, ChevronDown, ClipboardList, HeartPulse, Pill, Stethoscope, Timer, UserRound } from "lucide-react";
import AreaChart from "../components/AreaChart.jsx";
import { LevelBadge } from "../components/ui.jsx";

const RANGES = [
  { id: "7", label: "1W" },
  { id: "14", label: "2W" },
  { id: "all", label: "All" },
];

export default function Dashboard({ data, go, loaded }) {
  const c = data.case;
  const r = data.result || {};
  const [tab, setTab] = useState("result");
  const [range, setRange] = useState("all");
  const plant = c?.plant;

  // chart: day 1 score, then one point per check-in
  const all = c ? c.scores : [];
  const shown = range === "all" ? all : all.slice(-Number(range));
  const offset = all.length - shown.length;
  const labels = shown.map((_, i) => `Day ${offset + i + 1}`);

  const badges = c ? [...c.badges, ...c.locked_badges].slice(0, 4) : [];
  const earned = new Set((c?.badges || []).map((b) => b.key));

  return (
    <>
      <div className="grid-top">
        <div className="stack">
          {/* like "Total Holding" */}
          <div className="card glow">
            <div className="card-title">
              <h3>Tulsi Growth</h3>
              <div style={{ display: "flex", gap: 6 }}>
                <span className="pill-outline">{plant ? plant.name : "Seed"}</span>
                <button className="circle-outline" aria-label="Open check-in" onClick={() => go("checkin")}><ChevronDown size={15} /></button>
              </div>
            </div>
            <div className="big-number">{c ? c.xp : 0} XP</div>
            <div className="small muted">
              {plant?.next_stage_xp ? `${plant.next_stage_xp - plant.xp} XP to the next stage` : c ? "Fully grown!" : "Check in daily to grow your plant"}
            </div>
          </div>

          {/* like "Decisions Powered by Data" */}
          <div className="card arc">
            <h3>Feeling Unwell?</h3>
            <p>Tell MediAid your symptoms in English, Hindi or Marathi. Get a severity level, home care and the right doctor.</p>
            <button className="btn-glow" onClick={() => go("symptoms")}>Check Symptoms</button>
          </div>
        </div>

        {/* like "Watchlist" */}
        <div className="card">
          <div className="card-title"><h3>Latest Result</h3></div>
          <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            {[["result", "Result"], ["care", "Home care"], ["doctor", "Doctor"]].map(([id, label]) => (
              <button key={id} className={`chip ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>{label}</button>
            ))}
          </div>
          {!c ? (
            <div className="empty">
              {loaded ? "No symptom check yet." : "Loading…"}
              <div className="actions" style={{ justifyContent: "center" }}>
                <button className="pill-outline" onClick={() => go("symptoms")}>Start a check</button>
              </div>
            </div>
          ) : tab === "result" ? (
            <div>
              <Row icon={<HeartPulse size={18} />} title="Severity" sub={r.meaning} val={<LevelBadge level={c.level} />} />
              <Row icon={<ClipboardList size={18} />} title={cap(c.condition || r.condition || "—")} sub="Likely problem" />
              <Row icon={<UserRound size={18} />} title={c.specialty || "General Physician"} sub="Who to see" />
              <Row icon={<Timer size={18} />} title={`Day ${c.day}`} sub="Recovery day"
                val={<span>{Math.round(c.recovery_progress * 100)}%<small className="green">recovered</small></span>} />
            </div>
          ) : tab === "care" ? (
            <div>
              {r.remedies?.matched ? (
                <>
                  {(r.remedies.medicines || []).slice(0, 2).map((m) => (
                    <Row key={m.id} icon={<Pill size={18} />} title={m.name} sub={m.how_to_take} />
                  ))}
                  {(r.remedies.home_care || []).slice(0, 4 - Math.min(2, (r.remedies.medicines || []).length)).map((h, i) => (
                    <Row key={i} icon={<span>🏠</span>} title={h} />
                  ))}
                </>
              ) : (
                <div className="empty">{r.remedies?.summary || "No home-care advice for this result."}</div>
              )}
            </div>
          ) : (
            <div>
              <Row icon={<Stethoscope size={18} />} title={c.specialty || "General Physician"} sub={r.meaning}
                val={<LevelBadge level={c.level} />} />
              <div className="actions"><button className="btn-glow" onClick={() => go("doctors")}>Find nearby</button></div>
            </div>
          )}
        </div>

        {/* like "My Portfolio" */}
        <div className="card">
          <div className="card-title">
            <h3>My Badges</h3>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="pill-outline" onClick={() => go("checkin")}>See all</button>
              <button className="circle-outline" aria-label="Open check-in" onClick={() => go("checkin")}><ArrowUpRight size={15} /></button>
            </div>
          </div>
          {c ? (
            <div className="mini-grid">
              {badges.map((b) => (
                <div key={b.key} className={`mini ${earned.has(b.key) ? "" : "locked"}`}>
                  <div className="head">{b.name}</div>
                  <div className={`tiny ${earned.has(b.key) ? "green" : "muted"}`}>{earned.has(b.key) ? "Earned" : "Locked"}</div>
                  <div className="foot"><span style={{ fontSize: 20 }}>{b.emoji}</span><span className="tiny" style={{ textAlign: "right", maxWidth: 90 }}>{b.description}</span></div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty">Badges unlock as you check in every day.</div>
          )}
        </div>
      </div>

      {/* like "Portfolio Performance" */}
      <div className="card" style={{ background: "var(--card-2)" }}>
        <div className="card-title">
          <h3>Recovery Progress</h3>
          <div style={{ display: "flex", gap: 6 }}>
            {RANGES.map((x) => (
              <button key={x.id} className={`range ${range === x.id ? "active" : ""}`} onClick={() => setRange(x.id)}>{x.label}</button>
            ))}
          </div>
        </div>
        {shown.length >= 2 ? (
          <AreaChart values={shown} labels={labels}
            tooltip={(i) => {
              const prev = i > 0 ? shown[i - 1] : null;
              const diff = prev === null ? null : prev - shown[i];
              return (
                <>
                  <span className="muted">{labels[i]}</span>
                  <b>Score {shown[i]}/10 {diff !== null && diff > 0 && <span className="tag-green">↓ {diff} better</span>}</b>
                </>
              );
            }} />
        ) : (
          <div className="empty">Check in for a few days to see your recovery curve here. Lower score = feeling better.</div>
        )}
      </div>
    </>
  );
}

function Row({ icon, title, sub, val }) {
  return (
    <div className="row">
      <div className="ico">{icon}</div>
      <div className="txt"><b>{title}</b>{sub && <small>{sub}</small>}</div>
      {val && <div className="val">{val}</div>}
    </div>
  );
}

function cap(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}
