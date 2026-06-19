import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCostOverview, getModels, getKeys, getPrompts, getMCPServers } from "../api/client";

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
        <h3 className="sidebar-panel__title">任务</h3>
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
          + 新建审计
        </button>

        {recentIds.length > 0 && (
          <>
            <div className="sidebar-section-label">最近</div>
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
          <p className="sidebar-empty">暂无最近任务，创建一个新审计开始吧</p>
        )}
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

  if (isLoading) return <p className="sidebar-empty">加载中…</p>;
  if (!data) return null;

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">成本概览</h3>
      </div>
      <div className="sidebar-panel__body">
        {data.total_tokens !== undefined && (
          <div className="sidebar-stat">
            <span className="sidebar-stat__label">Token 总量</span>
            <span className="sidebar-stat__value">{Number(data.total_tokens).toLocaleString()}</span>
          </div>
        )}
        {data.total_cost !== undefined && (
          <div className="sidebar-stat">
            <span className="sidebar-stat__label">预估成本</span>
            <span className="sidebar-stat__value">${Number(data.total_cost).toFixed(4)}</span>
          </div>
        )}
        {data.task_count !== undefined && (
          <div className="sidebar-stat">
            <span className="sidebar-stat__label">任务总数</span>
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
        <h3 className="sidebar-panel__title">模型</h3>
        <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
          {data.models.length} 已注册
        </span>
      </div>
      <div className="sidebar-panel__body">
        {data.models.length === 0 && (
          <p className="sidebar-empty">未配置模型，请在密钥页面添加 API Key</p>
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
              ${m.input_price_per_m.toFixed(2)} 输入
              <br />${m.output_price_per_m.toFixed(2)} 输出
            </div>
          </div>
        ))}

        <div className="sidebar-section-label">节点分配</div>
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

/* ── Keys Panel ── */

function KeysPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["keys"],
    queryFn: getKeys,
    refetchInterval: 60_000,
  });

  if (isLoading) return <p className="sidebar-empty">Loading…</p>;
  if (!data) return null;

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">API Keys</h3>
        <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
          {data.keys.filter((k: any) => k.has_key).length} configured
        </span>
      </div>
      <div className="sidebar-panel__body">
        {data.keys.length === 0 && (
          <p className="sidebar-empty">No keys configured. Add one to enable a provider.</p>
        )}
        {data.keys.map((k: any) => (
          <div key={k.provider} className="sidebar-task-item" style={{ justifyContent: "space-between", cursor: "default" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-heading)" }}>
              {k.provider}
            </span>
            <span
              className={`badge ${k.has_key ? "badge--success" : "badge--warning"}`}
              style={{ fontSize: "0.6rem" }}
            >
              {k.has_key ? "set" : "empty"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Prompts Panel ── */

function PromptsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["prompts"],
    queryFn: getPrompts,
    refetchInterval: 60_000,
  });

  if (isLoading) return <p className="sidebar-empty">Loading…</p>;
  if (!data) return null;

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">Prompts</h3>
        <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
          {data.prompts.filter((p) => p.overridden).length} edited
        </span>
      </div>
      <div className="sidebar-panel__body">
        {data.prompts.map((p) => (
          <div key={p.agent} className="sidebar-task-item" style={{ justifyContent: "space-between", cursor: "default" }}>
            <span style={{ fontSize: "0.72rem", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
              {p.agent}
            </span>
            {p.overridden && (
              <span className="badge badge--warning" style={{ fontSize: "0.6rem" }}>edited</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── MCP Servers Panel ── */

function MCPServersPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: getMCPServers,
    refetchInterval: 30_000,
  });

  if (isLoading) return <p className="sidebar-empty">加载中…</p>;
  if (!data) return null;

  return (
    <div className="sidebar-panel">
      <div className="sidebar-panel__header">
        <h3 className="sidebar-panel__title">MCP 服务器</h3>
        <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
          {data.servers.filter((s) => s.enabled).length}/{data.servers.length} 已激活
        </span>
      </div>
      <div className="sidebar-panel__body">
        {data.servers.length === 0 && (
          <p className="sidebar-empty">未配置 MCP 服务器。</p>
        )}
        {data.servers.map((s) => (
          <div key={s.name} className="sidebar-task-item" style={{ justifyContent: "space-between", cursor: "default" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-heading)" }}>
              {s.name}
            </span>
            <span
              className={`badge ${s.enabled ? "badge--success" : "badge--warning"}`}
              style={{ fontSize: "0.6rem" }}
            >
              {s.transport}
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
    if (location.pathname.startsWith("/settings")) return <CostPanel />;
    if (location.pathname.startsWith("/tasks/")) return <TasksPanel />;
    if (location.pathname.startsWith("/models")) return <ModelsPanel />;
    if (location.pathname.startsWith("/keys")) return <KeysPanel />;
    if (location.pathname.startsWith("/prompts")) return <PromptsPanel />;
    if (location.pathname.startsWith("/mcp")) return <MCPServersPanel />;
    if (location.pathname.startsWith("/trace")) return <TasksPanel />;
    return <TasksPanel />;
  };

  return (
    <aside className="sidebar">
      {panel()}
    </aside>
  );
}
