import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import Dropdown from "../components/Dropdown";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDate } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

export default function Prescriptions() {
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!pharmacy) return;
    api
      .prescriptions(pharmacy.id, { status: status || undefined })
      .then(setRows)
      .catch((err) => setError(err.message));
  }, [pharmacy, status]);

  if (!pharmacy) return <div className="loading">{t("rx.loading")}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("nav.prescriptions")}</h2>
          <p>{t("rx.lead")}</p>
        </div>
        <div className="toolbar">
          <Dropdown
            ariaLabel={t("dash.status")}
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: t("rx.allStatuses") },
              { value: "recorded", label: t("status.recorded") },
              { value: "dispensed", label: t("status.dispensed") },
              { value: "cancelled", label: t("status.cancelled") },
            ]}
          />
          <Link className="btn" to="/prescriptions/new">
            {t("dash.newPrescription")}
          </Link>
        </div>
      </div>
      {error && <div className="error">{localizeError(error, t)}</div>}
      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>{t("dash.patient")}</th>
              <th>{t("dash.doctor")}</th>
              <th>{t("rx.diagnosis")}</th>
              <th>{t("rx.items")}</th>
              <th>{t("dash.status")}</th>
              <th>{t("dash.date")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="clickable" onClick={() => navigate(`/prescriptions/${row.id}`)}>
                <td>{row.patient_name}</td>
                <td>{row.doctor_name || "—"}</td>
                <td>{row.diagnosis || "—"}</td>
                <td>{row.items.length}</td>
                <td>
                  <span className={`badge ${row.status}`}>{named("status", row.status)}</span>
                </td>
                <td>{formatDate(row.prescribed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="empty">{t("rx.empty")}</p>}
      </section>
    </div>
  );
}
