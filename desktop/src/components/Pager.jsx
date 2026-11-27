import { useState } from "react";
import { useI18n } from "../i18n/LanguageContext.jsx";

export const PAGE_SIZE = 25;

/** Page resets to 1 when the filter key changes, before the list is fetched. */
export function usePage(filterKey) {
  const [page, setPage] = useState(1);
  const [key, setKey] = useState(filterKey);
  if (key !== filterKey) {
    setKey(filterKey);
    if (page !== 1) setPage(1);
  }
  return [key === filterKey ? page : 1, setPage];
}

export default function Pager({ page, pageSize, total, onPage }) {
  const { t } = useI18n();
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <div className="pager">
      <span>{t("common.pageRange", { start, end, total })}</span>
      <div className="pager-actions">
        <button type="button" className="btn ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          {t("common.previous")}
        </button>
        <span>{t("common.pageOf", { page, pages })}</span>
        <button type="button" className="btn ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          {t("common.next")}
        </button>
      </div>
    </div>
  );
}
