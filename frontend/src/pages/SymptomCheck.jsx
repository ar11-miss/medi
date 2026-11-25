import { useEffect, useRef, useState } from "react";
import { RotateCcw, SendHorizontal } from "lucide-react";
import { api } from "../api.js";
import { Emergency, ErrorNote, LevelBadge, Typing } from "../components/ui.jsx";

export default function SymptomCheck({ go, refresh, firstMessage, clearFirst }) {
  const [sid, setSid] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const listRef = useRef(null);
  const started = useRef(false);

  const start = async (initial) => {
    setError("");
    setResult(null);
    setMessages([]);
    try {
      const s = await api.startSymptoms();
      setSid(s.session_id);
      setMessages([{ who: "bot", text: s.greeting }]);
      if (initial) send(initial, s.session_id);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start(firstMessage);
    clearFirst();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send(value, sessionId = sid) {
    const t = value.trim();
    if (!t || !sessionId || busy) return;
    setText("");
    setError("");
    setMessages((m) => [...m, { who: "me", text: t }]);
    setBusy(true);
    try {
      const r = await api.sendSymptom(sessionId, t);
      if (r.done) {
        setResult(r.result);
        setMessages((m) => [...m, { who: "bot", text: "Thank you. Here is what I found. 👉" }]);
        refresh();
      } else {
        setMessages((m) => [...m, { who: "bot", text: r.question }]);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="two-col">
      <div className="card">
        <div className="card-title">
          <h3>Symptom Check</h3>
          <button className="pill-outline" onClick={() => start()}><RotateCcw size={13} /> New check</button>
        </div>
        <div className="chat">
          <div className="messages" ref={listRef}>
            {messages.map((m, i) => <div key={i} className={`bubble ${m.who}`}>{m.text}</div>)}
            {busy && <div className="bubble bot"><Typing />{messages.length > 3 && <span className="tiny muted" style={{ marginLeft: 10 }}>thinking…</span>}</div>}
          </div>
          <ErrorNote error={error} />
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
            <input value={text} onChange={(e) => setText(e.target.value)} disabled={!!result}
              placeholder={result ? "Check finished. Start a new check to ask again." : "Type your answer… (English, हिंदी, मराठी)"} />
            <button className="send" disabled={busy || !text.trim() || !!result} aria-label="Send"><SendHorizontal size={18} /></button>
          </form>
        </div>
      </div>

      <div className="stack">
        {!result ? (
          <div className="card arc">
            <h3>How It Works</h3>
            <p>MediAid asks a few questions like a nurse, then gives a severity level, home care from its knowledge base, and the right doctor near you.</p>
            <LevelBadge level="green" /> <LevelBadge level="yellow" /> <LevelBadge level="orange" /> <LevelBadge level="red" />
          </div>
        ) : (
          <Result result={result} go={go} />
        )}
      </div>
    </div>
  );
}

function Result({ result, go }) {
  const rem = result.remedies || {};
  return (
    <>
      {result.level === "red" && <Emergency />}
      <div className="card glow">
        <div className="card-title"><h3>Your Result</h3><LevelBadge level={result.level} /></div>
        <div className="big-number" style={{ fontSize: 24 }}>{cap(result.condition) || "Assessment"}</div>
        <div className="small muted">{result.meaning}</div>
        <div className="row" style={{ marginTop: 10 }}>
          <div className="txt"><small>Who to see</small><b>{result.specialty}</b></div>
          {result.level !== "green" && <button className="btn-glow" onClick={() => go("doctors")}>Find doctors</button>}
        </div>
        {result.advice && <p className="small" style={{ color: "var(--text-2)", lineHeight: 1.6 }}>{result.advice}</p>}
        <div className="actions"><button className="pill-outline" onClick={() => go("checkin")}>🌱 Start daily check-in</button></div>
      </div>

      {rem.matched ? (
        <div className="card">
          <div className="card-title"><h3>Home Care</h3><span className="tiny muted">📚 {rem.source}</span></div>
          <p className="small" style={{ marginTop: 0, color: "var(--text-2)", lineHeight: 1.6 }}>{rem.summary}</p>
          <ul className="clean">{rem.home_care.map((h, i) => <li key={i}>{h}</li>)}</ul>
          {rem.medicines?.length > 0 && (
            <>
              <div className="section-label">Medicines you can take · follow the pack label</div>
              {rem.medicines.map((m) => (
                <div className="row" key={m.id}>
                  <div className="ico">💊</div>
                  <div className="txt"><b>{m.name}</b><small>{m.how_to_take}{m.note ? ` · ${m.note}` : ""}</small></div>
                </div>
              ))}
            </>
          )}
          {rem.excluded_medicines?.map((x) => (
            <div key={x.id} className="tiny muted" style={{ marginTop: 6 }}>✕ {x.name} left out: {x.reason}</div>
          ))}
          {rem.notes?.map((n, i) => <div key={i} className="notice" style={{ marginTop: 10 }}>{n}</div>)}
          <div className="section-label">See a doctor if</div>
          <ul className="clean">{rem.see_doctor_if.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      ) : (
        rem.summary && <div className="notice">{rem.summary}</div>
      )}
    </>
  );
}

function cap(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}
