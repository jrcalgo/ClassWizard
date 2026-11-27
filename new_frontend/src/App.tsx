import { Route, Routes } from "react-router-dom";

import { AccountPage, ActivityPage, HistoryPage } from "@/features/account/AccountPages";
import { ForgotPage, LoginPage, ResetPage, SignupPage, VerifyPage } from "@/features/auth/AuthPages";
import { AppShell } from "@/layout/AppShell";
import { useSystemThemeListener } from "@/theme/theme";

export default function App() {
  useSystemThemeListener();
  return (
    <Routes>
      {/* The planner stays mounted under every route, so opening sign-in or the
          account pages never loses the current plan. */}
      <Route path="/" element={<AppShell />}>
        <Route index element={null} />
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route path="forgot" element={<ForgotPage />} />
        <Route path="reset" element={<ResetPage />} />
        <Route path="verify" element={<VerifyPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="account/history" element={<HistoryPage />} />
        <Route path="account/activity" element={<ActivityPage />} />
        <Route path="*" element={null} />
      </Route>
    </Routes>
  );
}
