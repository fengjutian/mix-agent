import { useState, useEffect, useRef } from "react";
import { listRoutes, traceInterface } from "../api/client";
import mermaid from "mermaid";

// Initialize mermaid with dark-friendly theme
mermaid.initialize({
  startOnLoad: false,
  theme: "base",
  themeVariables: {
    primaryColor: "#2d3748",
    primaryTextColor: "#e2e8f0",
    primaryBorderColor: "#4a5568",
    lineColor: "#718096",
    secondaryColor: "#1a202c",
    tertiaryColor: "#2a4365",
    background: "#1a1a2e",
    mainBkg: "#16213e",
    nodeBorder: "#4a5568",
    clusterBkg: "#0f3460",
    clusterBorder: "#3182ce",
    titleColor: "#e2e8f0",
    edgeLabelBackground: "#16213e",
  },
  flowchart: {
    htmlLabels: true,
    curve: "basis",
  },
});

interface RouteItem {
  method: string;
  path: string;
  full_path: string;
  handler: string;
  file_path: string;
  line_number: number;
  has_auth: boolean;
  tags: string[];
  summary: string;
}

interface TraceResult {
  ok: boolean;
  entry_point: string;
  route_info: any;
  call_chain: Array<{
    name: string;
    kind: string;
    file_path: string;
    line_number: number;
  }>;
  tables: Array<{
    table_name: string;
    class_name: string | null;
    operation: string;
    location: string;
    file_path: string;
    line_number: number;
  }>;
  swimlane: string;
  diagram_nodes: Array<{
    id: string;
    name: string;
    kind: string;
    file_path: string;
    line_number: number;
  }>;
  diagram_edges: Array<{ from: string; to: string }>;
  summary: string;
  all_routes: Array<{
    method: string;
    path: string;
    full_path: string;
    handler: string;
    file_path: string;
    line_number: number;
  }>;
  error: string;
}

const KIND_LABELS: Record<string, string> = {
  route: "🚏 Route",
  service: "⚙️ Service",
  dao: "📦 DAO",
  db: "🗄️ DB",
  function: "📁 Func",
};

const METHOD_COLORS: Record<string, string> = {
  GET: "var(--accent)",
  POST: "var(--success)",
  PUT: "var(--warning)",
  DELETE: "var(--danger)",
  PATCH: "var(--warning)",
};

export default function TracePage() {
  const [routes, setRoutes] = useState<RouteItem[]>([]);
  const [routesLoading, setRoutesLoading] = useState(true);
  const [selectedMethod, setSelectedMethod] = useState("GET");
  const [selectedPath, setSelectedPath] = useState("");
  const [customPath, setCustomPath] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TraceResult | null>(null);
  const [error, setError] = useState("");
  const mermaidRef = useRef<HTMLDivElement>(null);

  // Load route list on mount
  useEffect(() => {
    listRoutes()
      .then((data) => {
        if (data.ok) setRoutes(data.routes);
      })
      .catch(() => {})
      .finally(() => setRoutesLoading(false));
  }, []);

  // Render mermaid when swimlane changes
  useEffect(() => {
    if (result?.swimlane && mermaidRef.current) {
      const id = "swimlane-svg-" + Date.now();
      mermaidRef.current.innerHTML = "";
      const container = document.createElement("div");
      container.id = id;
      container.style.display = "flex";
      container.style.justifyContent = "center";
      mermaidRef.current.appendChild(container);

      mermaid
        .render(id, result.swimlane)
        .then(({ svg }) => {
          if (mermaidRef.current) {
            // Find the container we created
            const el = mermaidRef.current.querySelector(`#${id}`);
            if (el) {
              el.innerHTML = svg;
            }
          }
        })
        .catch((err) => {
          console.error("Mermaid render error:", err);
          if (mermaidRef.current) {
            mermaidRef.current.innerHTML =
              '<p style="color:var(--danger);padding:16px;">图表渲染失败，请检查 Mermaid 语法</p>';
          }
        });
    }
  }, [result?.swimlane]);

  // Group routes by method for the dropdown
  const routesByMethod: Record<string, RouteItem[]> = {};
  for (const r of routes) {
    if (!routesByMethod[r.method]) routesByMethod[r.method] = [];
    routesByMethod[r.method].push(r);
  }

  const handleSelectRoute = (method: string, fullPath: string) => {
    setSelectedMethod(method);
    setSelectedPath(fullPath);
    setCustomPath("");
  };

  const handleTrace = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setResult(null);

    const path = customPath || selectedPath;
    if (!path) {
      setError("请选择一个接口或手动输入路径");
      return;
    }

    setLoading(true);
    try {
      const data = await traceInterface(selectedMethod, path, ".");
      if (data.ok) {
        setResult(data);
      } else {
        setError(data.error || "分析失败");
      }
    } catch (err: any) {
      setError(err.message || "请求失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>🔍 接口调用链分析</h1>
      <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginBottom: 20 }}>
        选择一个 API 接口，分析其代码调用过程、涉及的数据库表，并生成泳道图
      </p>

      {/* ── Form ── */}
      <div className="card" style={{ marginBottom: 24 }}>
        <form onSubmit={handleTrace}>
          {/* Method select + dropdown */}
          <div className="form-row" style={{ alignItems: "flex-end" }}>
            <div className="form-group" style={{ flex: "0 0 100px" }}>
              <label className="form-label">方法</label>
              <select
                className="form-input"
                value={selectedMethod}
                onChange={(e) => {
                  setSelectedMethod(e.target.value);
                  setSelectedPath("");
                  setCustomPath("");
                }}
              >
                {["GET", "POST", "PUT", "DELETE", "PATCH"].map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">
                接口路径
                {routesLoading && (
                  <span style={{ fontWeight: 400, color: "var(--text-muted)", marginLeft: 8 }}>
                    加载路由列表中...
                  </span>
                )}
              </label>
              <select
                className="form-input"
                value={selectedPath}
                onChange={(e) => {
                  setSelectedPath(e.target.value);
                  setCustomPath("");
                }}
                style={{ fontFamily: "var(--mono)", fontSize: "0.82rem" }}
              >
                <option value="">-- 从列表中选择或手动输入 --</option>
                {(routesByMethod[selectedMethod] || []).map((r) => (
                  <option key={`${r.method} ${r.full_path}`} value={r.full_path}>
                    {r.full_path} {r.summary ? `— ${r.summary}` : ""} {r.has_auth ? "🔒" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              或手动输入路径
              <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>
                {" "}
                （如 /api/v1/admin/cost/overview）
              </span>
            </label>
            <input
              className="form-input"
              value={customPath}
              onChange={(e) => {
                setCustomPath(e.target.value);
                setSelectedPath("");
              }}
              placeholder="/api/v1/..."
              style={{ fontFamily: "var(--mono)" }}
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary btn--lg btn--block"
            disabled={loading}
            style={{ marginTop: 12 }}
          >
            {loading ? "⚡ 分析中..." : "🔍 分析调用链"}
          </button>
        </form>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="result-banner result-banner--error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* ── Results ── */}
      {result && result.ok && (
        <div>
          {/* Summary bar */}
          <div className="result-banner result-banner--success" style={{ marginBottom: 16 }}>
            <strong>{result.entry_point}</strong>
            <span style={{ marginLeft: 12, color: "var(--text-muted)" }}>
              {result.summary}
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 24 }}>
            {/* Swimlane diagram */}
            <div className="card" style={{ overflow: "auto" }}>
              <h3 style={{ marginTop: 0, fontSize: "1rem" }}>🏊 泳道图</h3>
              <div
                ref={mermaidRef}
                style={{
                  minHeight: 200,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  overflow: "auto",
                }}
              />
            </div>

            {/* Tables & chain info */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Route info card */}
              {result.route_info && (
                <div className="card">
                  <h3 style={{ marginTop: 0, fontSize: "0.95rem" }}>📌 路由信息</h3>
                  <div style={{ fontSize: "0.82rem", display: "grid", gap: 4 }}>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>Handler: </span>
                      <code style={{ fontFamily: "var(--mono)" }}>
                        {result.route_info.handler}
                      </code>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)" }}>File: </span>
                      <code style={{ fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
                        {result.route_info.file_path}:{result.route_info.line_number}
                      </code>
                    </div>
                    {result.route_info.has_auth && (
                      <div>
                        <span className="badge badge--warning">🔒 Auth</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Tables card */}
              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: "0.95rem" }}>
                  🗄️ 涉及的表
                  {result.tables.length > 0 && (
                    <span style={{ fontWeight: 400, color: "var(--text-muted)", marginLeft: 4 }}>
                      ({result.tables.length})
                    </span>
                  )}
                </h3>
                {result.tables.length === 0 ? (
                  <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                    未检测到数据库表引用
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {result.tables.map((t, i) => (
                      <div
                        key={i}
                        style={{
                          padding: "6px 10px",
                          background: "var(--bg-surface)",
                          borderRadius: 6,
                          fontSize: "0.82rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <strong style={{ fontFamily: "var(--mono)" }}>{t.table_name}</strong>
                          <span className={`badge ${t.operation === "SELECT" ? "badge--info" : t.operation === "INSERT" ? "badge--success" : t.operation === "UPDATE" ? "badge--warning" : t.operation === "DELETE" ? "badge--danger" : ""}`}>
                            {t.operation}
                          </span>
                        </div>
                        {t.class_name && (
                          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                            ORM: {t.class_name}
                          </div>
                        )}
                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                          {t.location} @ {t.file_path}:{t.line_number}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Call chain card */}
              <div className="card">
                <h3 style={{ marginTop: 0, fontSize: "0.95rem" }}>📋 调用链</h3>
                {result.call_chain.length === 0 ? (
                  <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                    无法追踪调用链
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {result.call_chain.map((node, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "4px 8px",
                          borderRadius: 4,
                          background: "var(--bg-surface)",
                          fontSize: "0.78rem",
                        }}
                      >
                        {i > 0 && (
                          <span style={{ color: "var(--text-muted)", marginRight: 2 }}>↓</span>
                        )}
                        <span style={{ fontSize: "0.75rem" }}>
                          {KIND_LABELS[node.kind] || "📁"}
                        </span>
                        <code style={{ fontFamily: "var(--mono)", flex: 1 }}>
                          {node.name}
                        </code>
                        {node.line_number > 0 && (
                          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                            :{node.line_number}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Mermaid source code - collapsible */}
          <details className="card" style={{ cursor: "pointer" }}>
            <summary style={{ fontWeight: 600, fontSize: "0.95rem", padding: 4 }}>
              📝 Mermaid 源码
            </summary>
            <pre
              style={{
                marginTop: 12,
                padding: 12,
                background: "var(--bg-surface)",
                borderRadius: 6,
                fontSize: "0.75rem",
                fontFamily: "var(--mono)",
                overflow: "auto",
                maxHeight: 300,
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {result.swimlane}
            </pre>
          </details>
        </div>
      )}

      {/* ── All routes quick reference ── */}
      {routes.length > 0 && !result && (
        <details className="card" style={{ cursor: "pointer", marginTop: 16 }}>
          <summary style={{ fontWeight: 600, fontSize: "0.9rem", padding: 4 }}>
            📡 所有已注册路由 ({routes.length})
          </summary>
          <div style={{ maxHeight: 400, overflow: "auto", marginTop: 8 }}>
            <table style={{ width: "100%", fontSize: "0.78rem", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)" }}>方法</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)" }}>路径</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)" }}>Handler</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--text-muted)" }}>Auth</th>
                </tr>
              </thead>
              <tbody>
                {routes.map((r, i) => (
                  <tr
                    key={i}
                    style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                    onClick={() => handleSelectRoute(r.method, r.full_path)}
                    className="hover-row"
                  >
                    <td style={{ padding: "4px 8px" }}>
                      <span
                        className="badge"
                        style={{
                          background: METHOD_COLORS[r.method] || "var(--text-muted)",
                          color: "#fff",
                          fontSize: "0.65rem",
                        }}
                      >
                        {r.method}
                      </span>
                    </td>
                    <td style={{ padding: "4px 8px", fontFamily: "var(--mono)", fontSize: "0.75rem" }}>
                      {r.full_path}
                    </td>
                    <td style={{ padding: "4px 8px", fontFamily: "var(--mono)", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      {r.handler}
                    </td>
                    <td style={{ padding: "4px 8px" }}>
                      {r.has_auth ? "🔒" : "🌐"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {/* Hover style for route table rows */}
      <style>{`
        .hover-row:hover {
          background: var(--bg-surface);
        }
      `}</style>
    </div>
  );
}
