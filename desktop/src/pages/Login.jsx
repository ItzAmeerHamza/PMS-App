import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { LanguageSwitcher, useI18n } from "../i18n/LanguageContext.jsx";
import { localizeError } from "../i18n/catalog";
import { useSession } from "../layout/SessionContext.jsx";

export default function Login() {
  const { staff, ready, login } = useSession();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [username, setUsername] = useState("manager");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!ready) return <div className="loading">{t("auth.checking")}</div>;
  if (staff) return <Navigate to="/" replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(localizeError(err.message, t));
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <LanguageSwitcher tone="light" />
        <div className="brand-mark">Rx</div>
        <h1>{t("auth.storeManager")}</h1>
        <p>{t("auth.lead")}</p>
        {error && <div className="error">{error}</div>}
        <label>
          <span>{t("auth.username")}</span>
          <input className="input" autoFocus value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          <span>{t("auth.password")}</span>
          <input
            className="input"
            type="password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? t("auth.signingIn") : t("auth.signIn")}
        </button>
        <p className="muted">{t("auth.demo")}</p>
      </form>
    </div>
  );
}
