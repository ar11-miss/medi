import { useEffect, useState } from "react";
import { LocateFixed, MapPin, Navigation, Phone, Star } from "lucide-react";
import { api, getLocation } from "../api.js";
import { Emergency, ErrorNote, LevelBadge, Typing } from "../components/ui.jsx";

const SPECIALTIES = ["General Physician", "Dermatologist", "ENT Specialist", "Gastroenterologist", "Pulmonologist",
  "Cardiologist", "Neurologist", "Orthopedic", "Ophthalmologist", "Dentist", "Gynecologist", "Pediatrician",
  "Urologist", "Psychiatrist", "Endocrinologist", "Emergency Department"];
const RADII = [2000, 5000, 10000];

export default function Doctors({ data }) {
  const c = data.case;
  const [specialty, setSpecialty] = useState(c?.specialty || "General Physician");
  const [radius, setRadius] = useState(5000);
  const [loc, setLoc] = useState(null);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const level = c?.level || "yellow";

  useEffect(() => { if (c?.specialty) setSpecialty(c.specialty); }, [c?.specialty]);

  const search = async (where = loc) => {
    setBusy(true);
    setError("");
    try {
      const l = where || (await getLocation());
      setLoc(l);
      setRes(await api.doctors({ lat: l.lat, lng: l.lng, level, specialty, radius }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {level === "red" && <Emergency />}
      <div className="card glow">
        <div className="card-title">
          <h3>Find Doctors Near You</h3>
          {c && <LevelBadge level={level} />}
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <select value={specialty} onChange={(e) => setSpecialty(e.target.value)} className="pill-outline"
            style={{ background: "var(--raised)", padding: "9px 16px" }}>
            {SPECIALTIES.map((s) => <option key={s}>{s}</option>)}
          </select>
          {RADII.map((r) => (
            <button key={r} className={`range ${radius === r ? "active" : ""}`} onClick={() => setRadius(r)}>{r / 1000} km</button>
          ))}
          <button className="btn-glow" onClick={() => search()} disabled={busy}>
            {busy ? <Typing /> : <><LocateFixed size={15} /> Search near me</>}
          </button>
        </div>
        <div className="tiny muted" style={{ marginTop: 10 }}>
          <MapPin size={11} /> {loc ? `${loc.label} (${loc.lat.toFixed(3)}, ${loc.lng.toFixed(3)})` : "Your browser will ask for your location. If you say no, MediAid searches near Alandi, Pune."}
        </div>
      </div>

      {busy && <div className="notice">Searching nearby clinics… if the map servers are busy this can take up to a minute.</div>}
      <ErrorNote error={error} />
      {res?.note && <div className="notice">{res.note}</div>}

      {!res && !busy && (
        <div className="card arc">
          <h3>Doctors For Your Result</h3>
          <p>Pick a specialty and distance, then press Search near me. You'll get clinics with phone numbers and directions, nearest first.</p>
        </div>
      )}
      {res && (
        res.clinics.length === 0 ? null : (
          <div className="clinic-grid">
            {res.clinics.map((d, i) => (
              <div key={i} className="mini" style={{ gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <div className="head" style={{ fontSize: 14 }}>{d.name}</div>
                  <span className="tiny green" style={{ whiteSpace: "nowrap" }}>{d.distance_km} km</span>
                </div>
                <div className="tiny muted">{d.specialty}{d.rating ? <> · <Star size={10} /> {d.rating}</> : null}
                  {d.open_now === true && <span className="green"> · Open now</span>}</div>
                {d.address && <div className="tiny" style={{ color: "var(--text-2)" }}>{d.address}</div>}
                <div className="tiny" style={{ color: "var(--text-2)" }}><Phone size={10} /> {d.phone || "No phone listed"}</div>
                <div className="actions" style={{ marginTop: "auto", paddingTop: 8 }}>
                  {d.phone && <a className="pill-outline" href={d.call_link}><Phone size={13} /> Call</a>}
                  <a className="btn-glow" style={{ padding: "7px 16px" }} href={d.maps_link} target="_blank" rel="noreferrer">
                    <Navigation size={13} /> Directions
                  </a>
                </div>
              </div>
            ))}
          </div>
        )
      )}
      {res && res.clinics.length > 0 && (
        <span className="tiny muted">
          {res.source === "google" ? "Source: Google Places"
            : res.source === "geoapify" ? <>Powered by <a href="https://www.geoapify.com/" target="_blank" rel="noreferrer" className="pink">Geoapify</a> · © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="pink">OpenStreetMap</a> contributors</>
            : <>© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="pink">OpenStreetMap</a> contributors</>}
        </span>
      )}
      {res && (
        <div className="card">
          <div className="card-title">
            <h3>Map: {res.specialty} near you</h3>
            <a className="pill-outline" href={res.maps_search_link} target="_blank" rel="noreferrer"><MapPin size={13} /> Open in Google Maps</a>
          </div>
          <iframe title="Doctors near you on Google Maps" src={res.maps_embed} loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
            style={{ width: "100%", height: 380, border: 0, borderRadius: 14, filter: "grayscale(0.15) contrast(0.95)" }} />
          <div className="tiny muted" style={{ marginTop: 8 }}>Tap a place on the map to see its phone number and directions.</div>
        </div>
      )}
    </div>
  );
}
