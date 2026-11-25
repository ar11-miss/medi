import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Settings({ name, onSave }) {
  const [value, setValue] = useState(name);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.health().then(setHealth).catch((e) => setError(e.message)); }, []);

  return (
    <div className="two-col">
      <form className="card glow" onSubmit={(e) => { e.preventDefault(); onSave(value); }}>
        <div className="card-title"><h3>Your Name</h3></div>
        <input className="text-input" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Your name" />
        <div className="actions"><button className="btn-glow" type="submit">Save</button></div>
      </form>
      <div className="card">
        <div className="card-title"><h3>Connection</h3></div>
        {error && <div className="notice">Can't reach the MediAid server: {error}</div>}
        {health && (
          <>
            <div className="row"><div className="txt"><b>Groq API key</b><small>Needed for the AI</small></div>
              <div className={`val ${health.groq_key ? "green" : "muted"}`}>{health.groq_key ? "Set" : "Missing"}</div></div>
            <div className="row"><div className="txt"><b>Model</b><small>From GROQ_MODEL in .env</small></div>
              <div className="val">{health.model}</div></div>
            <div className="row"><div className="txt"><b>Geoapify</b><small>Free doctor search key</small></div>
              <div className={`val ${health.geoapify ? "green" : "muted"}`}>{health.geoapify ? "Set" : "Missing"}</div></div>
            <div className="row"><div className="txt"><b>Google Places</b><small>Optional, needs billing</small></div>
              <div className={`val ${health.google_places ? "green" : "muted"}`}>{health.google_places ? "Set" : "Not used"}</div></div>
          </>
        )}
      </div>
    </div>
  );
}
