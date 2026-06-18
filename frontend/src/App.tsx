import { HashRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "./stores/auth";
import LoginPage from "./pages/Login";
import HomePage from "./pages/Home";
import TaskDetailPage from "./pages/TaskDetail";
import ApprovalsPage from "./pages/Approvals";
import SettingsPage from "./pages/Settings";

const queryClient = new QueryClient();

function Layout({ children }: { children: React.ReactNode }) {
  const { isLoggedIn, logout } = useAuthStore();

  return (
    <div>
      <nav style={{
        display: "flex", gap: 16, padding: "12px 24px",
        background: "#1a1a2e", color: "#fff", alignItems: "center"
      }}>
        <Link to="/" style={{ color: "#fff", fontWeight: "bold", fontSize: 18, textDecoration: "none" }}>
          mix-agent
        </Link>
        <Link to="/" style={{ color: "#ccc", textDecoration: "none" }}>Home</Link>
        <Link to="/approvals" style={{ color: "#ccc", textDecoration: "none" }}>Approvals</Link>
        <Link to="/settings" style={{ color: "#ccc", textDecoration: "none" }}>Cost</Link>
        <div style={{ flex: 1 }} />
        {isLoggedIn ? (
          <button onClick={logout} style={{ background: "transparent", color: "#fff", border: "1px solid #fff", padding: "4px 12px", borderRadius: 4 }}>
            Logout
          </button>
        ) : (
          <Link to="/login" style={{ color: "#fff" }}>Login</Link>
        )}
      </nav>
      <main>{children}</main>
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={
            <Layout>
              <ProtectedRoute><HomePage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/tasks/:id" element={
            <Layout>
              <ProtectedRoute><TaskDetailPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/approvals" element={
            <Layout>
              <ProtectedRoute><ApprovalsPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/settings" element={
            <Layout>
              <ProtectedRoute><SettingsPage /></ProtectedRoute>
            </Layout>
          } />
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  );
}
