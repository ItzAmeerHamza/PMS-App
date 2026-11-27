import { NavLink, Outlet } from "react-router-dom";
import SyncIndicator from "../components/SyncIndicator.jsx";
import { LanguageSwitcher, useI18n } from "../i18n/LanguageContext.jsx";
import { PharmacyContext } from "./PharmacyContext";
import { useSession } from "./SessionContext.jsx";

export default function AppLayout() {
  const { staff, logout } = useSession();
  const { t } = useI18n();
  const pharmacy = staff?.pharmacy || null;
  const managerName = staff?.full_name === "Store manager" || !staff?.full_name ? t("auth.storeManager") : staff.full_name;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Rx</div>
          <div>
            <h1>PharmaCare</h1>
            <p>{t("nav.brand")}</p>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            {t("nav.dashboard")}
          </NavLink>
          <NavLink to="/billing">{t("nav.billing")}</NavLink>
          <NavLink to="/inventory">{t("nav.inventory")}</NavLink>
          <NavLink to="/prescriptions">{t("nav.prescriptions")}</NavLink>
          <NavLink to="/patients">{t("nav.patients")}</NavLink>
        </nav>
        <div className="sidebar-foot">
          <SyncIndicator />
          <LanguageSwitcher />
          <strong>{managerName}</strong>
          <span>{pharmacy?.name || t("nav.pharmacy")}</span>
          <button className="btn ghost sign-out" type="button" onClick={logout}>
            {t("auth.signOut")}
          </button>
        </div>
      </aside>
      <main className="main">
        <div className="main-tools">
          <nav className="top-nav">
            <NavLink to="/" end>
              {t("nav.dashboard")}
            </NavLink>
            <NavLink to="/billing">{t("nav.billing")}</NavLink>
            <NavLink to="/inventory">{t("nav.inventory")}</NavLink>
            <NavLink to="/prescriptions">{t("nav.prescriptions")}</NavLink>
            <NavLink to="/patients">{t("nav.patients")}</NavLink>
          </nav>
          <div className="top-nav-end">
            <SyncIndicator tone="light" />
            <LanguageSwitcher tone="light" />
            <button className="btn ghost" type="button" onClick={logout}>
              {t("auth.signOut")}
            </button>
          </div>
        </div>
        <PharmacyContext.Provider value={pharmacy}>
          <Outlet />
        </PharmacyContext.Provider>
      </main>
    </div>
  );
}
