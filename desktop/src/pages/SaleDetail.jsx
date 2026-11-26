import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import Modal from "../components/Modal";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDate, formatDateTime, money } from "../lib/format";
import { usePharmacy } from "../layout/PharmacyContext";

function batchText(item) {
  return item.allocations.map((alloc) => `${alloc.batch_number} (${alloc.quantity}) ${formatDate(alloc.expiry_date)}`).join(", ");
}

export default function SaleDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const { t, named } = useI18n();
  const pharmacy = usePharmacy();
  const [sale, setSale] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiding, setVoiding] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    api
      .sale(id)
      .then((result) => {
        setSale(result);
        if (params.get("created")) setNotice(t("saleDetail.billed", { number: result.invoice_number }));
      })
      .catch((err) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function print() {
    setError("");
    setNotice("");
    if (!window.pharmacare?.print) {
      window.print();
      return;
    }
    setBusy(true);
    try {
      const result = await window.pharmacare.print();
      if (!result?.ok) setError(result?.error || "The printer did not accept this page");
      else setNotice(t("rxDetail.sentTo", { name: result.printer }));
    } catch {
      setError("The printer did not accept this page");
    } finally {
      setBusy(false);
    }
  }

  async function confirmVoid() {
    setBusy(true);
    try {
      setSale(await api.voidSale(id, reason));
      setVoiding(false);
      setError("");
      setNotice("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!sale) return <div className="loading">{error ? localizeError(error, t) : t("saleDetail.loading")}</div>;

  const isVoid = sale.status === "void";
  const customer = sale.customer_name || t("bill.walkIn");

  return (
    <div>
      <div className="page-head screen-only">
        <div>
          <h2>{sale.invoice_number}</h2>
          <p>
            {customer} · {formatDateTime(sale.created_at)}
            {sale.staff_name ? ` · ${t("saleDetail.servedBy", { name: sale.staff_name })}` : ""}
          </p>
        </div>
        <div className="toolbar">
          <span className={`badge ${isVoid ? "cancelled" : "ok"}`}>{named("status", sale.status)}</span>
          {sale.prescription_id && (
            <Link className="btn ghost" to={`/prescriptions/${sale.prescription_id}`}>
              {t("saleDetail.openRx")}
            </Link>
          )}
          {!isVoid && (
            <button className="btn ghost" type="button" disabled={busy} onClick={() => setVoiding(true)}>
              {t("saleDetail.void")}
            </button>
          )}
          <button className="btn ghost" type="button" disabled={busy || isVoid} onClick={print}>
            {t("saleDetail.print")}
          </button>
          <Link className="btn" to="/billing/new">
            {t("bill.new")}
          </Link>
        </div>
      </div>
      {error && <div className="error screen-only">{localizeError(error, t)}</div>}
      {notice && <div className="notice screen-only">{notice}</div>}
      {isVoid && (
        <div className="error screen-only">
          {t("saleDetail.voidedOn", { date: formatDateTime(sale.voided_at) })}
          {sale.void_reason ? ` · ${sale.void_reason}` : ""}
        </div>
      )}

      <div className="pos-layout screen-only">
        <section className="panel">
          <table>
            <thead>
              <tr>
                <th>{t("dash.medicine")}</th>
                <th className="num">{t("sale.price")}</th>
                <th className="qty-cell">{t("dash.qty")}</th>
                <th className="num">{t("sale.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {sale.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.medicine_name}
                    <div className="muted">
                      {t("saleDetail.batches")}: {batchText(item)}
                    </div>
                  </td>
                  <td className="num">{money(item.unit_price)}</td>
                  <td className="qty-cell">{item.quantity}</td>
                  <td className="num">{money(item.line_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <aside className="panel pos-side">
          <dl className="totals">
            <div>
              <dt>{t("sale.subtotal")}</dt>
              <dd>{money(sale.subtotal)}</dd>
            </div>
            {Number(sale.discount_amount) > 0 && (
              <div>
                <dt>{t("sale.discountLine", { p: Number(sale.discount_percent) })}</dt>
                <dd>− {money(sale.discount_amount)}</dd>
              </div>
            )}
            {Number(sale.tax_amount) > 0 && (
              <div>
                <dt>{t("sale.taxLine", { p: Number(sale.tax_percent) })}</dt>
                <dd>{money(sale.tax_amount)}</dd>
              </div>
            )}
            <div className="grand">
              <dt>{t("sale.total")}</dt>
              <dd>{money(sale.total)}</dd>
            </div>
            <div>
              <dt>
                {t("saleDetail.paid")} · {named("pay", sale.payment_method)}
              </dt>
              <dd>{money(sale.amount_paid)}</dd>
            </div>
            {Number(sale.change_due) > 0 && (
              <div>
                <dt>{t("saleDetail.change")}</dt>
                <dd>{money(sale.change_due)}</dd>
              </div>
            )}
          </dl>
          {sale.customer_phone && <p className="muted">{sale.customer_phone}</p>}
          {sale.notes && <p className="muted">{sale.notes}</p>}
        </aside>
      </div>

      <article className="print-sheet invoice-sheet">
        <header className="print-head">
          <h1>{pharmacy?.name || "PharmaCare"}</h1>
          {pharmacy?.address && <p>{pharmacy.address}</p>}
          <p>
            {[pharmacy?.phone, pharmacy?.license_number ? t("rxDetail.license", { number: pharmacy.license_number }) : ""]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </header>
        <h2>{t("saleDetail.printTitle")}</h2>
        <div className="print-meta">
          <div>
            <strong>{customer}</strong>
            {sale.customer_phone && <div>{sale.customer_phone}</div>}
          </div>
          <div>
            <strong>{sale.invoice_number}</strong>
            <div>{formatDateTime(sale.created_at)}</div>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t("dash.medicine")}</th>
              <th>{t("dash.batch")}</th>
              <th className="num">{t("sale.price")}</th>
              <th className="num">{t("dash.qty")}</th>
              <th className="num">{t("sale.amount")}</th>
            </tr>
          </thead>
          <tbody>
            {sale.items.map((item) => (
              <tr key={item.id}>
                <td>{item.medicine_name}</td>
                <td>{batchText(item)}</td>
                <td className="num">{money(item.unit_price)}</td>
                <td className="num">{item.quantity}</td>
                <td className="num">{money(item.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="totals print-totals">
          <div>
            <dt>{t("sale.subtotal")}</dt>
            <dd>{money(sale.subtotal)}</dd>
          </div>
          {Number(sale.discount_amount) > 0 && (
            <div>
              <dt>{t("sale.discountLine", { p: Number(sale.discount_percent) })}</dt>
              <dd>− {money(sale.discount_amount)}</dd>
            </div>
          )}
          {Number(sale.tax_amount) > 0 && (
            <div>
              <dt>{t("sale.taxLine", { p: Number(sale.tax_percent) })}</dt>
              <dd>{money(sale.tax_amount)}</dd>
            </div>
          )}
          <div className="grand">
            <dt>{t("sale.total")}</dt>
            <dd>{money(sale.total)}</dd>
          </div>
          <div>
            <dt>
              {t("saleDetail.paid")} · {named("pay", sale.payment_method)}
            </dt>
            <dd>{money(sale.amount_paid)}</dd>
          </div>
          {Number(sale.change_due) > 0 && (
            <div>
              <dt>{t("saleDetail.change")}</dt>
              <dd>{money(sale.change_due)}</dd>
            </div>
          )}
        </dl>
        <p className="print-thanks">{t("saleDetail.thanks")}</p>
      </article>

      {voiding && (
        <Modal title={t("saleDetail.voidTitle")} onClose={() => setVoiding(false)}>
          <p>{t("saleDetail.voidLead")}</p>
          <label className="full">
            <span className="field-label">{t("saleDetail.voidReason")}</span>
            <input className="input" value={reason} maxLength={255} onChange={(e) => setReason(e.target.value)} autoFocus />
          </label>
          <div className="modal-actions">
            <button className="btn ghost" type="button" onClick={() => setVoiding(false)}>
              {t("common.cancel")}
            </button>
            <button className="btn danger" type="button" disabled={busy} onClick={confirmVoid}>
              {t("saleDetail.void")}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
