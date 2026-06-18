import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPendingApprovals, getCostOverview, getModels } from "../api/client";

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

/* ── Models Panel ── */

function ModelsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
    refetchInterval: 60_000,
  });

  if (isLoading) return <p className="sidebar-empty">Loading…</p>;
  if (!data) return null;

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">Models</h3>
        <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
          {data.models.length} registered
        </span>
      </div>
      <div className="sidebar-panel__body">
        {data.models.length === 0 && (
          <p className="sidebar-empty">No models configured. Set API keys in .env.</p>
        )}
        {data.models.map((m: any) => (
          <div key={m.provider} className="sidebar-stat">
            <div>
              <div style={{ fontWeight: 600, color: "var(--text-heading)", fontSize: "0.82rem" }}>
                {m.provider}
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                {m.model}
              </div>
            </div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", textAlign: "right" }}>
              ${m.input_price_per_m.toFixed(2)} in
              <br />${m.output_price_per_m.toFixed(2)} out
            </div>
          </div>
        ))}

        <div className="sidebar-section-label">Node Assignments</div>
        {data.nodes.map((n: any) => (
          <div key={n.node} className="sidebar-task-item" style={{ justifyContent: "space-between", cursor: "default" }}>
            <span style={{ fontSize: "0.72rem", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
              {n.node}
            </span>
            <span
              style={{
                fontSize: "0.7rem",
                fontWeight: 600,
                color: n.model === "unknown" ? "var(--warning)" : "var(--accent)",
                fontFamily: "var(--mono)",
              }}
            >
              {n.provider}
              {n.overridden && " *"}
            </span>
          </div>
        ))}
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
    if (location.pathname.startsWith("/models")) return <ModelsPanel />;
    return <TasksPanel />;
  };

  return (
    <aside className="sidebar">
      {panel()}
    </aside>
  );
}
