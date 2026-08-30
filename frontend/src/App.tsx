import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { RequireAuth } from "./components/auth/RequireAuth";
import { ComingSoonPage } from "./pages/ComingSoonPage";
import { ExceptionsPage } from "./pages/ExceptionsPage";
import { InvestigationsListPage } from "./pages/InvestigationsListPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReconciliationPage } from "./pages/ReconciliationPage";
import { SignupPage } from "./pages/SignupPage";
import { EvidenceTab } from "./pages/investigation/EvidenceTab";
import { FinancialsTab } from "./pages/investigation/FinancialsTab";
import { HypothesesTab } from "./pages/investigation/HypothesesTab";
import { InvestigationWorkspaceLayout } from "./pages/investigation/InvestigationWorkspaceLayout";
import { SummaryTab } from "./pages/investigation/SummaryTab";

function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="signup" element={<SignupPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="reconciliation" element={<ReconciliationPage />} />
          <Route path="exceptions" element={<ExceptionsPage />} />
          <Route path="investigations" element={<InvestigationsListPage />} />
          <Route
            path="investigations/:id"
            element={<InvestigationWorkspaceLayout />}
          >
            <Route index element={<Navigate to="summary" replace />} />
            <Route path="summary" element={<SummaryTab />} />
            <Route path="evidence" element={<EvidenceTab />} />
            <Route path="hypotheses" element={<HypothesesTab />} />
            <Route path="financials" element={<FinancialsTab />} />
          </Route>
          <Route
            path="transactions"
            element={<ComingSoonPage title="Transactions" />}
          />
          <Route path="reports" element={<ComingSoonPage title="Reports" />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default App;
