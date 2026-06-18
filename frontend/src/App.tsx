import { HashRouter, Routes, Route, Link, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "./stores/auth";
import LoginPage from "./pages/Login";
import HomePage from "./pages/Home";
import TaskDetailPage from "./pages/TaskDetail";
import ApprovalsPage from "./pages/Approvals";
import SettingsPage from "./pages/Settings";

const queryClient = new QueryClient();

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  const location = useLocation();
  const isActive = location.pathname === to;
  return (
    <Link to={to} className={isActive ? "active" : ""}>
      {children}
    </Link>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const { isLoggedIn, logout } = useAuthStore();

  return (
    <div className="page-shell">
      <header className="site-header">
        <Link to="/" className="site-header__brand">
          <span className="site-header__brand-dot" />
          mix-agent
        </Link>

        <nav className="site-header__nav">
          <NavLink to="/">Home</NavLink>
          <NavLink to="/approvals">Approvals</NavLink>
          <NavLink to="/settings">Cost</NavLink>
        </nav>

        <div className="site-header__actions">
          {isLoggedIn ? (
            <button onClick={logout} className="btn btn--secondary btn--sm">
              Logout
            </button>
          ) : (
            <Link to="/login" className="btn btn--secondary btn--sm">
              Login
            </Link>
          )}
        </div>
      </header>

      <main className="page-content">{children}</main>
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
