import { useState, useCallback } from "react";
import { HashRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "./stores/auth";
import { useResizable } from "./hooks/useResizable";
import ActivityBar from "./components/ActivityBar";
import Sidebar from "./components/Sidebar";
import StatusBar from "./components/StatusBar";
import LockScreen from "./pages/LockScreen";
import HomePage from "./pages/Home";
import TaskDetailPage from "./pages/TaskDetail";
import ApprovalsPage from "./pages/Approvals";
import SettingsPage from "./pages/Settings";
import PromptsPage from "./pages/Prompts";
import MCPServersPage from "./pages/MCPServers";
import KeysPage from "./pages/Keys";
import TracePage from "./pages/Trace";
import ModelsPage from "./pages/Models";
import ReviewPage from "./pages/Review";

const queryClient = new QueryClient();

function Layout({ children }: { children: React.ReactNode }) {
  const { isUnlocked, hasPassword, lock } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { panelRef, onMouseDown } = useResizable({ initial: 260, min: 180, max: 420 });
  const location = useLocation();

  const toggleSidebar = useCallback(() => setSidebarOpen((o) => !o), []);

  // 代码审查页面有自己的左侧面板，不需要全局资源管理器
  const isReviewPage = location.pathname === "/review";

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
        <ActivityBar sidebarOpen={sidebarOpen} onToggleSidebar={toggleSidebar} />

        {!isReviewPage && (
          <>
            <div className={`sidebar-area${sidebarOpen ? "" : " sidebar-area--collapsed"}`} ref={panelRef}>
              <div className="sidebar-area__inner">
                <div className="sidebar-area__header">
                  <span className="sidebar-area__title">资源管理器</span>
                  <button
                    className="sidebar-area__collapse-btn"
                    onClick={toggleSidebar}
                    aria-label="切换侧边栏"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      {sidebarOpen ? (
                        <polyline points="15 18 9 12 15 6" />
                      ) : (
                        <polyline points="9 18 15 12 9 6" />
                      )}
                    </svg>
                  </button>
                </div>
                <Sidebar />
              </div>
            </div>

            {/* Resize handle */}
            {sidebarOpen && (
              <div className="workspace__resize-handle" onMouseDown={onMouseDown} />
            )}
          </>
        )}

        <main className="page-content">{children}</main>
      </div>

      {/* ── Status Bar ── */}
      <StatusBar />
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
          <Route path="/approvals" element={
            <Layout>
              <ProtectedRoute><ApprovalsPage /></ProtectedRoute>
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
