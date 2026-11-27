import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useI18n } from "../i18n/LanguageContext.jsx";

const LABELS = {
  synced: "sync.synced",
  syncing: "sync.syncing",
  waiting: "sync.waiting",
  error: "sync.error",
  not_activated: "sync.notActivated",
};

export default function SyncIndicator({ tone = "dark" }) {
  const { t } = useI18n();
  const [status, setStatus] = useState(undefined);

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const next = await api.syncStatus();
        if (!stop) setStatus(next);
      } catch {
        if (!stop) setStatus(null);
      }
    }
    load();
    const timer = setInterval(load, 15000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  const indicator = status?.indicator;
  const label = indicator ? t(LABELS[indicator] || "sync.unavailable") : t("sync.unavailable");
  return (
    <Link className={`sync-pill ${tone} ${indicator || "unknown"}`} to="/sync">
      {label}
    </Link>
  );
}
