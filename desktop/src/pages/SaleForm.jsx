import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { money } from "../lib/format";
import { findByBarcode, Highlight, suggestionsFor } from "../lib/medicineSearch.jsx";
import { usePharmacy } from "../layout/PharmacyContext";

const TAX_KEY = "pharmacare_tax_percent";
const METHODS = ["cash", "card", "bank_transfer", "other"];

function round2(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function percent(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return 0;
  return Math.min(number, 100);
}

function readTax() {
  try {
    return localStorage.getItem(TAX_KEY) || "0";
  } catch {
    return "0";
  }
}

export default function SaleForm() {
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const prescriptionId = params.get("prescription");
  const searchRef = useRef(null);

  const [medicines, setMedicines] = useState([]);
  const [prescription, setPrescription] = useState(null);
  const [lines, setLines] = useState([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [customer, setCustomer] = useState({ name: "", phone: "" });
  const [discount, setDiscount] = useState("0");
  const [tax, setTax] = useState(readTax);
  const [method, setMethod] = useState("cash");
  const [received, setReceived] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!pharmacy) return;
    const loads = [api.medicines(pharmacy.id)];
    if (prescriptionId) loads.push(api.prescription(prescriptionId));
    Promise.all(loads)
      .then(([stock, rx]) => {
        setMedicines(stock.filter((medicine) => medicine.is_active));
        if (rx) {
          setPrescription(rx);
          setLines(rx.items.map((item) => ({ medicine_id: item.medicine_id, quantity: String(item.quantity) })));
        }
        setReady(true);
      })
      .catch((err) => setError(err.message));
  }, [pharmacy, prescriptionId]);

  useEffect(() => {
    if (ready) searchRef.current?.focus();
  }, [ready]);

  const byId = new Map(medicines.map((medicine) => [medicine.id, medicine]));
  const choices = suggestionsFor(medicines, query);
  const highlighted = Math.min(activeIndex, Math.max(choices.length - 1, 0));

  function addMedicine(medicine) {
    setLines((current) => {
      const existing = current.find((line) => line.medicine_id === medicine.id);
      if (existing) {
        return current.map((line) =>
          line.medicine_id === medicine.id ? { ...line, quantity: String((Number(line.quantity) || 0) + 1) } : line,
        );
      }
      return [...current, { medicine_id: medicine.id, quantity: "1" }];
    });
    setQuery("");
    setOpen(false);
    setActiveIndex(0);
    setError("");
    searchRef.current?.focus();
  }

  function onSearchKey(event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setOpen(true);
      setActiveIndex(Math.max(0, Math.min(highlighted + delta, choices.length - 1)));
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const scanned = findByBarcode(medicines, query);
      if (scanned) addMedicine(scanned);
      else if (choices[highlighted]) addMedicine(choices[highlighted]);
    }
  }

  function setQuantity(medicineId, value) {
    if (value !== "" && !/^\d+$/.test(value)) return;
    setLines((current) => current.map((line) => (line.medicine_id === medicineId ? { ...line, quantity: value } : line)));
  }

  function removeLine(medicineId) {
    setLines((current) => current.filter((line) => line.medicine_id !== medicineId));
  }

  function changeTax(value) {
    setTax(value);
    try {
      localStorage.setItem(TAX_KEY, value || "0");
    } catch {
      /* the saved rate is only a convenience */
    }
  }

  const rows = lines
    .map((line) => {
      const medicine = byId.get(line.medicine_id);
      const quantity = Number(line.quantity) || 0;
      const price = Number(medicine?.unit_price || 0);
      return { ...line, medicine, qty: quantity, price, amount: round2(price * quantity) };
    })
    .filter((row) => row.medicine);
  const subtotal = round2(rows.reduce((sum, row) => sum + row.amount, 0));
  const discountPercent = percent(discount);
  const taxPercent = percent(tax);
  const discountAmount = round2((subtotal * discountPercent) / 100);
  const taxAmount = round2(((subtotal - discountAmount) * taxPercent) / 100);
  const total = round2(subtotal - discountAmount + taxAmount);
  const receivedAmount = received === "" ? null : Number(received);
  const change = receivedAmount === null ? 0 : round2(receivedAmount - total);
  const overStock = rows.filter((row) => row.qty > row.medicine.sellable_quantity);
  const rxOnly = prescription ? [] : rows.filter((row) => row.medicine.requires_prescription);
  const hasBlankQty = rows.some((row) => row.qty <= 0);
  const short = method === "cash" && receivedAmount !== null && change < 0;
  const canSave = rows.length > 0 && !hasBlankQty && overStock.length === 0 && !short && !saving;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError("");
    try {
      const sale = await api.createSale({
        pharmacy_id: pharmacy.id,
        prescription_id: prescription ? prescription.id : null,
        customer_name: prescription ? null : customer.name,
        customer_phone: prescription ? null : customer.phone,
        items: rows.map((row) => ({ medicine_id: row.medicine_id, quantity: row.qty })),
        discount_percent: discountPercent,
        tax_percent: taxPercent,
        payment_method: method,
        amount_paid: method === "cash" && receivedAmount !== null ? receivedAmount : null,
        notes,
      });
      navigate(`/billing/${sale.id}?created=1`, { replace: true });
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  if (!pharmacy || (!ready && !error)) return <div className="loading">{t("sale.loading")}</div>;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{prescription ? t("sale.forRx", { name: prescription.patient_name }) : t("bill.new")}</h2>
          <p>{prescription ? t("sale.rxPrefilled") : t("sale.lead")}</p>
        </div>
        {prescription && (
          <Link className="btn ghost" to={`/prescriptions/${prescription.id}`}>
            {t("saleDetail.openRx")}
          </Link>
        )}
      </div>
      {error && <div className="error">{localizeError(error, t)}</div>}

      <div className="pos-layout">
        <section className="panel pos-cart">
          <div className="suggest pos-search">
            <input
              ref={searchRef}
              className="input"
              placeholder={t("sale.search")}
              value={query}
              autoComplete="off"
              onFocus={() => setOpen(true)}
              onBlur={() => window.setTimeout(() => setOpen(false), 150)}
              onChange={(event) => {
                setQuery(event.target.value);
                setOpen(true);
                setActiveIndex(0);
              }}
              onKeyDown={onSearchKey}
            />
            {open && query.trim() && (
              <ul className="suggest-list">
                {choices.length === 0 && <li className="suggest-empty">{t("suggest.noMatch", { query: query.trim() })}</li>}
                {choices.map((medicine, index) => (
                  <li key={medicine.id}>
                    <button
                      type="button"
                      className={`suggest-item ${index === highlighted ? "active" : ""}`}
                      onMouseDown={(event) => event.preventDefault()}
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => addMedicine(medicine)}
                      disabled={medicine.sellable_quantity <= 0}
                    >
                      <span>
                        <span className="suggest-name">
                          <Highlight text={medicine.name} query={query} />
                          {medicine.requires_prescription && <span className="badge recorded tag">{t("sale.rxOnly")}</span>}
                        </span>
                        <span className="suggest-meta">
                          <Highlight text={medicine.salt || t("inv.saltNotSet")} query={query} />
                          {" · "}
                          <Highlight text={medicine.manufacturer || t("suggest.companyNotSet")} query={query} />
                          {" · "}
                          {money(medicine.unit_price)}
                        </span>
                      </span>
                      <span className="suggest-stock">
                        {medicine.sellable_quantity > 0 ? t("sale.available", { n: medicine.sellable_quantity }) : t("sale.noStock")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <table className="cart-table">
            <thead>
              <tr>
                <th>{t("dash.medicine")}</th>
                <th className="num">{t("sale.price")}</th>
                <th className="qty-cell">{t("dash.qty")}</th>
                <th className="num">{t("sale.amount")}</th>
                <th aria-label={t("sale.remove")} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const over = row.qty > row.medicine.sellable_quantity;
                return (
                  <tr key={row.medicine_id}>
                    <td>
                      <strong>{row.medicine.name}</strong>
                      {row.medicine.requires_prescription && <span className="badge recorded tag">{t("sale.rxOnly")}</span>}
                      <div className={over ? "stock-warn" : "muted"}>
                        {over
                          ? t("sale.onlyAvailable", { n: row.medicine.sellable_quantity })
                          : [row.medicine.salt, row.medicine.manufacturer, t("sale.available", { n: row.medicine.sellable_quantity })]
                              .filter(Boolean)
                              .join(" · ")}
                      </div>
                    </td>
                    <td className="num">{money(row.price)}</td>
                    <td className="qty-cell">
                      <input
                        className={`input qty-input ${over || row.qty <= 0 ? "invalid" : ""}`}
                        inputMode="numeric"
                        value={row.quantity}
                        onChange={(e) => setQuantity(row.medicine_id, e.target.value)}
                      />
                    </td>
                    <td className="num">{money(row.amount)}</td>
                    <td className="qty-cell">
                      <button type="button" className="btn ghost" onClick={() => removeLine(row.medicine_id)}>
                        {t("sale.remove")}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 && <p className="empty">{t("sale.cartEmpty")}</p>}
          {rxOnly.length > 0 && (
            <div className="allergy-banner">
              {t("sale.rxWarning", { names: rxOnly.map((row) => row.medicine.name).join(", ") })}
            </div>
          )}
        </section>

        <aside className="panel pos-side">
          {!prescription && (
            <>
              <h3>{t("sale.customer")}</h3>
              <div className="form-grid">
                <label>
                  <span className="field-label">{t("sale.customerName")}</span>
                  <input className="input" value={customer.name} onChange={(e) => setCustomer({ ...customer, name: e.target.value })} />
                </label>
                <label>
                  <span className="field-label">{t("sale.customerPhone")}</span>
                  <input className="input" value={customer.phone} onChange={(e) => setCustomer({ ...customer, phone: e.target.value })} />
                </label>
              </div>
            </>
          )}

          <div className="form-grid">
            <label>
              <span className="field-label">{t("sale.discount")}</span>
              <input className="input" type="number" min="0" max="100" step="0.5" value={discount} onChange={(e) => setDiscount(e.target.value)} />
            </label>
            <label>
              <span className="field-label">{t("sale.tax")}</span>
              <input className="input" type="number" min="0" max="100" step="0.5" value={tax} onChange={(e) => changeTax(e.target.value)} />
            </label>
          </div>

          <dl className="totals">
            <div>
              <dt>{t("sale.subtotal")}</dt>
              <dd>{money(subtotal)}</dd>
            </div>
            {discountAmount > 0 && (
              <div>
                <dt>{t("sale.discountLine", { p: discountPercent })}</dt>
                <dd>− {money(discountAmount)}</dd>
              </div>
            )}
            {taxAmount > 0 && (
              <div>
                <dt>{t("sale.taxLine", { p: taxPercent })}</dt>
                <dd>{money(taxAmount)}</dd>
              </div>
            )}
            <div className="grand">
              <dt>{t("sale.total")}</dt>
              <dd>{money(total)}</dd>
            </div>
          </dl>

          <span className="field-label">{t("sale.paymentMethod")}</span>
          <div className="segmented full-width" role="group">
            {METHODS.map((value) => (
              <button key={value} type="button" className={method === value ? "active" : ""} onClick={() => setMethod(value)}>
                {named("pay", value)}
              </button>
            ))}
          </div>

          {method === "cash" && (
            <div className="form-grid">
              <label>
                <span className="field-label">{t("sale.received")}</span>
                <input className="input" type="number" min="0" step="1" value={received} onChange={(e) => setReceived(e.target.value)} />
              </label>
              <div>
                <span className="field-label">{t("sale.change")}</span>
                <div className={`change-due ${short ? "short" : ""}`}>
                  {short ? t("sale.short", { amount: money(-change) }) : money(Math.max(change, 0))}
                </div>
              </div>
            </div>
          )}

          <label className="full">
            <span className="field-label">{t("sale.notes")}</span>
            <input className="input" value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} />
          </label>

          <button type="button" className="btn pos-complete" disabled={!canSave} onClick={save}>
            {saving ? t("sale.saving") : `${t("sale.complete")} · ${money(total)}`}
          </button>
        </aside>
      </div>
    </div>
  );
}
