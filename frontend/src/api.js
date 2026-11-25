// Small wrapper around the MediAid Python API.
async function call(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : `Server error (${res.status})`);
  }
  return data;
}

export const api = {
  health: () => call("/health"),
  startSymptoms: () => call("/symptoms/start", { method: "POST" }),
  sendSymptom: (sid, text) => call(`/symptoms/${sid}/message`, { method: "POST", body: { text } }),
  latest: () => call("/cases/latest"),
  journey: (id) => call(`/cases/${id}/journey`),
  checkin: (id, body) => call(`/cases/${id}/checkin`, { method: "POST", body }),
  doctors: ({ lat, lng, level, specialty, radius }) =>
    call(`/doctors?${new URLSearchParams({ lat, lng, level, specialty, radius })}`),
};

// Browser location, with Alandi (Pune) as the fallback.
export const DEFAULT_LOCATION = { lat: 18.677, lng: 73.897, label: "Alandi, Pune (default)" };
export function getLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(DEFAULT_LOCATION);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, label: "Your location" }),
      () => resolve(DEFAULT_LOCATION),
      { timeout: 8000 },
    );
  });
}
