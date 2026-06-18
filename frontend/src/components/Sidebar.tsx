import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPendingApprovals, getCostOverview } from "../api/client";

/* ── Tasks Panel ── */

function TasksPanel() {
  const navigate = useNavigate();

  // Pull recent task IDs from localStorage
  const recentIds: string[] = (() => {
    try {
      return JSON.parse(localStorage.getItem("recent_task_ids") || "[]");
    } catch {
      return [];
    }
  })();

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">Tasks</h3>
      </div>
      <div className="sidebar-panel__body">
        <button
          className="btn btn--primary btn--sm btn--block"
          onClick={() => {
            // Scroll to the form on home page
            const form = document.querySelector(".card");
            form?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          + New Audit
        </button>

        {recentIds.length > 0 && (
          <>
            <div className="sidebar-section-label">Recent</div>
            {recentIds.slice(0, 12).map((id) => (
              <button
                key={id}
                className="sidebar-task-item"
                onClick={() => navigate(`/tasks/${id}`)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span className="sidebar-task-item__id">{id.slice(0, 8)}…</span>
              </button>
            ))}
          </>
        )}

        {recentIds.length === 0 && (
          <p className="sidebar-empty">No recent tasks. Create a new audit to get started.</p>
        )}
      </div>
    </div>
  );
}

/* ── Approvals Panel ── */

function ApprovalsPanel() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["pending-approvals"],
    queryFn: getPendingApprovals,
    refetchInterval: 15_000,
  });

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">Pending Approvals</h3>
        {data && <span className="badge badge--warning">{data.total}</span>}
      </div>
      <div className="sidebar-panel__body">
        {isLoading && <p className="sidebar-empty">Loading…</p>}
        {!isLoading && data && data.items.length === 0 && (
          <p className="sidebar-empty">Nothing pending.</p>
        )}
        {data?.items.map((item: any) => (
          <button
            key={item.task_id}
            className="sidebar-task-item"
            onClick={() => navigate(`/tasks/${item.task_id}`)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span className="sidebar-task-item__id">{item.node_name || item.task_id?.slice(0, 12)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Cost Panel ── */

function CostPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["cost-overview"],
    queryFn: getCostOverview,
    refetchInterval: 60_000,
  });

  if (isLoading) return <p className="sidebar-empty">Loading…</p>;
  if (!data) return null;

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">Cost Overview</h3>
      </div>
      <div className="sidebar-panel__body">
        {data.total_tokens !== undefined && (
          <div className="sidebar-stat">
            <span className="sidebar-stat__label">Total Tokens</span>
            <span className="sidebar-stat__value">{Number(data.total_tokens).toLocaleString()}</span>
          </div>
        )}
        {data.total_cost !== undefined && (
          <div className="sidebar-stat">
            <span className="sidebar-stat__label">Est. Cost</span>
            <span className="sidebar-stat__value">${Number(data.total_cost).toFixed(4)}</span>
          </div>
        )}
        {data.task_count !== undefined && (
          <div className="sidebar-stat">
            <span className="sidebar-stat__label">Total Tasks</span>
            <span className="sidebar-stat__value">{data.task_count}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Sidebar Root ── */

export default function Sidebar() {
  const location = useLocation();

  const panel = () => {
    if (location.pathname === "/") return <TasksPanel />;
    if (location.pathname.startsWith("/approvals")) return <ApprovalsPanel />;
    if (location.pathname.startsWith("/settings")) return <CostPanel />;
    if (location.pathname.startsWith("/tasks/")) return <TasksPanel />;
    return <TasksPanel />;
  };

  return (
    <aside className="sidebar">
      {panel()}
    </aside>
  );
}
