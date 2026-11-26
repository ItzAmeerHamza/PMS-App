import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDateTime } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

export default function PrescriptionDetail() {
  const { id } = useParams();
  const { t, named } = useI18n();
  const pharmacy = usePharmacy();
  const [rx, setRx] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
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

  async function printPrescription() {
    setError("");
    setNotice("");
    if (!window.pharmacare?.printPrescription) {
      window.print();
      return;
    }
    setBusy(true);
    try {
      const result = await window.pharmacare.printPrescription();
      if (!result?.ok) {
        setError(result?.error || "The printer did not accept this prescription");
        return;
      }
      setNotice(t("rxDetail.sentTo", { name: result.printer }));
    } catch {
      setError("The printer did not accept this prescription");
    } finally {
      setBusy(false);
    }
  }

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
      <div className="page-head screen-only">
        <div>
          <h2>{rx.patient_name}</h2>
          <p>
            {rx.doctor_name || t("patient.noDoctor")} · {formatDateTime(rx.prescribed_at)}
          </p>
        </div>
        <div className="toolbar">
          <span className={`badge ${rx.status}`}>{named("status", rx.status)}</span>
          <button className="btn ghost" type="button" disabled={busy} onClick={printPrescription}>
            {t("rxDetail.print")}
          </button>
          {rx.sale_id && (
            <Link className="btn ghost" to={`/billing/${rx.sale_id}`}>
              {t("rxDetail.openBill")}
            </Link>
          )}
          {rx.status === "recorded" && (
            <>
              <Link className="btn" to={`/billing/new?prescription=${rx.id}`}>
                {t("rxDetail.bill")}
              </Link>
              <button className="btn ghost" disabled={busy} onClick={() => run(api.cancel)}>
                {t("common.cancel")}
              </button>
            </>
          )}
        </div>
      </div>
      {error && <div className="error screen-only">{localizeError(error, t)}</div>}
      {notice && <div className="notice screen-only">{notice}</div>}
      <div className="two-col screen-only">
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
      <article className="print-sheet">
        <header className="print-head">
          <h1>{pharmacy?.name || "PharmaCare"}</h1>
          {pharmacy?.address && <p>{pharmacy.address}</p>}
          <p>
            {[pharmacy?.phone, pharmacy?.license_number ? t("rxDetail.license", { number: pharmacy.license_number }) : ""]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </header>
        <h2>{t("rxDetail.printTitle")}</h2>
        <div className="print-meta">
          <div>
            <strong>{rx.patient_name}</strong>
            <div>{rx.doctor_name || t("patient.noDoctor")}</div>
          </div>
          <div>{formatDateTime(rx.prescribed_at)}</div>
        </div>
        <p>
          <strong>{t("script.complaint")}: </strong>
          {rx.complaint || "—"}
        </p>
        <p>
          <strong>{t("rx.diagnosis")}: </strong>
          {rx.diagnosis || "—"}
        </p>
        {rx.notes && (
          <p>
            <strong>{t("patients.notes")}: </strong>
            {rx.notes}
          </p>
        )}
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
                  <strong>{item.medicine_name}</strong>
                  <div>
                    {[item.medicine_salt, item.medicine_company].filter(Boolean).join(" · ")}
                  </div>
                  {item.instructions && <div>{item.instructions}</div>}
                </td>
                <td>
                  {[item.dosage, item.frequency, item.duration_days ? t("patient.days", { n: item.duration_days }) : ""]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </td>
                <td>{item.quantity}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="print-sign">
          <span>{t("rxDetail.signature")}</span>
        </p>
      </article>
    </div>
  );
}
