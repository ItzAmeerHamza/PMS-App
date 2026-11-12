import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useI18n } from "./i18n/LanguageContext.jsx";
import AppLayout from "./layout/AppLayout";
import { SessionProvider, useSession } from "./layout/SessionContext.jsx";
import Dashboard from "./pages/Dashboard";
import Inventory from "./pages/Inventory";
import Login from "./pages/Login";
import Patients from "./pages/Patients";
import PatientDetail from "./pages/PatientDetail";
import Prescriptions from "./pages/Prescriptions";
import PrescriptionForm from "./pages/PrescriptionForm";
import PrescriptionDetail from "./pages/PrescriptionDetail";

function RequireAuth() {
  const { staff, ready } = useSession();
  const { t } = useI18n();
  if (!ready) return <div className="loading">{t("auth.checking")}</div>;
  if (!staff) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/patients/:id" element={<PatientDetail />} />
            <Route path="/prescriptions" element={<Prescriptions />} />
            <Route path="/prescriptions/new" element={<PrescriptionForm />} />
            <Route path="/prescriptions/:id" element={<PrescriptionDetail />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </SessionProvider>
  );
}
