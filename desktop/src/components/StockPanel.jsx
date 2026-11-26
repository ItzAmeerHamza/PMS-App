import { useEffect, useState } from "react";
import { api } from "../api/client";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDate, formatDateTime, fromInputDate, startOfDay } from "../lib/format";
import Modal from "./Modal";

export function isExpired(expiryDate) {
  if (!expiryDate) return false;
  return fromInputDate(String(expiryDate).slice(0, 10)) < startOfDay();
}

function sourceText(movement, t) {
  if (movement.movement_type === "adjustment") return movement.reason || "—";
  if (movement.source_type === "sale") return t("inv.sourceSale", { id: movement.source_id });
  if (movement.source_type === "prescription") return t("inv.sourcePrescription", { id: movement.source_id });
  if (movement.source_type === "import") return t("inv.sourceImport");
  if (movement.source_type === "seed") return t("inv.sourceSeed");
  if (movement.source_type === "migration") return t("inv.sourceMigration");
  return movement.reason || "—";
}

/** Batches, manual adjustment, and the movement ledger for one medicine. */
export default function StockPanel({ medicineId, onClose, onChanged }) {
  const { t, named } = useI18n();
  const [medicine, setMedicine] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [adjusting, setAdjusting] = useState(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const [item, moves] = await Promise.all([api.medicine(medicineId), api.movements(medicineId)]);
      setMedicine(item);
      setHistory(moves);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [medicineId]);

  async function saveAdjustment(event) {
    event.preventDefault();
    const quantity = Number(adjusting.quantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setError(t("inv.adjustQtyInvalid"));
      return;
    }
    if (!adjusting.reason.trim()) {
      setError(t("inv.reasonRequired"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      const delta = adjusting.direction === "decrease" ? -quantity : quantity;
      await api.adjustBatch(adjusting.batch.id, delta, adjusting.reason.trim());
      setAdjusting(null);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const batches = medicine ? [...medicine.batches].sort((a, b) => String(a.expiry_date).localeCompare(String(b.expiry_date))) : [];
  const newestFirst = [...history].reverse();

  return (
    <Modal wide title={medicine ? t("inv.stockTitle", { name: medicine.name }) : t("inv.stock")} onClose={onClose}>
      {error && <div className="error">{localizeError(error, t)}</div>}
      {!medicine ? (
        <p className="empty">{t("inv.loading")}</p>
      ) : (
        <>
          <p className="muted">
            {t("inv.stockSummary", { onHand: medicine.quantity_on_hand, sellable: medicine.sellable_quantity })}
          </p>

          <h4 className="stock-heading">{t("inv.batches")}</h4>
          {batches.length === 0 ? (
            <p className="empty">{t("inv.noBatches")}</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t("dash.batch")}</th>
                  <th>{t("dash.expiry")}</th>
                  <th className="num">{t("dash.qty")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
                  <tr key={batch.id}>
                    <td>{batch.batch_number}</td>
                    <td>
                      {formatDate(batch.expiry_date)}
                      {isExpired(batch.expiry_date) && <span className="badge danger tag">{t("status.expired")}</span>}
                    </td>
                    <td className="num">{batch.quantity}</td>
                    <td className="qty-cell">
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => {
                          setError("");
                          setAdjusting({ batch, direction: "decrease", quantity: "", reason: "" });
                        }}
                      >
                        {t("inv.adjust")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {adjusting && (
            <form className="adjust-form" onSubmit={saveAdjustment}>
              <h4 className="stock-heading">{t("inv.adjustTitle", { batch: adjusting.batch.batch_number, qty: adjusting.batch.quantity })}</h4>
              <div className="segmented" role="group">
                {["increase", "decrease"].map((direction) => (
                  <button
                    key={direction}
                    type="button"
                    className={adjusting.direction === direction ? "active" : ""}
                    onClick={() => setAdjusting({ ...adjusting, direction })}
                  >
                    {t(`inv.${direction}`)}
                  </button>
                ))}
              </div>
              <div className="form-grid">
                <label>
                  <span>{t("inv.adjustQty")}</span>
                  <input
                    className="input"
                    inputMode="numeric"
                    required
                    autoFocus
                    value={adjusting.quantity}
                    onChange={(e) => /^\d*$/.test(e.target.value) && setAdjusting({ ...adjusting, quantity: e.target.value })}
                  />
                </label>
                <label>
                  <span>{t("inv.reason")}</span>
                  <input
                    className="input"
                    required
                    maxLength={255}
                    placeholder={t("inv.reasonPlaceholder")}
                    value={adjusting.reason}
                    onChange={(e) => setAdjusting({ ...adjusting, reason: e.target.value })}
                  />
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn ghost" onClick={() => setAdjusting(null)}>
                  {t("common.cancel")}
                </button>
                <button className="btn" type="submit" disabled={saving}>
                  {t("inv.saveAdjust")}
                </button>
              </div>
            </form>
          )}

          <h4 className="stock-heading">{t("inv.history")}</h4>
          {newestFirst.length === 0 ? (
            <p className="empty">{t("inv.noHistory")}</p>
          ) : (
            <div className="history-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("inv.when")}</th>
                    <th>{t("inv.movement")}</th>
                    <th>{t("dash.batch")}</th>
                    <th className="num">{t("inv.change")}</th>
                    <th className="num">{t("inv.after")}</th>
                    <th>{t("inv.details")}</th>
                  </tr>
                </thead>
                <tbody>
                  {newestFirst.map((move) => (
                    <tr key={move.id}>
                      <td>
                        {formatDateTime(move.created_at)}
                        {move.staff_name && <div className="muted">{move.staff_name}</div>}
                      </td>
                      <td>{named("move", move.movement_type)}</td>
                      <td>{move.batch_number}</td>
                      <td className={`num ${move.quantity_delta < 0 ? "delta-out" : "delta-in"}`}>
                        {move.quantity_delta > 0 ? `+${move.quantity_delta}` : move.quantity_delta}
                      </td>
                      <td className="num">{move.quantity_after}</td>
                      <td>{sourceText(move, t)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="modal-actions">
            <button type="button" className="btn ghost" onClick={onClose}>
              {t("inv.close")}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
