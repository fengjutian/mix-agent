import { useState, useCallback } from "react";
import { HashRouter, Routes, Route, Link } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "./stores/auth";
import ActivityBar from "./components/ActivityBar";
import StatusBar from "./components/StatusBar";
import SettingsModal from "./components/SettingsModal";
import LockScreen from "./pages/LockScreen";
import HomePage from "./pages/Home";
import TaskDetailPage from "./pages/TaskDetail";
import SettingsPage from "./pages/Settings";
import PromptsPage from "./pages/Prompts";
import MCPServersPage from "./pages/MCPServers";
import KeysPage from "./pages/Keys";
import TracePage from "./pages/Trace";
import ModelsPage from "./pages/Models";
import ReviewPage from "./pages/Review";
import PRPage from "./pages/PR";

const queryClient = new QueryClient();


function Layout({ children }: { children: React.ReactNode }) {
  const { isUnlocked, hasPassword, lock } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const toggleSidebar = useCallback(() => setSidebarOpen((o) => !o), []);

  return (
    <div className="page-shell">
      {/* ── Slim top bar ── */}
      <header className="site-header">
        <Link to="/" className="site-header__brand">
          <span className="site-header__brand-dot" />
          mix-agent
        </Link>
        <div className="site-header__actions">
          {hasPassword && (
            <button onClick={lock} className="btn btn--secondary btn--sm">
              锁定屏幕
            </button>
          )}
        </div>
      </header>

      {/* ── Body: Activity Bar | Sidebar | Content ── */}
      <div className="workspace">
        <ActivityBar sidebarOpen={sidebarOpen} onToggleSidebar={toggleSidebar} onOpenSettings={() => setSettingsOpen(true)} />

        <main className="page-content">{children}</main>
      </div>

      {/* ── Status Bar ── */}
      <StatusBar />

      {/* ── Settings Modal ── */}
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isUnlocked = useAuthStore((s) => s.isUnlocked);
  if (!isUnlocked) return <LockScreen />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <Routes>
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
          <Route path="/models" element={
            <Layout>
              <ProtectedRoute><ModelsPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/prompts" element={
            <Layout>
              <ProtectedRoute><PromptsPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/mcp" element={
            <Layout>
              <ProtectedRoute><MCPServersPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/keys" element={
            <Layout>
              <ProtectedRoute><KeysPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/trace" element={
            <Layout>
              <ProtectedRoute><TracePage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/review" element={
            <Layout>
              <ProtectedRoute><ReviewPage /></ProtectedRoute>
            </Layout>
          } />
          <Route path="/pr" element={
            <Layout>
              <ProtectedRoute><PRPage /></ProtectedRoute>
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
