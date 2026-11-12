import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDate } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

export default function Dashboard() {
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!pharmacy) return;
    api
      .dashboard(pharmacy.id)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [pharmacy]);

  if (!pharmacy || !data) return <div className="loading">{error ? localizeError(error, t) : t("dash.loading")}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("nav.dashboard")}</h2>
          <p>{t("dash.lead", { name: pharmacy.name })}</p>
        </div>
        <Link className="btn" to="/prescriptions/new">
          {t("dash.newPrescription")}
        </Link>
      </div>

      <div className="card-grid">
        <div className="stat-card">
          <span>{t("dash.medicines")}</span>
          <strong>{data.medicine_count}</strong>
        </div>
        <div className="stat-card">
          <span>{t("dash.units")}</span>
          <strong>{data.units_on_hand}</strong>
        </div>
        <div className="stat-card">
          <span>{t("dash.lowStock")}</span>
          <strong>{data.low_stock_count}</strong>
        </div>
        <div className="stat-card">
          <span>{t("dash.patients")}</span>
          <strong>{data.patient_count}</strong>
        </div>
      </div>

      <div className="two-col">
        <section className="panel">
          <h3>{t("dash.lowStock")}</h3>
          {data.low_stock.length === 0 ? (
            <p className="empty">{t("dash.noLow")}</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t("dash.medicine")}</th>
                  <th>{t("dash.qty")}</th>
                  <th>{t("dash.reorder")}</th>
                </tr>
              </thead>
              <tbody>
                {data.low_stock.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>{item.quantity_on_hand}</td>
                    <td>{item.reorder_level}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <h3>{t("dash.expiring")}</h3>
          {data.expiring.length === 0 ? (
            <p className="empty">{t("dash.noExpiry")}</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t("dash.medicine")}</th>
                  <th>{t("dash.batch")}</th>
                  <th>{t("dash.expiry")}</th>
                </tr>
              </thead>
              <tbody>
                {data.expiring.map((item) => (
                  <tr key={item.id}>
                    <td>{item.medicine_name}</td>
                    <td>{item.batch_number}</td>
                    <td>{formatDate(item.expiry_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <section className="panel" style={{ marginTop: 14 }}>
        <h3>{t("dash.recent")}</h3>
        <table>
          <thead>
            <tr>
              <th>{t("dash.patient")}</th>
              <th>{t("dash.doctor")}</th>
              <th>{t("dash.status")}</th>
              <th>{t("dash.date")}</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_prescriptions.map((rx) => (
              <tr key={rx.id}>
                <td>
                  <Link to={`/prescriptions/${rx.id}`}>{rx.patient_name}</Link>
                </td>
                <td>{rx.doctor_name || "—"}</td>
                <td>
                  <span className={`badge ${rx.status}`}>{named("status", rx.status)}</span>
                </td>
                <td>{formatDate(rx.prescribed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
