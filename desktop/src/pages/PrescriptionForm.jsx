import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import Dropdown from "../components/Dropdown";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDateTime, fullName } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

const emptyItem = {
  medicine_id: "",
  medicine_query: "",
  suggest_open: false,
  active_index: 0,
  dosage: "",
  frequency: "1-0-1",
  duration_days: "",
  quantity: "",
  instructions: "",
  expanded: true,
};

const emptyPatient = { first_name: "", last_name: "", phone: "", allergies: "" };

function matchScore(medicine, query) {
  const fields = [medicine.name, medicine.salt, medicine.generic_name, medicine.manufacturer, medicine.sku, medicine.strength, medicine.form].map(
    (value) => (value || "").toLowerCase(),
  );
  const starts = fields.findIndex((value) => value.startsWith(query));
  if (starts >= 0) return starts;
  const contains = fields.findIndex((value) => value.includes(query));
  if (contains >= 0) return 10 + contains;
  return 99;
}

function suggestionsFor(medicines, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return medicines
    .map((medicine) => ({ medicine, score: matchScore(medicine, needle) }))
    .filter((row) => row.score < 99)
    .sort((a, b) => a.score - b.score || a.medicine.name.localeCompare(b.medicine.name))
    .slice(0, 8)
    .map((row) => row.medicine);
}

function Highlight({ text, query }) {
  const value = text || "";
  const needle = query.trim();
  const index = needle ? value.toLowerCase().indexOf(needle.toLowerCase()) : -1;
  if (index < 0) return value;
  return (
    <>
      {value.slice(0, index)}
      <mark>{value.slice(index, index + needle.length)}</mark>
      {value.slice(index + needle.length)}
    </>
  );
}

function MedicineSuggest({ item, medicines, onChoose, onPatch }) {
  const { t, named } = useI18n();
  const fieldRef = useRef(null);
  const query = item.medicine_query;
  const choices = suggestionsFor(medicines, query);
  const selected = medicines.find((medicine) => String(medicine.id) === String(item.medicine_id));
  const activeIndex = Math.min(item.active_index || 0, Math.max(choices.length - 1, 0));

  useEffect(() => {
    if (item.suggest_open && !item.medicine_id) fieldRef.current?.focus();
  }, [item.suggest_open, item.medicine_id]);

  function onKeyDown(event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const next = Math.max(0, Math.min(activeIndex + delta, choices.length - 1));
      onPatch({ suggest_open: true, active_index: choices.length ? next : 0 });
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      onPatch({ suggest_open: false });
      return;
    }
    if (event.key === "Enter" && item.suggest_open && choices[activeIndex]) {
      event.preventDefault();
      onChoose(choices[activeIndex]);
    }
  }

  if (selected && !item.suggest_open) {
    return (
      <div className="chosen-med">
        <div>
          <strong>{selected.name}</strong>
          <div className="muted">
            {[selected.salt, selected.manufacturer, selected.strength, selected.form ? named("form", selected.form) : ""].filter(Boolean).join(" · ")}
          </div>
          <div className="muted">
            {t("suggest.inStock", { n: selected.quantity_on_hand })}
            {selected.rack_location ? ` · ${t("inv.rack", { location: selected.rack_location })}` : ""}
            {selected.is_low_stock ? ` · ${t("dash.lowStock")}` : ""}
          </div>
        </div>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onPatch({ medicine_id: "", medicine_query: "", suggest_open: true, active_index: 0 })}
        >
          {t("suggest.change")}
        </button>
      </div>
    );
  }

  return (
    <div className="suggest">
      <input
        ref={fieldRef}
        className="input"
        placeholder={t("suggest.placeholder")}
        value={query}
        autoComplete="off"
        onFocus={() => onPatch({ suggest_open: true })}
        onBlur={() => {
          window.setTimeout(() => onPatch({ suggest_open: false }), 150);
        }}
        onChange={(event) =>
          onPatch({
            medicine_query: event.target.value,
            medicine_id: "",
            suggest_open: true,
            active_index: 0,
          })
        }
        onKeyDown={onKeyDown}
      />
      {item.suggest_open && query.trim() && (
        <ul className="suggest-list">
          {choices.length === 0 && <li className="suggest-empty">{t("suggest.noMatch", { query: query.trim() })}</li>}
          {choices.map((medicine, choiceIndex) => (
            <li key={medicine.id}>
              <button
                type="button"
                className={`suggest-item ${choiceIndex === activeIndex ? "active" : ""}`}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => onPatch({ active_index: choiceIndex })}
                onClick={() => onChoose(medicine)}
              >
                <span>
                  <span className="suggest-name">
                    <Highlight text={medicine.name} query={query} />
                  </span>
                  <span className="suggest-meta">
                    <Highlight text={medicine.salt || t("inv.saltNotSet")} query={query} />
                    {medicine.strength || medicine.form
                      ? ` · ${[medicine.strength, medicine.form ? named("form", medicine.form) : ""].filter(Boolean).join(" ")}`
                      : ""}
                    {" · "}
                    <Highlight text={medicine.manufacturer || t("suggest.companyNotSet")} query={query} />
                  </span>
                </span>
                <span className="suggest-stock">{t("suggest.inStock", { n: medicine.quantity_on_hand })}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function lineText(item, t) {
  return [
    item.dosage,
    item.frequency,
    item.duration_days ? t("patient.days", { n: item.duration_days }) : "",
    item.quantity ? t("patient.qty", { n: item.quantity }) : "",
    item.instructions,
  ]
    .filter(Boolean)
    .join(" · ");
}

export default function PrescriptionForm() {
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [patients, setPatients] = useState([]);
  const [medicines, setMedicines] = useState([]);
  const [patientQuery, setPatientQuery] = useState("");
  const [newPatient, setNewPatient] = useState(false);
  const [patientForm, setPatientForm] = useState(emptyPatient);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    patient_id: params.get("patientId") || "",
    doctor_name: "",
    complaint: "",
    diagnosis: "",
    notes: "",
    items: [{ ...emptyItem }],
  });

  useEffect(() => {
    if (!pharmacy) return;
    Promise.all([api.patients(pharmacy.id), api.medicines(pharmacy.id)])
      .then(([people, stock]) => {
        setPatients(people);
        setMedicines(stock.filter((medicine) => medicine.is_active));
      })
      .catch((err) => setError(err.message));
  }, [pharmacy]);

  useEffect(() => {
    if (!pharmacy || newPatient || !form.patient_id) {
      setSelectedPatient(null);
      setHistory([]);
      return;
    }
    Promise.all([api.patient(form.patient_id), api.prescriptions(pharmacy.id, { patientId: form.patient_id })])
      .then(([person, visits]) => {
        setSelectedPatient(person);
        setHistory(visits);
      })
      .catch((err) => setError(err.message));
  }, [pharmacy, form.patient_id, newPatient]);

  function updateItem(index, patch) {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    }));
  }

  function chooseMedicine(index, medicine) {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, i) =>
        i === index
          ? {
              ...item,
              medicine_id: String(medicine.id),
              medicine_query: "",
              suggest_open: false,
              active_index: 0,
              dosage: item.dosage || medicine.strength || "",
            }
          : item,
      ),
    }));
  }

  function reuseVisit(visit) {
    const items = visit.items
      .filter((item) => medicines.some((medicine) => medicine.id === item.medicine_id))
      .map((item) => ({
        medicine_id: String(item.medicine_id),
        medicine_query: "",
        suggest_open: false,
        active_index: 0,
        dosage: item.dosage || "",
        frequency: item.frequency || "1-0-1",
        duration_days: item.duration_days || "",
        quantity: item.quantity || "",
        instructions: item.instructions || "",
        expanded: false,
      }));
    if (!items.length) {
      setError("Those medicines are no longer active in the store.");
      return;
    }
    setError("");
    setForm((current) => ({ ...current, items }));
  }

  async function save(event) {
    event.preventDefault();
    const lines = form.items.filter((item) => item.medicine_id && item.quantity);
    if (!lines.length) {
      setError("Add at least one medicine from the store.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      let patientId = Number(form.patient_id);
      if (newPatient) {
        const createdPatient = await api.createPatient({
          pharmacy_id: pharmacy.id,
          first_name: patientForm.first_name,
          last_name: patientForm.last_name,
          phone: patientForm.phone,
          allergies: patientForm.allergies || null,
        });
        patientId = createdPatient.id;
      }
      const created = await api.createPrescription({
        pharmacy_id: pharmacy.id,
        patient_id: patientId,
        doctor_name: form.doctor_name,
        complaint: form.complaint,
        diagnosis: form.diagnosis,
        notes: form.notes,
        items: lines.map((item) => ({
          medicine_id: Number(item.medicine_id),
          dosage: item.dosage,
          frequency: item.frequency,
          duration_days: item.duration_days ? Number(item.duration_days) : null,
          quantity: Number(item.quantity),
          instructions: item.instructions,
        })),
      });
      navigate(`/patients/${patientId}?visit=${created.id}`);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  if (!pharmacy) return <div className="loading">{t("script.loading")}</div>;

  const visiblePatients = patients.filter((patient) => {
    const haystack = `${fullName(patient)} ${patient.phone}`.toLowerCase();
    return haystack.includes(patientQuery.trim().toLowerCase());
  });

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("dash.newPrescription")}</h2>
          <p>{t("script.lead")}</p>
        </div>
      </div>
      {error && <div className="error">{localizeError(error, t)}</div>}
      <div className="visit-layout">
        <form className="panel" onSubmit={save} style={{ paddingBottom: 22 }}>
          <div className="form-grid">
            <div className="full">
              <span className="field-label">{t("script.patient")}</span>
              {!newPatient ? (
                <>
                  <input
                    className="input"
                    placeholder={t("patients.search")}
                    value={patientQuery}
                    onChange={(e) => setPatientQuery(e.target.value)}
                  />
                  <Dropdown
                    required
                    className="dropdown-spaced"
                    value={form.patient_id}
                    onChange={(value) => setForm((current) => ({ ...current, patient_id: value }))}
                    options={[
                      { value: "", label: t("script.selectPatient") },
                      ...visiblePatients.map((patient) => ({
                        value: String(patient.id),
                        label: `${fullName(patient)} · ${patient.phone}${patient.allergies ? ` · ${t("script.allergyMark")}` : ""}`,
                      })),
                    ]}
                  />
                </>
              ) : (
                <div className="form-grid">
                  <label>
                    <span>{t("patients.firstName")}</span>
                    <input
                      className="input"
                      required
                      value={patientForm.first_name}
                      onChange={(e) => setPatientForm({ ...patientForm, first_name: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>{t("patients.lastName")}</span>
                    <input
                      className="input"
                      required
                      value={patientForm.last_name}
                      onChange={(e) => setPatientForm({ ...patientForm, last_name: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>{t("patients.phone")}</span>
                    <input
                      className="input"
                      required
                      value={patientForm.phone}
                      onChange={(e) => setPatientForm({ ...patientForm, phone: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>{t("patients.allergies")}</span>
                    <input
                      className="input"
                      value={patientForm.allergies}
                      onChange={(e) => setPatientForm({ ...patientForm, allergies: e.target.value })}
                    />
                  </label>
                </div>
              )}
              <button
                type="button"
                className="btn ghost"
                style={{ marginTop: 8 }}
                onClick={() => {
                  setNewPatient((value) => !value);
                  setError("");
                }}
              >
                {newPatient ? t("script.existing") : t("script.newPatient")}
              </button>
            </div>
            {selectedPatient?.allergies && (
              <div className="allergy-banner full">{t("patient.allergies", { value: selectedPatient.allergies })}</div>
            )}
            <label>
              <span>{t("dash.doctor")}</span>
              <input
                className="input"
                value={form.doctor_name}
                onChange={(e) => setForm((current) => ({ ...current, doctor_name: e.target.value }))}
              />
            </label>
            <label>
              <span>{t("script.complaint")}</span>
              <input
                className="input"
                value={form.complaint}
                placeholder={t("script.complaintPlaceholder")}
                onChange={(e) => setForm((current) => ({ ...current, complaint: e.target.value }))}
              />
            </label>
            <label className="full">
              <span>{t("rx.diagnosis")}</span>
              <input
                className="input"
                value={form.diagnosis}
                onChange={(e) => setForm((current) => ({ ...current, diagnosis: e.target.value }))}
              />
            </label>
            <label className="full">
              <span>{t("script.notes")}</span>
              <textarea
                rows="2"
                value={form.notes}
                onChange={(e) => setForm((current) => ({ ...current, notes: e.target.value }))}
              />
            </label>
          </div>

          <h3>{t("script.medicines")}</h3>
          {form.items.map((item, index) => {
            const started = Boolean(item.medicine_id || item.quantity);
            const selected = medicines.find((medicine) => String(medicine.id) === String(item.medicine_id));
            const expanded = item.expanded !== false;
            const summary = lineText(item, t);
            return (
              <div className="line-card" key={index}>
                {(selected || form.items.length > 1) && (
                <div className="line-head">
                  <div>
                    {!expanded && selected && (
                      <>
                        <strong>{selected.name}</strong>
                        <div className="muted line-summary">{summary || t("script.noDetails")}</div>
                      </>
                    )}
                  </div>
                  <div className="line-actions">
                    {selected && (
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => updateItem(index, { expanded: !expanded, suggest_open: false })}
                      >
                        {expanded ? t("script.hideDetails") : t("script.showDetails")}
                      </button>
                    )}
                    {form.items.length > 1 && (
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() =>
                          setForm((current) => ({ ...current, items: current.items.filter((_, i) => i !== index) }))
                        }
                      >
                        {t("script.remove")}
                      </button>
                    )}
                  </div>
                </div>
                )}
                {expanded && (
                  <div className="form-grid">
                    <div className="full">
                      <span className="field-label">{t("script.medicine")}</span>
                      <MedicineSuggest
                        item={item}
                        medicines={medicines}
                        onChoose={(medicine) => chooseMedicine(index, medicine)}
                        onPatch={(patch) => updateItem(index, patch)}
                      />
                    </div>
                    <label>
                      <span>{t("script.dosage")}</span>
                      <input className="input" value={item.dosage} onChange={(e) => updateItem(index, { dosage: e.target.value })} />
                    </label>
                    <label>
                      <span>{t("script.frequency")}</span>
                      <input className="input" value={item.frequency} onChange={(e) => updateItem(index, { frequency: e.target.value })} />
                    </label>
                    <label>
                      <span>{t("script.days")}</span>
                      <input
                        className="input"
                        type="number"
                        min="1"
                        value={item.duration_days}
                        onChange={(e) => updateItem(index, { duration_days: e.target.value })}
                      />
                    </label>
                    <label>
                      <span>{t("inv.quantity")}</span>
                      <input
                        className="input"
                        type="number"
                        min="1"
                        required={form.items.length === 1 || started}
                        value={item.quantity}
                        onChange={(e) => updateItem(index, { quantity: e.target.value })}
                      />
                    </label>
                    <label className="full">
                      <span>{t("script.instructions")}</span>
                      <input
                        className="input"
                        value={item.instructions}
                        onChange={(e) => updateItem(index, { instructions: e.target.value })}
                      />
                    </label>
                  </div>
                )}
              </div>
            );
          })}

          <div className="toolbar" style={{ margin: "12px 0 0" }}>
            <button
              type="button"
              className="btn ghost"
              onClick={() =>
                setForm((current) => ({
                  ...current,
                  items: [
                    ...current.items.map((item) =>
                      item.medicine_id && item.quantity ? { ...item, expanded: false, suggest_open: false } : item,
                    ),
                    { ...emptyItem },
                  ],
                }))
              }
            >
              {t("script.addMedicine")}
            </button>
            <button className="btn" disabled={saving}>
              {saving ? t("script.saving") : t("script.save")}
            </button>
          </div>
        </form>

        <aside className="panel">
          <h3>{t("script.history")}</h3>
          {!form.patient_id || newPatient ? (
            <p className="empty">{t("script.historyEmpty")}</p>
          ) : (
            <>
              <p className="muted">
                {t(history.length === 1 ? "script.previousOne" : "script.previousMany", { n: history.length })}
                {selectedPatient ? ` · ${fullName(selectedPatient)}` : ""}
              </p>
              {history.length === 0 && <p className="empty">{t("script.noEarlier")}</p>}
              {history.map((visit) => (
                <div className="history-item" key={visit.id}>
                  <div className="history-head">
                    <Link to={`/prescriptions/${visit.id}`}>
                      <strong>{visit.complaint || visit.diagnosis || t("patient.visit")}</strong>
                    </Link>
                    <span className={`badge ${visit.status}`}>{named("status", visit.status)}</span>
                  </div>
                  <div className="muted">
                    {formatDateTime(visit.prescribed_at)}
                    {visit.diagnosis ? ` · ${visit.diagnosis}` : ""}
                  </div>
                  <ul className="history-meds">
                    {visit.items.map((item) => (
                      <li key={item.id}>
                        {item.medicine_name}
                        {item.medicine_salt ? ` · ${item.medicine_salt}` : ""}
                        <div className="muted">{lineText(item, t)}</div>
                      </li>
                    ))}
                  </ul>
                  {visit.status !== "cancelled" && (
                    <button type="button" className="btn ghost" style={{ marginTop: 8 }} onClick={() => reuseVisit(visit)}>
                      {t("script.again")}
                    </button>
                  )}
                </div>
              ))}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
