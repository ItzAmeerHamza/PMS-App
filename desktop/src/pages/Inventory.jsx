import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import Dropdown from "../components/Dropdown";
import Modal from "../components/Modal";
import { localizeError } from "../i18n/catalog";
import { useI18n, withName } from "../i18n/LanguageContext.jsx";
import { formatDate, money } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

const FORMS = ["tablet", "capsule", "syrup", "suspension", "injection", "ointment", "cream", "drops", "inhaler", "sachet", "gel"];

const emptyMedicine = {
  sku: "",
  name: "",
  salt: "",
  manufacturer: "",
  form: "tablet",
  strength: "",
  pack_size: "",
  category: "",
  barcode: "",
  rack_location: "",
  unit_price: "",
  reorder_level: 10,
  requires_prescription: false,
  is_active: true,
  notes: "",
};

export default function Inventory() {
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [lowStock, setLowStock] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyMedicine);
  const [batchForm, setBatchForm] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [importResult, setImportResult] = useState(null);
  const fileRef = useRef(null);

  function updateField(key) {
    return (event) => {
      const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
      setForm((current) => ({ ...current, [key]: value }));
    };
  }

  async function load() {
    if (!pharmacy) return;
    try {
      setRows(await api.medicines(pharmacy.id, { search, lowStock }));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [pharmacy, search, lowStock]);

  function openCreate() {
    setEditing("new");
    setForm(emptyMedicine);
    setError("");
  }

  function openEdit(row) {
    setEditing(row);
    setForm({
      sku: row.sku,
      name: row.name,
      salt: row.salt || row.generic_name || "",
      manufacturer: row.manufacturer || "",
      form: row.form || "tablet",
      strength: row.strength || "",
      pack_size: row.pack_size || "",
      category: row.category || "",
      barcode: row.barcode || "",
      rack_location: row.rack_location || "",
      unit_price: row.unit_price,
      reorder_level: row.reorder_level,
      requires_prescription: Boolean(row.requires_prescription),
      is_active: row.is_active !== false,
      notes: row.notes || "",
    });
    setError("");
  }

  async function saveMedicine(event) {
    event.preventDefault();
    const payload = {
      ...form,
      pharmacy_id: pharmacy.id,
      unit_price: Number(form.unit_price || 0),
      reorder_level: Number(form.reorder_level || 0),
    };
    try {
      if (editing === "new") {
        await api.createMedicine(payload);
      } else {
        await api.updateMedicine(editing.id, payload);
      }
      setEditing(null);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeMedicine() {
    if (!pendingDelete) return;
    try {
      await api.deleteMedicine(pendingDelete.id);
      setPendingDelete(null);
      load();
    } catch (err) {
      setPendingDelete(null);
      setError(err.message);
    }
  }

  function openImport() {
    setImportOpen(true);
    setImportFile(null);
    setImportError("");
    setImportResult(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  function downloadSample() {
    const csv = [
      "name,sku,salt,company,form,strength,pack,category,barcode,rack,price,reorder,rx,notes,quantity,batch,expiry,cost",
      "Crocin 500,CRO-500,Paracetamol,GSK,tablet,500mg,Strip of 15,Analgesic,,A-12,25,20,no,After food,100,B-100,2027-06-30,18",
    ].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "medicines-sample.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function importMedicines(event) {
    event.preventDefault();
    if (!importFile) {
      setImportError(t("inv.noFile"));
      return;
    }
    setImporting(true);
    setImportError("");
    try {
      const result = await api.importMedicines(pharmacy.id, importFile);
      setImportResult(result);
      if (result.created) load();
    } catch (err) {
      setImportError(err.message);
    } finally {
      setImporting(false);
    }
  }

  function issueList(items) {
    const shown = items.slice(0, 8);
    return (
      <>
        <ul className="import-issues">
          {shown.map((issue) => (
            <li key={`${issue.row}-${issue.sku || ""}-${issue.message}`}>
              {t("inv.rowIssue", { row: issue.row })}
              {issue.name ? ` · ${issue.name}` : ""}
              {issue.sku ? ` · ${issue.sku}` : ""}
              {" — "}
              {localizeError(issue.message, t)}
            </li>
          ))}
        </ul>
        {items.length > shown.length && <p className="muted">{t("inv.moreIssues", { n: items.length - shown.length })}</p>}
      </>
    );
  }

  async function saveBatch(event) {
    event.preventDefault();
    try {
      await api.addBatch(batchForm.medicineId, {
        batch_number: batchForm.batch_number,
        expiry_date: batchForm.expiry_date,
        quantity: Number(batchForm.quantity),
        cost_price: Number(batchForm.cost_price || 0),
        selling_price: Number(batchForm.selling_price || 0),
      });
      setBatchForm(null);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!pharmacy) return <div className="loading">{t("inv.loading")}</div>;

  const formOptions = FORMS.includes(form.form) ? FORMS : [form.form, ...FORMS];

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("nav.inventory")}</h2>
          <p>{t("inv.lead")}</p>
        </div>
        <div className="toolbar">
          <input
            className="input search"
            placeholder={t("inv.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className={`btn ${lowStock ? "" : "ghost"}`} onClick={() => setLowStock((v) => !v)}>
            {t("dash.lowStock")}
          </button>
          <button className="btn ghost" onClick={openImport}>
            {t("inv.upload")}
          </button>
          <button className="btn" onClick={openCreate}>
            {t("inv.add")}
          </button>
        </div>
      </div>
      {error && <div className="error">{localizeError(error, t)}</div>}
      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>{t("dash.medicine")}</th>
              <th>{t("inv.company")}</th>
              <th>{t("dash.qty")}</th>
              <th>{t("inv.price")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>{row.name}</strong>{" "}
                  {!row.is_active && <span className="badge inactive">{t("status.inactive")}</span>}
                  {row.requires_prescription && <span className="badge recorded">Rx</span>}
                  <div className="muted">{row.salt || t("inv.saltNotSet")}</div>
                  <div className="muted">
                    {[
                      row.sku,
                      row.strength,
                      row.form ? named("form", row.form) : "",
                      row.pack_size,
                      row.rack_location ? t("inv.rack", { location: row.rack_location }) : "",
                      row.nearest_expiry ? t("inv.exp", { date: formatDate(row.nearest_expiry) }) : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </td>
                <td>{row.manufacturer || "—"}</td>
                <td>
                  {row.quantity_on_hand} {row.is_low_stock && <span className="badge low">{t("status.low")}</span>}
                </td>
                <td>{money(row.unit_price)}</td>
                <td className="row-actions">
                  <button className="btn ghost" onClick={() => openEdit(row)}>
                    {t("common.edit")}
                  </button>
                  <button
                    className="btn ghost"
                    onClick={() =>
                      setBatchForm({
                        medicineId: row.id,
                        name: row.name,
                        batch_number: "",
                        expiry_date: "",
                        quantity: "",
                        cost_price: "",
                        selling_price: row.unit_price,
                      })
                    }
                  >
                    {t("inv.addStock")}
                  </button>
                  <button className="btn ghost" onClick={() => setPendingDelete(row)}>
                    {t("common.delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="empty">{t("inv.empty")}</p>}
      </section>

      {editing && (
        <Modal title={editing === "new" ? t("inv.add") : t("inv.editTitle")} onClose={() => setEditing(null)}>
          <form onSubmit={saveMedicine}>
            <div className="form-grid">
              <label>
                <span>{t("inv.name")}</span>
                <input className="input" required value={form.name} onChange={updateField("name")} placeholder={t("inv.namePlaceholder")} />
              </label>
              <label>
                <span>{t("inv.sku")}</span>
                <input className="input" required value={form.sku} onChange={updateField("sku")} placeholder={t("inv.skuPlaceholder")} />
              </label>
              <label>
                <span>{t("inv.salt")}</span>
                <input
                  className="input"
                  value={form.salt}
                  onChange={updateField("salt")}
                  placeholder={t("inv.saltPlaceholder")}
                />
              </label>
              <label>
                <span>{t("inv.company")}</span>
                <input
                  className="input"
                  value={form.manufacturer}
                  onChange={updateField("manufacturer")}
                  placeholder={t("inv.companyPlaceholder")}
                />
              </label>
              <label>
                <span>{t("inv.form")}</span>
                <Dropdown
                  value={form.form}
                  onChange={(value) => updateField("form")({ target: { value, type: "text" } })}
                  options={formOptions.map((option) => ({ value: option, label: named("form", option) }))}
                />
              </label>
              <label>
                <span>{t("inv.strength")}</span>
                <input className="input" value={form.strength} onChange={updateField("strength")} placeholder={t("inv.strengthPlaceholder")} />
              </label>
              <label>
                <span>{t("inv.pack")}</span>
                <input className="input" value={form.pack_size} onChange={updateField("pack_size")} placeholder={t("inv.packPlaceholder")} />
              </label>
              <label>
                <span>{t("inv.category")}</span>
                <input className="input" value={form.category} onChange={updateField("category")} placeholder={t("inv.categoryPlaceholder")} />
              </label>
              <label>
                <span>{t("inv.barcode")}</span>
                <input className="input" value={form.barcode} onChange={updateField("barcode")} />
              </label>
              <label>
                <span>{t("inv.rackLabel")}</span>
                <input className="input" value={form.rack_location} onChange={updateField("rack_location")} placeholder={t("inv.rackPlaceholder")} />
              </label>
              <label>
                <span>{t("inv.sellingPrice")}</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.unit_price}
                  onChange={updateField("unit_price")}
                />
              </label>
              <label>
                <span>{t("inv.reorderLevel")}</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  value={form.reorder_level}
                  onChange={updateField("reorder_level")}
                />
              </label>
              <div className="full checks">
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={form.requires_prescription}
                    onChange={updateField("requires_prescription")}
                  />
                  <span>{t("inv.rxRequired")}</span>
                </label>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={updateField("is_active")}
                  />
                  <span>{t("inv.active")}</span>
                </label>
              </div>
              <label className="full">
                <span>{t("patients.notes")}</span>
                <textarea rows="2" value={form.notes} onChange={updateField("notes")} placeholder={t("inv.notesPlaceholder")} />
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn ghost" onClick={() => setEditing(null)}>
                {t("common.cancel")}
              </button>
              <button className="btn" type="submit">
                {t("common.save")}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {pendingDelete && (
        <Modal title={t("inv.deleteTitle")} onClose={() => setPendingDelete(null)}>
          <p>{withName(t("inv.deleteBody"), pendingDelete.name)}</p>
          <div className="modal-actions">
            <button type="button" className="btn ghost" onClick={() => setPendingDelete(null)}>
              {t("common.cancel")}
            </button>
            <button type="button" className="btn danger" onClick={removeMedicine}>
              {t("common.delete")}
            </button>
          </div>
        </Modal>
      )}

      {importOpen && (
        <Modal title={t("inv.uploadTitle")} onClose={() => setImportOpen(false)}>
          <form onSubmit={importMedicines}>
            <p className="import-lead">{t("inv.uploadLead")}</p>
            <p className="import-lead">{t("inv.uploadColumns")}</p>
            <div className="import-file">
              <button type="button" className="btn ghost" onClick={() => fileRef.current?.click()}>
                {t("inv.chooseFile")}
              </button>
              <span>{importFile ? importFile.name : ""}</span>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={(event) => {
                  setImportFile(event.target.files?.[0] || null);
                  setImportResult(null);
                  setImportError("");
                }}
              />
            </div>
            {importError && <div className="error import-error">{localizeError(importError, t)}</div>}
            {importResult && (
              <div className="import-result">
                <p>{t("inv.importSummary", { created: importResult.created, skipped: importResult.skipped.length })}</p>
                {importResult.errors.length > 0 && (
                  <>
                    <strong>{t("inv.importErrors")}</strong>
                    {issueList(importResult.errors)}
                  </>
                )}
                {importResult.skipped.length > 0 && (
                  <>
                    <strong>{t("inv.importSkipped")}</strong>
                    {issueList(importResult.skipped)}
                  </>
                )}
              </div>
            )}
            <div className="modal-actions">
              <button type="button" className="btn ghost" onClick={downloadSample}>
                {t("inv.downloadSample")}
              </button>
              <button type="button" className="btn ghost" onClick={() => setImportOpen(false)}>
                {t("common.cancel")}
              </button>
              <button className="btn" type="submit" disabled={importing}>
                {importing ? t("inv.importing") : t("inv.import")}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {batchForm && (
        <Modal title={t("inv.addStockTitle", { name: batchForm.name })} onClose={() => setBatchForm(null)}>
          <form onSubmit={saveBatch}>
            <div className="form-grid">
              <label>
                <span>{t("inv.batchNumber")}</span>
                <input className="input" required value={batchForm.batch_number} onChange={(e) => setBatchForm({ ...batchForm, batch_number: e.target.value })} />
              </label>
              <label>
                <span>{t("dash.expiry")}</span>
                <input className="input" type="date" required value={batchForm.expiry_date} onChange={(e) => setBatchForm({ ...batchForm, expiry_date: e.target.value })} />
              </label>
              <label>
                <span>{t("inv.quantity")}</span>
                <input className="input" type="number" min="0" required value={batchForm.quantity} onChange={(e) => setBatchForm({ ...batchForm, quantity: e.target.value })} />
              </label>
              <label>
                <span>{t("inv.sellingPrice")}</span>
                <input className="input" type="number" min="0" step="0.01" value={batchForm.selling_price} onChange={(e) => setBatchForm({ ...batchForm, selling_price: e.target.value })} />
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn ghost" onClick={() => setBatchForm(null)}>
                {t("common.cancel")}
              </button>
              <button className="btn" type="submit">
                {t("inv.addBatch")}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
