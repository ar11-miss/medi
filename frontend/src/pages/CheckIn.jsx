import { useState } from "react";
import { Check, Flame } from "lucide-react";
import { api } from "../api.js";
import { ErrorNote, LevelBadge, Typing } from "../components/ui.jsx";

const FEELINGS = [
  { id: "better", emoji: "😊", label: "Better" },
  { id: "same", emoji: "😐", label: "Same" },
  { id: "worse", emoji: "😟", label: "Worse" },
];

export default function CheckIn({ data, refresh, go, loaded }) {
  const c = data.case;
  const [feeling, setFeeling] = useState("");
  const [score, setScore] = useState(5);
  const [done, setDone] = useState([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reward, setReward] = useState(null);

  if (!c) {
    return (
      <div className="card arc" style={{ maxWidth: 520 }}>
        <h3>Plant Your Tulsi</h3>
        <p>{loaded ? "Start with a symptom check. Then check in every day to earn XP, keep your streak and grow your Tulsi." : "Loading…"}</p>
        <button className="btn-glow" onClick={() => go("symptoms")}>I feel unwell</button>
      </div>
    );
  }

  const toggle = (id) => setDone((d) => (d.includes(id) ? d.filter((x) => x !== id) : [...d, id]));
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api.checkin(c.case_id, { feeling, score, quests_done: done, note });
      setReward(r);
      setFeeling("");
      setDone([]);
      setNote("");
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="two-col">
      <div className="stack">
        {reward ? (
          <Reward r={reward} go={go} close={() => setReward(null)} />
        ) : (
          <div className="card">
            <div className="card-title">
              <h3>Day {c.day} Check-in</h3>
              {c.checked_in_today ? <span className="tiny green">✓ Done today</span> : <span className="tiny muted">{c.condition}</span>}
            </div>

            <div className="section-label" style={{ marginTop: 0 }}>How do you feel compared to yesterday?</div>
            <div className="feel-row">
              {FEELINGS.map((f) => (
                <button key={f.id} className={`feel ${feeling === f.id ? "active" : ""}`} onClick={() => setFeeling(f.id)}>
                  <span>{f.emoji}</span>{f.label}
                </button>
              ))}
            </div>

            <div className="section-label">How bad are your symptoms now? <b style={{ color: "var(--text)" }}>{score}/10</b></div>
            <input type="range" min="1" max="10" value={score} className="slider"
              style={{ "--fill": `${((score - 1) / 9) * 100}%` }} onChange={(e) => setScore(Number(e.target.value))} />
            <div className="tiny muted" style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              <span>1 · no symptoms</span><span>10 · worst</span>
            </div>

            <div className="section-label">Today's quests · +5 XP each</div>
            <div className="stack" style={{ gap: 8 }}>
              {c.today_quests.map((q) => (
                <button key={q.id} className={`quest ${done.includes(q.id) ? "done" : ""}`} onClick={() => toggle(q.id)}>
                  <span style={{ fontSize: 18 }}>{q.emoji}</span>{q.title}
                  <span className="tick">{done.includes(q.id) && <Check size={14} strokeWidth={3} />}</span>
                </button>
              ))}
            </div>

            <div className="section-label">Anything else? (optional)</div>
            <input className="note-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. cough is less, slept well" />
            <ErrorNote error={error} />
            <div className="actions">
              <button className="btn-glow" disabled={!feeling || busy} onClick={submit}>
                {busy ? <Typing /> : c.checked_in_today ? "Update today's check-in" : "Check in"}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="stack">
        <div className="card glow" style={{ textAlign: "center" }}>
          <div className="card-title"><h3>Your Tulsi</h3><span className="pill-outline">{c.plant.name}</span></div>
          <div className="plant">{c.plant.emoji}</div>
          <div className="big-number">{c.xp} XP</div>
          <div className="bar" style={{ margin: "10px 0 6px" }}><div style={{ width: `${Math.round(c.plant.progress * 100)}%` }} /></div>
          <div className="tiny muted">{c.plant.next_stage_xp ? `${c.plant.next_stage_xp - c.xp} XP to the next stage` : "Fully grown! 🌸"}</div>
        </div>

        <div className="card">
          <div className="row">
            <div className="ico"><Flame size={20} color="#f9d7f8" /></div>
            <div className="txt"><b>{c.streak ? `${c.streak}-day streak` : "Start your streak today"}</b><small>Every 3rd day in a row: +15 XP bonus</small></div>
            <div className="val"><LevelBadge level={c.level} /></div>
          </div>
          <div className="row">
            <div className="ico">📈</div>
            <div className="txt"><b>{Math.round(c.recovery_progress * 100)}% recovered</b><small>Scores: {c.scores.join(" → ")}</small></div>
          </div>
        </div>

        <div className="card">
          <div className="card-title"><h3>Badges</h3><span className="tiny muted">{c.badges.length} / {c.badges.length + c.locked_badges.length}</span></div>
          <div className="mini-grid">
            {[...c.badges, ...c.locked_badges].map((b) => {
              const has = c.badges.some((x) => x.key === b.key);
              return (
                <div key={b.key} className={`mini ${has ? "" : "locked"}`}>
                  <div style={{ fontSize: 22 }}>{b.emoji}</div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{b.name}</div>
                  <div className="tiny muted">{b.description}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function Reward({ r, go, close }) {
  return (
    <div className="card arc" style={{ textAlign: "left" }}>
      <div style={{ textAlign: "center" }}>
        <div className="plant">{r.plant.emoji}</div>
        <div className="xp-burst">{r.already_checked_in_today ? "Updated" : `+${r.xp_gained} XP`}</div>
        <div className="small" style={{ color: "var(--text-2)" }}>🔥 {r.streak}-day streak · {r.plant.name}</div>
      </div>
      {r.new_badges.length > 0 && (
        <div className="mini-grid" style={{ marginTop: 14 }}>
          {r.new_badges.map((b) => (
            <div key={b.key} className="mini">
              <div style={{ fontSize: 22 }}>{b.emoji}</div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>New: {b.name}</div>
              <div className="tiny muted">{b.description}</div>
            </div>
          ))}
        </div>
      )}
      <p style={{ maxWidth: "none", textAlign: "left", fontSize: 14, marginTop: 14 }}>{r.message}</p>
      {r.recovered && <div className="notice">🎉 You've recovered! Your Tulsi is proud of you.</div>}
      {r.retriaged && (
        <div className="notice" style={{ marginTop: 10 }}>
          I checked your symptoms again: <LevelBadge level={r.level} /> {r.triage?.meaning} See: <b>{r.specialty}</b>.
          {r.see_doctor && <div className="actions"><button className="btn-glow" onClick={() => go("doctors")}>Find doctors</button></div>}
        </div>
      )}
      <div className="section-label">Tomorrow's quests</div>
      <ul className="clean">{r.tomorrow_quests.map((q) => <li key={q.id}>{q.emoji} {q.title}</li>)}</ul>
      <div className="actions"><button className="pill-outline" onClick={close}>Done</button></div>
    </div>
  );
}
