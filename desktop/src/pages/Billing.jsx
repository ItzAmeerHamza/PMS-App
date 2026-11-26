import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import Dropdown from "../components/Dropdown";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { addDays, formatDateTime, fromInputDate, money, startOfDay, toInputDate } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

function presetRange(days) {
  const today = startOfDay();
  return { from: toInputDate(addDays(today, -(days - 1))), to: toInputDate(today) };
}

export default function Billing() {
  const pharmacy = usePharmacy();
  const { t, named } = useI18n();
  const navigate = useNavigate();
  const [range, setRange] = useState(() => presetRange(1));
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!pharmacy || !range.from || !range.to) return;
    const start = fromInputDate(range.from);
    const end = addDays(fromInputDate(range.to), 1);
    const timer = window.setTimeout(() => {
      api
        .sales(pharmacy.id, { start, end, search: search.trim(), status })
        .then((result) => {
          setData(result);
          setError("");
        })
        .catch((err) => setError(err.message));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [pharmacy, range, search, status]);

  if (!pharmacy) return <div className="loading">{t("bill.loading")}</div>;

  const presets = [
    { days: 1, label: t("bill.today") },
    { days: 7, label: t("bill.week") },
    { days: 30, label: t("bill.month") },
  ];
  const summary = data?.summary;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("nav.billing")}</h2>
          <p>{t("bill.lead")}</p>
        </div>
        <Link className="btn" to="/billing/new">
          {t("bill.new")}
        </Link>
      </div>

      <div className="bill-filters">
        <div className="segmented" role="group">
          {presets.map((preset) => {
            const value = presetRange(preset.days);
            const active = value.from === range.from && value.to === range.to;
            return (
              <button key={preset.days} type="button" className={active ? "active" : ""} onClick={() => setRange(value)}>
                {preset.label}
              </button>
            );
          })}
        </div>
        <label className="inline-field">
          <span>{t("bill.from")}</span>
          <input
            className="input"
            type="date"
            value={range.from}
            max={range.to}
            onChange={(e) => e.target.value && setRange((r) => ({ ...r, from: e.target.value }))}
          />
        </label>
        <label className="inline-field">
          <span>{t("bill.to")}</span>
          <input
            className="input"
            type="date"
            value={range.to}
            min={range.from}
            onChange={(e) => e.target.value && setRange((r) => ({ ...r, to: e.target.value }))}
          />
        </label>
        <input
          className="input search"
          placeholder={t("bill.search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Dropdown
          ariaLabel={t("dash.status")}
          value={status}
          onChange={setStatus}
          options={[
            { value: "", label: t("bill.allStatuses") },
            { value: "paid", label: t("status.paid") },
            { value: "void", label: t("status.void") },
          ]}
        />
      </div>

      {error && <div className="error">{localizeError(error, t)}</div>}

      {summary && (
        <div className="card-grid">
          <div className="stat-card">
            <span>{t("bill.sales")}</span>
            <strong>{money(summary.total)}</strong>
          </div>
          <div className="stat-card">
            <span>{t("bill.count")}</span>
            <strong>{summary.count}</strong>
          </div>
          <div className="stat-card">
            <span>{t("bill.discounts")}</span>
            <strong>{money(summary.discount)}</strong>
          </div>
          <div className="stat-card">
            <span>{t("bill.payment")}</span>
            <div className="method-split">
              {Object.keys(summary.by_method).length === 0 && <span>—</span>}
              {Object.entries(summary.by_method).map(([method, amount]) => (
                <div key={method}>
                  <span>{named("pay", method)}</span>
                  <b>{money(amount)}</b>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <section className="panel">
        {!data ? (
          <p className="empty">{t("bill.loading")}</p>
        ) : (
          <>
            <table>
              <thead>
                <tr>
                  <th>{t("bill.invoice")}</th>
                  <th>{t("dash.date")}</th>
                  <th>{t("bill.customer")}</th>
                  <th>{t("bill.items")}</th>
                  <th>{t("bill.payment")}</th>
                  <th className="num">{t("bill.total")}</th>
                  <th>{t("dash.status")}</th>
                </tr>
              </thead>
              <tbody>
                {data.sales.map((sale) => (
                  <tr key={sale.id} className="clickable" onClick={() => navigate(`/billing/${sale.id}`)}>
                    <td>
                      <strong>{sale.invoice_number}</strong>
                      {sale.prescription_id && <span className="badge recorded tag">Rx</span>}
                    </td>
                    <td>{formatDateTime(sale.created_at)}</td>
                    <td>
                      {sale.customer_name || t("bill.walkIn")}
                      {sale.customer_phone && <div className="muted">{sale.customer_phone}</div>}
                    </td>
                    <td>{sale.item_count}</td>
                    <td>{named("pay", sale.payment_method)}</td>
                    <td className="num">{money(sale.total)}</td>
                    <td>
                      <span className={`badge ${sale.status === "paid" ? "ok" : "cancelled"}`}>
                        {named("status", sale.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.sales.length === 0 && <p className="empty">{t("bill.empty")}</p>}
          </>
        )}
      </section>
    </div>
  );
}
