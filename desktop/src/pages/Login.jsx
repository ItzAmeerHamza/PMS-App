import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { LanguageSwitcher, useI18n } from "../i18n/LanguageContext.jsx";
import { localizeError } from "../i18n/catalog";
import { useSession } from "../layout/SessionContext.jsx";

const MIN_PASSWORD = 8;

const emptySetup = {
  pharmacy_name: "",
  pharmacy_address: "",
  pharmacy_phone: "",
  license_number: "",
  full_name: "",
  username: "",
  password: "",
  confirm: "",
};

function SetupForm({ status, onDone }) {
  const { setup } = useSession();
  const { t } = useI18n();
  const [form, setForm] = useState(emptySetup);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const needsPharmacy = !status.has_pharmacy;

  function field(name) {
    return { value: form[name], onChange: (event) => setForm({ ...form, [name]: event.target.value }) };
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (form.password.length < MIN_PASSWORD) {
      setError(t("auth.tooShort"));
      return;
    }
    if (form.password !== form.confirm) {
      setError(t("auth.mismatch"));
      return;
    }
    setBusy(true);
    try {
      const { confirm, ...body } = form;
      await setup(needsPharmacy ? body : { ...body, pharmacy_name: null, pharmacy_address: null, pharmacy_phone: null, license_number: null });
      onDone();
    } catch (err) {
      setError(localizeError(err.message, t));
      setBusy(false);
    }
  }

  return (
    <form className="login-card setup-card" onSubmit={submit}>
      <LanguageSwitcher tone="light" />
      <div className="brand-mark">Rx</div>
      <h1>{t("auth.setupTitle")}</h1>
      <p>{needsPharmacy ? t("auth.setupLead") : t("auth.setupLeadExisting", { name: status.pharmacy_name })}</p>
      {error && <div className="error">{error}</div>}
      {needsPharmacy && (
        <fieldset className="setup-section">
          <legend>{t("auth.pharmacySection")}</legend>
          <label>
            <span>{t("auth.pharmacyName")}</span>
            <input className="input" required autoFocus maxLength={255} {...field("pharmacy_name")} />
          </label>
          <label>
            <span>{t("auth.pharmacyAddress")}</span>
            <input className="input" maxLength={500} {...field("pharmacy_address")} />
          </label>
          <div className="form-grid">
            <label>
              <span>{t("auth.pharmacyPhone")}</span>
              <input className="input" maxLength={20} {...field("pharmacy_phone")} />
            </label>
            <label>
              <span>{t("auth.license")}</span>
              <input className="input" maxLength={100} {...field("license_number")} />
            </label>
          </div>
        </fieldset>
      )}
      <fieldset className="setup-section">
        <legend>{t("auth.managerSection")}</legend>
        <label>
          <span>{t("auth.fullName")}</span>
          <input className="input" maxLength={255} autoFocus={!needsPharmacy} {...field("full_name")} />
        </label>
        <label>
          <span>{t("auth.username")}</span>
          <input className="input" required maxLength={64} autoComplete="username" {...field("username")} />
        </label>
        <label>
          <span>{t("auth.password")}</span>
          <input className="input" type="password" required autoComplete="new-password" {...field("password")} />
        </label>
        <label>
          <span>{t("auth.confirmPassword")}</span>
          <input className="input" type="password" required autoComplete="new-password" {...field("confirm")} />
        </label>
        <p className="muted">{t("auth.passwordHint")}</p>
      </fieldset>
      <button className="btn" type="submit" disabled={busy}>
        {busy ? t("auth.creating") : t("auth.createAccount")}
      </button>
    </form>
  );
}

export default function Login() {
  const { staff, ready, login } = useSession();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [setupStatus, setSetupStatus] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!ready || staff) return;
    api
      .setupStatus()
      .then(setSetupStatus)
      .catch((err) => {
        setSetupStatus({ needs_setup: false });
        setError(localizeError(err.message, t));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, staff]);

  if (!ready || (!staff && !setupStatus)) return <div className="loading">{t("auth.checking")}</div>;
  if (staff) return <Navigate to="/" replace />;

  if (setupStatus.needs_setup) {
    return (
      <div className="login-screen">
        <SetupForm status={setupStatus} onDone={() => navigate("/")} />
      </div>
    );
  }

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
          <input
            className="input"
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label>
          <span>{t("auth.password")}</span>
          <input
            className="input"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? t("auth.signingIn") : t("auth.signIn")}
        </button>
      </form>
    </div>
  );
}
