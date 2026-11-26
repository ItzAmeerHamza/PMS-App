import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import Modal from "../components/Modal";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDate, formatDateTime, fullName } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

export default function PatientDetail() {
  const { id } = useParams();
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const [patient, setPatient] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);
  const navigate = useNavigate();

  async function removePatient() {
    setRemoving(true);
    try {
      await api.removePatient(patient.id);
      navigate("/patients");
    } catch (err) {
      setError(err.message);
      setRemoving(false);
      setConfirmRemove(false);
    }
  }

  useEffect(() => {
    Promise.all([api.patient(id), pharmacy ? api.prescriptions(pharmacy.id, { patientId: id, order: "asc" }) : Promise.resolve([])])
      .then(([person, visits]) => {
        setPatient(person);
        setHistory(visits);
      })
      .catch((err) => setError(err.message));
  }, [id, pharmacy]);

  if (error) return <div className="error">{localizeError(error, t)}</div>;
  if (!patient) return <div className="loading">{t("patient.loading")}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>
            {fullName(patient)}
            <span className={`badge tag ${patient.is_repeat_visitor ? "ok" : "inactive"}`}>
              {patient.is_repeat_visitor ? t("patients.returning") : t("patients.new")}
            </span>
          </h2>
          <p>
            {patient.phone} · {named("gender", patient.gender)} · {t("patient.dobLine", { date: formatDate(patient.date_of_birth) })}
          </p>
          <p className="muted">
            {patient.is_repeat_visitor
              ? t("patient.visitSummary", { n: patient.prescription_count, date: formatDate(patient.last_visit) })
              : t("patient.firstVisit")}
          </p>
        </div>
        {!patient.deleted && (
          <div className="toolbar">
            <button className="btn ghost" type="button" onClick={() => setConfirmRemove(true)}>
              {t("patient.remove")}
            </button>
            <Link className="btn" to={`/prescriptions/new?patientId=${patient.id}`}>
              {t("dash.newPrescription")}
            </Link>
          </div>
        )}
      </div>
      {patient.deleted && (
        <div className="error">{t("patient.removedOn", { date: formatDateTime(patient.deleted_at) })}</div>
      )}

      {patient.allergies && <div className="allergy-banner">{t("patient.allergies", { value: patient.allergies })}</div>}
      <section className="panel">
        <h3>{t("patient.profile")}</h3>
        <p>
          <strong>{t("patients.address")}</strong>
          <br />
          {patient.address || "—"}
        </p>
        <p>
          <strong>{t("patients.notes")}</strong>
          <br />
          {patient.notes || "—"}
        </p>
      </section>
      <section className="panel" style={{ marginTop: 14 }}>
          <h3>{t("patient.history")}</h3>
          {history.length > 1 && <p className="muted">{t("patient.historyOrder")}</p>}
          {history.length === 0 && <p className="empty">{t("patient.emptyHistory")}</p>}
          {history.map((rx) => (
            <div className="history-item" key={rx.id} id={`visit-${rx.id}`}>
              <div className="history-head">
                <Link to={`/prescriptions/${rx.id}`}>
                  <strong>{rx.complaint || rx.diagnosis || t("patient.visit")}</strong>
                </Link>
                <span className={`badge ${rx.status}`}>{named("status", rx.status)}</span>
              </div>
              <div className="muted">
                {formatDateTime(rx.prescribed_at)} · {rx.doctor_name || t("patient.noDoctor")}
                {rx.diagnosis ? ` · ${rx.diagnosis}` : ""}
              </div>
              {rx.notes && <p>{rx.notes}</p>}
              <ul className="history-meds">
                {rx.items.map((item) => (
                  <li key={item.id}>
                    <strong>{item.medicine_name}</strong>
                    {item.medicine_salt ? ` · ${item.medicine_salt}` : ""}
                    {item.medicine_company ? ` · ${item.medicine_company}` : ""}
                    <div className="muted">
                      {[
                        item.dosage,
                        item.frequency,
                        item.duration_days ? t("patient.days", { n: item.duration_days }) : "",
                        t("patient.qty", { n: item.quantity }),
                        item.instructions,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
      </section>
      {confirmRemove && (
        <Modal title={t("patient.removeTitle")} onClose={() => setConfirmRemove(false)}>
          <p>{t("patient.removeBody", { name: fullName(patient) })}</p>
          <div className="modal-actions">
            <button type="button" className="btn ghost" onClick={() => setConfirmRemove(false)}>
              {t("common.cancel")}
            </button>
            <button type="button" className="btn danger" disabled={removing} onClick={removePatient}>
              {t("patient.remove")}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
