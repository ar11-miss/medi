import { useCallback, useEffect, useState } from "react";
import { Bell, HeartPulse, LayoutDashboard, LifeBuoy, MapPin, Mic, Settings as SettingsIcon, Sprout, Stethoscope } from "lucide-react";
import { api } from "./api.js";
import Dashboard from "./pages/Dashboard.jsx";
import SymptomCheck from "./pages/SymptomCheck.jsx";
import CheckIn from "./pages/CheckIn.jsx";
import Doctors from "./pages/Doctors.jsx";
import Settings from "./pages/Settings.jsx";
import Support from "./pages/Support.jsx";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "symptoms", label: "Check Symptoms", icon: Stethoscope },
  { id: "checkin", label: "Daily Check-in", icon: Sprout },
  { id: "doctors", label: "Find Doctors", icon: MapPin },
];
const TABS = [
  { id: "dashboard", label: "Overview" },
  { id: "checkin", label: "Check-in" },
  { id: "doctors", label: "Doctors" },
];

function usePage() {
  const read = () => window.location.hash.replace("#/", "").split("?")[0] || "dashboard";
  const [page, setPage] = useState(read);
  useEffect(() => {
    const on = () => setPage(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [page, (p) => { window.location.hash = `#/${p}`; }];
}

export default function App() {
  const [page, go] = usePage();
  const [name, setName] = useState(() => localStorage.getItem("mediaid-name") || "");
  const [askName, setAskName] = useState(!localStorage.getItem("mediaid-name"));
  const [data, setData] = useState({ case: null, result: {} });
  const [loaded, setLoaded] = useState(false);
  const [firstMessage, setFirstMessage] = useState("");
  const [search, setSearch] = useState("");
  const [version, setVersion] = useState("");
  useEffect(() => { api.health().then((h) => setVersion(h.version || "old")).catch(() => setVersion("offline")); }, []);

  const refresh = useCallback(async () => {
    try {
      setData(await api.latest());
    } catch {
      /* server not running yet */
    } finally {
      setLoaded(true);
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const saveName = (n) => {
    const v = n.trim() || "Friend";
    localStorage.setItem("mediaid-name", v);
    setName(v);
    setAskName(false);
  };
  const ask = (text) => {
    setFirstMessage(text);
    go("symptoms");
  };

  const c = data.case;
  const props = { data, refresh, go, loaded };
  const subtitle = {
    dashboard: "Here's your health overview",
    symptoms: "Tell MediAid how you feel, in English, Hindi or Marathi",
    checkin: "Grow your Tulsi: check in every day",
    doctors: "Doctors and hospitals near you",
    settings: "Your MediAid settings",
    support: "Emergency numbers and help",
  }[page] || "";

  return (
    <div className="frame">
      <aside className="sidebar">
        <div className="logo"><HeartPulse size={22} strokeWidth={2.4} /> MediAid</div>
        {NAV.map((n) => (
          <button key={n.id} className={`nav-item ${page === n.id ? "active" : ""}`} onClick={() => go(n.id)}>
            <n.icon size={18} strokeWidth={1.7} /> {n.label}
          </button>
        ))}
        <div className="nav-gap" />
        <button className={`nav-item bottom ${page === "settings" ? "active" : ""}`} onClick={() => go("settings")}>
          <SettingsIcon size={18} strokeWidth={1.7} /> Settings
        </button>
        <button className={`nav-item bottom ${page === "support" ? "active" : ""}`} onClick={() => go("support")}>
          <LifeBuoy size={18} strokeWidth={1.7} /> Support
        </button>
        <div className="tiny muted-2 nav-item bottom" style={{ padding: "6px 16px" }}>MediAid v{version || "…"}</div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="welcome">
            <h1>Welcome, <span>{name || "Friend"}</span></h1>
            <p>{subtitle}</p>
          </div>
          <div className="top-right">
            <button className="icon-btn" aria-label="Daily check-in reminder" onClick={() => go("checkin")}>
              <Bell size={17} strokeWidth={1.8} />
            </button>
            <button className="icon-btn" aria-label="Settings" onClick={() => go("settings")}>
              <SettingsIcon size={17} strokeWidth={1.8} />
            </button>
            <div className="avatar">
              <div className="pic">{(name || "F").slice(0, 1).toUpperCase()}</div>
              <div className="who">
                {name || "Friend"}
                <small>{c ? `Recovery day ${c.day}${c.streak ? ` · ${c.streak}-day streak 🔥` : ""}` : "No check-in yet"}</small>
              </div>
            </div>
          </div>
        </div>

        <div className="toolbar">
          <div className="tabs">
            {TABS.map((t) => (
              <button key={t.id} className={`tab ${page === t.id ? "active" : ""}`} onClick={() => go(t.id)}>{t.label}</button>
            ))}
          </div>
          <form className="search" onSubmit={(e) => { e.preventDefault(); if (search.trim()) { ask(search.trim()); setSearch(""); } }}>
            <Mic size={16} strokeWidth={1.7} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Ask MediAid anything" />
          </form>
        </div>

        {page === "dashboard" && <Dashboard {...props} />}
        {page === "symptoms" && <SymptomCheck {...props} firstMessage={firstMessage} clearFirst={() => setFirstMessage("")} />}
        {page === "checkin" && <CheckIn {...props} />}
        {page === "doctors" && <Doctors {...props} />}
        {page === "settings" && <Settings name={name} onSave={saveName} />}
        {page === "support" && <Support />}
      </main>

      {askName && (
        <div className="overlay">
          <form className="card glow" onSubmit={(e) => { e.preventDefault(); saveName(e.target.elements.n.value); }}>
            <div className="card-title"><h3>Welcome to MediAid</h3></div>
            <p className="small muted" style={{ marginTop: 0 }}>What should we call you?</p>
            <input name="n" className="text-input" placeholder="Your name" autoFocus />
            <div className="actions"><button className="btn-glow" type="submit">Continue</button></div>
          </form>
        </div>
      )}
    </div>
  );
}
