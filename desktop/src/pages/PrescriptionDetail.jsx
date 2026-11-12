import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDateTime } from "../lib/format";

export default function PrescriptionDetail() {
  const { id } = useParams();
  const { t, named } = useI18n();
  const [rx, setRx] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setRx(await api.prescription(id));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function run(action) {
    setBusy(true);
    try {
      setRx(await action(id));
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!rx) return <div className="loading">{error ? localizeError(error, t) : t("rxDetail.loading")}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{rx.patient_name}</h2>
          <p>
            {rx.doctor_name || t("patient.noDoctor")} · {formatDateTime(rx.prescribed_at)}
          </p>
        </div>
        <div className="toolbar">
          <span className={`badge ${rx.status}`}>{named("status", rx.status)}</span>
          {rx.status === "recorded" && (
            <>
              <button className="btn" disabled={busy} onClick={() => run(api.dispense)}>
                {t("rxDetail.dispense")}
              </button>
              <button className="btn ghost" disabled={busy} onClick={() => run(api.cancel)}>
                {t("common.cancel")}
              </button>
            </>
          )}
        </div>
      </div>
      {error && <div className="error">{localizeError(error, t)}</div>}
      <div className="two-col">
        <section className="panel">
          <h3>{t("rxDetail.visit")}</h3>
          <p>
            <strong>{t("script.complaint")}</strong>
            <br />
            {rx.complaint || "—"}
          </p>
          <p>
            <strong>{t("rx.diagnosis")}</strong>
            <br />
            {rx.diagnosis || "—"}
          </p>
          <p>
            <strong>{t("patients.notes")}</strong>
            <br />
            {rx.notes || "—"}
          </p>
          <p>
            <Link to={`/patients/${rx.patient_id}`}>{t("patient.openHistory")}</Link>
          </p>
        </section>
        <section className="panel">
          <h3>{t("rxDetail.medicines")}</h3>
          <table>
            <thead>
              <tr>
                <th>{t("dash.medicine")}</th>
                <th>{t("rxDetail.dose")}</th>
                <th>{t("dash.qty")}</th>
              </tr>
            </thead>
            <tbody>
              {rx.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.medicine_name}
                    <div className="muted">
                      {[item.medicine_salt, item.medicine_company].filter(Boolean).join(" · ")}
                    </div>
                    {item.instructions && <div className="muted">{item.instructions}</div>}
                  </td>
                  <td>
                    {item.dosage || "—"}
                    <div className="muted">{item.frequency}</div>
                  </td>
                  <td>{item.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
