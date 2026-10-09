import { Link, Navigate, Route, Routes } from "react-router-dom";
import CaregiverPage from "./pages/caregiver/CaregiverPage";
import PatientPage from "./pages/patient/PatientPage";
import DashboardPage from "./pages/dashboard/DashboardPage";

export default function App() {
  return (
    <>
      <nav style={{ display: "flex", gap: 16, padding: 16 }}>
        <Link to="/caregiver">Caregiver</Link>
        <Link to="/patient">Patient</Link>
        <Link to="/dashboard">Dashboard</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Navigate to="/patient" replace />} />
        <Route path="/caregiver" element={<CaregiverPage />} />
        <Route path="/patient" element={<PatientPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </>
  );
}