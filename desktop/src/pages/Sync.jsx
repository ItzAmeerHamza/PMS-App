import { useEffect, useState } from "react";
import { api } from "../api/client";
import { localizeError } from "../i18n/catalog";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { formatDateTime } from "../lib/format";

const BOOTSTRAP = {
  not_started: "sync.bootstrapNotStarted",
  running: "sync.bootstrapRunning",
  complete: "sync.bootstrapComplete",
};

export default function Sync() {
  const { t } = useI18n();
  const [status, setStatus] = useState(null);
  const [failures, setFailures] = useState([]);
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  const [cloudUrl, setCloudUrl] = useState("");
  const [replacing, setReplacing] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    const [next, detail] = await Promise.all([api.syncStatus(), api.syncDiagnostics()]);
    setStatus(next);
    setFailures(detail.failures || []);
  }

  useEffect(() => {
    let stop = false;
    async function refresh() {
      try {
        await load();
        if (!stop) setError("");
      } catch (err) {
        if (!stop) setError(err.message);
      }
    }
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  async function activate(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.activateSync(token.trim(), cloudUrl.trim());
      setToken("");
      setCloudUrl("");
      setReplacing(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function syncNow() {
    setBusy(true);
    setError("");
    try {
      const next = await api.syncNow();
      setStatus(next);
      const detail = await api.syncDiagnostics();
      setFailures(detail.failures || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!status) {
    return <div className="loading">{error ? localizeError(error, t) : t("sync.working")}</div>;
  }

  const showForm = !status.activated || replacing;

  return (
    <div>
      <div className="page-head">
        <div>
          <h2>{t("sync.title")}</h2>
          <p>{t("sync.lead")}</p>
        </div>
        {status.activated ? (
          <button className="btn" type="button" onClick={syncNow} disabled={busy}>
            {busy ? t("sync.working") : t("sync.now")}
          </button>
        ) : null}
      </div>
      {error ? <div className="error">{localizeError(error, t)}</div> : null}
      <div className="card-grid">
        <section className="panel">
          <h3>{t("sync.shopId")}</h3>
          <p className="sync-id">{status.shop_id}</p>
          <p className="muted">{t("sync.shopIdHelp")}</p>
        </section>
        <section className="panel">
          <h3>{t("sync.pending")}</h3>
          <p><strong>{status.pending}</strong></p>
          <p className="muted">{t("sync.failed")}: {status.failed}</p>
        </section>
        <section className="panel">
          <h3>{t("sync.lastSuccess")}</h3>
          <p>{status.last_success_at ? formatDateTime(status.last_success_at) : t("sync.never")}</p>
          <p className="muted">{t("sync.lastError")}: {status.last_error || t("sync.none")}</p>
        </section>
        <section className="panel">
          <h3>{t("sync.bootstrap")}</h3>
          <p>{t(BOOTSTRAP[status.bootstrap] || "sync.bootstrapNotStarted")}</p>
        </section>
      </div>
      {status.activated && !showForm ? (
        <p className="sync-note">
          {t("sync.activated")}{" "}
          <button className="btn ghost" type="button" onClick={() => setReplacing(true)}>
            {t("sync.replace")}
          </button>
        </p>
      ) : null}
      {showForm ? (
        <form className="panel sync-form" onSubmit={activate}>
          <label>
            <span>{t("sync.token")}</span>
            <input
              className="input"
              value={token}
              autoComplete="off"
              spellCheck="false"
              onChange={(event) => setToken(event.target.value)}
              required
            />
          </label>
          <p className="muted">{t("sync.tokenHint")}</p>
          <label>
            <span>{t("sync.cloudUrl")}</span>
            <input
              className="input"
              value={cloudUrl}
              autoComplete="off"
              spellCheck="false"
              placeholder="https://"
              onChange={(event) => setCloudUrl(event.target.value)}
            />
          </label>
          <p className="muted">{t("sync.cloudUrlHint")}</p>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? t("sync.saving") : t("sync.activate")}
          </button>
        </form>
      ) : null}
      <section className="panel">
        <h3>{t("sync.diagnostics")}</h3>
        {failures.length === 0 ? (
          <p className="muted">{t("sync.noFailures")}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("sync.sequence")}</th>
                <th>{t("sync.kind")}</th>
                <th>{t("sync.event")}</th>
                <th>{t("sync.code")}</th>
              </tr>
            </thead>
            <tbody>
              {failures.map((row) => (
                <tr key={row.event_id}>
                  <td>{row.sequence}</td>
                  <td>{row.entity_type}</td>
                  <td className="sync-id">{row.event_id}</td>
                  <td>{row.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
