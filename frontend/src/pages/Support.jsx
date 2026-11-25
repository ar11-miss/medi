export default function Support() {
  return (
    <div className="two-col">
      <div className="card arc">
        <h3>Emergency</h3>
        <p>Chest pain, trouble breathing, fainting, heavy bleeding or signs of a stroke? Don't wait.</p>
        <div className="actions" style={{ justifyContent: "center" }}>
          <a className="btn-glow" href="tel:108">Call 108 (ambulance)</a>
          <a className="pill-outline" href="tel:112">Call 112</a>
        </div>
      </div>
      <div className="card">
        <div className="card-title"><h3>Helplines</h3></div>
        <div className="row"><div className="ico">🚑</div><div className="txt"><b>108</b><small>Ambulance</small></div></div>
        <div className="row"><div className="ico">🆘</div><div className="txt"><b>112</b><small>All emergencies</small></div></div>
        <div className="row"><div className="ico">💬</div><div className="txt"><b>14416</b><small>Tele-MANAS mental health helpline, free, 24×7</small></div></div>
        <p className="tiny muted" style={{ marginTop: 14, lineHeight: 1.6 }}>
          MediAid is a student project for guidance only. It is not a doctor and does not replace medical advice.
        </p>
      </div>
    </div>
  );
}
