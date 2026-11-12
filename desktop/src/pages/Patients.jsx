import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import Dropdown from "../components/Dropdown";
import Modal from "../components/Modal";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDate, fullName } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

const emptyPatient = {
  first_name: "",
  last_name: "",
  phone: "",
  date_of_birth: "",
  gender: "",
  address: "",
  allergies: "",
  notes: "",
};

export default function Patients() {
  const pharmacy = usePharmacy();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyPatient);

  async function load() {
    if (!pharmacy) return;
    try {
      setRows(await api.patients(pharmacy.id, search));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [pharmacy, search]);

  async function save(event) {
    event.preventDefault();
    try {
      const created = await api.createPatient({
        ...form,
        pharmacy_id: pharmacy.id,
        date_of_birth: form.date_of_birth || null,
      });
      setOpen(false);
      navigate(`/patients/${created.id}`);
    } catch (err) {
      setError(err.message);
    }
  }

  if (!pharmacy) return <div className="loading">{t("patients.loading")}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("nav.patients")}</h2>
          <p>{t("patients.lead")}</p>
        </div>
        <div className="toolbar">
          <input className="input search" placeholder={t("patients.search")} value={search} onChange={(e) => setSearch(e.target.value)} />
          <button
            className="btn"
            onClick={() => {
              setForm(emptyPatient);
              setOpen(true);
            }}
          >
            {t("patients.add")}
          </button>
        </div>
      </div>
      {error && <div className="error">{localizeError(error, t)}</div>}
      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>{t("patients.name")}</th>
              <th>{t("patients.phone")}</th>
              <th>{t("patients.allergies")}</th>
              <th>{t("patients.visits")}</th>
              <th>{t("patients.lastVisit")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="clickable" onClick={() => navigate(`/patients/${row.id}`)}>
                <td>{fullName(row)}</td>
                <td>{row.phone}</td>
                <td>{row.allergies || "—"}</td>
                <td>{row.prescription_count}</td>
                <td>{formatDate(row.last_visit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="empty">{t("patients.empty")}</p>}
      </section>

      {open && (
        <Modal title={t("patients.add")} onClose={() => setOpen(false)}>
          <form onSubmit={save}>
            <div className="form-grid">
              <label>
                <span>{t("patients.firstName")}</span>
                <input className="input" required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
              </label>
              <label>
                <span>{t("patients.lastName")}</span>
                <input className="input" required value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
              </label>
              <label>
                <span>{t("patients.phone")}</span>
                <input className="input" required value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </label>
              <label>
                <span>{t("patients.dob")}</span>
                <input className="input" type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
              </label>
              <label>
                <span>{t("patients.gender")}</span>
                <Dropdown
                  value={form.gender}
                  onChange={(value) => setForm({ ...form, gender: value })}
                  options={[
                    { value: "", label: t("patients.select") },
                    { value: "female", label: t("gender.female") },
                    { value: "male", label: t("gender.male") },
                    { value: "other", label: t("gender.other") },
                  ]}
                />
              </label>
              <label>
                <span>{t("patients.allergies")}</span>
                <input className="input" value={form.allergies} onChange={(e) => setForm({ ...form, allergies: e.target.value })} />
              </label>
              <label className="full">
                <span>{t("patients.address")}</span>
                <input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
              </label>
              <label className="full">
                <span>{t("patients.notes")}</span>
                <textarea rows="3" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn ghost" onClick={() => setOpen(false)}>
                {t("common.cancel")}
              </button>
              <button className="btn" type="submit">
                {t("common.save")}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
