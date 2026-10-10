import { Navigate, Route, Routes } from "react-router-dom";
import PatientPage from "./pages/patient/PatientPage";
import CareLayout from "./pages/care/CareLayout";
import VoicesPage from "./pages/care/VoicesPage";
import MemoriesPage from "./pages/care/MemoriesPage";
import AlertsPage from "./pages/care/AlertsPage";
import ConversationsPage from "./pages/care/ConversationsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/patient" replace />} />
      <Route path="/patient" element={<PatientPage />} />
      <Route path="/care" element={<CareLayout />}>
        <Route index element={<Navigate to="voices" replace />} />
        <Route path="voices" element={<VoicesPage />} />
        <Route path="memories" element={<MemoriesPage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="alerts" element={<AlertsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/patient" replace />} />
    </Routes>
  );
}
