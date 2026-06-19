import { useState, useCallback, useEffect } from "react";
import { sendProxyRequest, type ProxyResponseBody } from "../api/client";

// ── Helpers ──

const HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"];
const METHODS_WITH_BODY = ["POST", "PUT", "PATCH", "DELETE"];
const CONTENT_TYPES = [
  "application/json",
  "application/x-www-form-urlencoded",
  "text/plain",
  "text/html",
  "application/xml",
];

const METHOD_COLORS: Record<string, string> = {
  GET: "var(--success)",
  POST: "var(--warning)",
  PUT: "var(--info)",
  DELETE: "var(--danger)",
  PATCH: "var(--warning)",
  HEAD: "var(--text-muted)",
  OPTIONS: "var(--text-muted)",
};

function formatTiming(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatBytes(text: string): string {
  const bytes = new Blob([text]).size;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function tryPrettifyJSON(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return raw;
  }
}

// ── Persisted History ──

interface HistoryEntry {
  id: string;
  method: string;
  url: string;
  headers: Record<string, string>;
  query_params: Record<string, string>;
  body: string | null;
  content_type: string | null;
  timestamp: number;
}

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem("api-client-history");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries: HistoryEntry[]) {
  try {
    localStorage.setItem("api-client-history", JSON.stringify(entries.slice(0, 50)));
  } catch {
    // storage full — ignore
  }
}

// ── Key-Value Editor ──

interface KVPair {
  key: string;
  value: string;
  enabled: boolean;
}

function KeyValueEditor({
  pairs,
  onChange,
  showEnableToggle,
}: {
  pairs: KVPair[];
  onChange: (pairs: KVPair[]) => void;
  showEnableToggle: boolean;
}) {
  const update = (i: number, p: Partial<KVPair>) => {
    const next = [...pairs];
    next[i] = { ...next[i], ...p };
    onChange(next);
  };

  const remove = (i: number) => {
    onChange(pairs.filter((_, idx) => idx !== i));
  };

  const add = () => {
    onChange([...pairs, { key: "", value: "", enabled: true }]);
  };

  return (
    <div>
      {pairs.map((p, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            gap: 6,
            marginBottom: 4,
            alignItems: "center",
          }}
        >
          {showEnableToggle && (
            <input
              type="checkbox"
              checked={p.enabled}
              onChange={(e) => update(i, { enabled: e.target.checked })}
              style={{ flexShrink: 0, accentColor: "var(--accent)" }}
            />
          )}
          <input
            className="form-input"
            value={p.key}
            onChange={(e) => update(i, { key: e.target.value })}
            placeholder="Key"
            style={{ flex: "1 1 35%", padding: "4px 8px", fontSize: "0.78rem", fontFamily: "var(--mono)" }}
          />
          <input
            className="form-input"
            value={p.value}
            onChange={(e) => update(i, { value: e.target.value })}
            placeholder="Value"
            style={{ flex: "1 1 65%", padding: "4px 8px", fontSize: "0.78rem", fontFamily: "var(--mono)" }}
          />
          <button
            className="btn btn--ghost btn--sm"
            onClick={() => remove(i)}
            style={{ padding: "2px 6px", fontSize: "0.7rem", flexShrink: 0 }}
            title="移除"
          >
            ✕
          </button>
        </div>
      ))}
      <button
        className="btn btn--ghost btn--sm"
        onClick={add}
        style={{ marginTop: 4, fontSize: "0.75rem" }}
      >
        + 添加
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════

export default function ApiClientPage() {
  // ── Request state ──
  const [method, setMethod] = useState("GET");
  const [url, setUrl] = useState("");
  const [headers, setHeaders] = useState<KVPair[]>([]);
  const [queryParams, setQueryParams] = useState<KVPair[]>([]);
  const [body, setBody] = useState("");
  const [contentType, setContentType] = useState("application/json");
  const [loading, setLoading] = useState(false);

  // ── Response state ──
  const [response, setResponse] = useState<ProxyResponseBody | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"headers" | "query" | "body">("headers");
  const [responseTab, setResponseTab] = useState<"body" | "headers">("body");

  // ── History ──
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);
  const [showHistory, setShowHistory] = useState(false);

  // ── Send request ──
  const handleSend = useCallback(async () => {
    if (!url.trim()) {
      setError("请输入 URL");
      return;
    }

    setError("");
    setResponse(null);
    setLoading(true);

    try {
      // Build headers map from enabled pairs
      const headersMap: Record<string, string> = {};
      for (const h of headers) {
        if (h.enabled && h.key.trim()) {
          headersMap[h.key.trim()] = h.value;
        }
      }

      // Build query params map from enabled pairs
      const queryMap: Record<string, string> = {};
      for (const q of queryParams) {
        if (q.enabled && q.key.trim()) {
          queryMap[q.key.trim()] = q.value;
        }
      }

      const res = await sendProxyRequest({
        method,
        url: url.trim(),
        headers: headersMap,
        query_params: queryMap,
        body: METHODS_WITH_BODY.includes(method) && body ? body : null,
        content_type: METHODS_WITH_BODY.includes(method) && body ? contentType : null,
        timeout_seconds: 30,
      });

      setResponse(res);

      // Save to history
      const entry: HistoryEntry = {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        method,
        url: url.trim(),
        headers: headersMap,
        query_params: queryMap,
        body: METHODS_WITH_BODY.includes(method) ? body : null,
        content_type: METHODS_WITH_BODY.includes(method) ? contentType : null,
        timestamp: Date.now(),
      };
      const updated = [entry, ...history].slice(0, 50);
      setHistory(updated);
      saveHistory(updated);
    } catch (err: any) {
      setError(err.message || "请求失败");
    } finally {
      setLoading(false);
    }
  }, [method, url, headers, queryParams, body, contentType, history]);

  // ── Clear ──
  const handleClear = () => {
    setResponse(null);
    setError("");
  };

  // ── Load from history ──
  const loadFromHistory = (entry: HistoryEntry) => {
    setMethod(entry.method);
    setUrl(entry.url);
    setHeaders(
      Object.entries(entry.headers).map(([k, v]) => ({ key: k, value: v, enabled: true }))
    );
    setQueryParams(
      Object.entries(entry.query_params).map(([k, v]) => ({ key: k, value: v, enabled: true }))
    );
    setBody(entry.body ?? "");
    if (entry.content_type) setContentType(entry.content_type);
    setShowHistory(false);
    setResponse(null);
    setError("");
  };

  // ── Keyboard shortcut Ctrl+Enter to send ──
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        handleSend();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleSend]);

  const hasBody = METHODS_WITH_BODY.includes(method);
  const responseStatusCode = response?.status ?? 0;
  const statusBadgeColor =
    responseStatusCode >= 200 && responseStatusCode < 300
      ? "var(--success)"
      : responseStatusCode >= 300 && responseStatusCode < 400
      ? "var(--info)"
      : responseStatusCode >= 400 && responseStatusCode < 500
      ? "var(--warning)"
      : responseStatusCode >= 500
      ? "var(--danger)"
      : "var(--text-muted)";

  return (
    <div>
      <h1>📡 API 客户端</h1>
      <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginBottom: 20 }}>
        发送 HTTP 请求并查看响应 — 类似 Postman 的接口调试工具。按 Ctrl+Enter 快速发送。
      </p>

      {/* ── Request Builder ── */}
      <div className="card" style={{ marginBottom: 20 }}>
        {/* Method + URL + Send row */}
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <select
            className="form-input"
            value={method}
            onChange={(e) => {
              setMethod(e.target.value);
              if (!METHODS_WITH_BODY.includes(e.target.value)) {
                setActiveTab("headers");
              }
            }}
            style={{
              flex: "0 0 110px",
              fontWeight: 650,
              color: METHOD_COLORS[method] || "var(--text-heading)",
              fontFamily: "var(--mono)",
            }}
          >
            {HTTP_METHODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>

          <input
            className="form-input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.example.com/endpoint"
            style={{ flex: 1, fontFamily: "var(--mono)", fontSize: "0.85rem" }}
          />

          <button
            className="btn btn--primary"
            onClick={handleSend}
            disabled={loading}
            style={{ flex: "0 0 auto", minWidth: 100 }}
          >
            {loading ? "⏳ 发送中..." : "▶ 发送"}
          </button>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--border)", marginBottom: 10 }}>
          {(["headers", "query", "body"] as const).map((tab) => {
            if (tab === "body" && !hasBody) return null;
            const labels: Record<string, string> = { headers: "Headers", query: "Query Params", body: "Body" };
            const counts: Record<string, number> = {
              headers: headers.filter((h) => h.enabled && h.key.trim()).length,
              query: queryParams.filter((q) => q.enabled && q.key.trim()).length,
              body: body.trim() ? 1 : 0,
            };
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: "6px 14px",
                  background: "transparent",
                  border: "none",
                  borderBottom: activeTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                  color: activeTab === tab ? "var(--text-heading)" : "var(--text-muted)",
                  fontWeight: activeTab === tab ? 600 : 400,
                  cursor: "pointer",
                  fontSize: "0.82rem",
                  fontFamily: "var(--sans)",
                  transition: "color 140ms var(--ease-out), border-color 140ms var(--ease-out)",
                }}
              >
                {labels[tab]}
                {counts[tab] > 0 && (
                  <span style={{ marginLeft: 6, fontSize: "0.7rem", opacity: 0.7 }}>
                    ({counts[tab]})
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <div style={{ minHeight: 80 }}>
          {activeTab === "headers" && (
            <KeyValueEditor
              pairs={headers.length > 0 ? headers : [{ key: "", value: "", enabled: true }]}
              onChange={setHeaders}
              showEnableToggle
            />
          )}

          {activeTab === "query" && (
            <KeyValueEditor
              pairs={queryParams.length > 0 ? queryParams : [{ key: "", value: "", enabled: true }]}
              onChange={setQueryParams}
              showEnableToggle
            />
          )}

          {activeTab === "body" && hasBody && (
            <div>
              <div className="form-group">
                <label className="form-label">Content-Type</label>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <select
                    className="form-input"
                    value={contentType}
                    onChange={(e) => setContentType(e.target.value)}
                    style={{ maxWidth: 300 }}
                  >
                    {CONTENT_TYPES.map((ct) => (
                      <option key={ct} value={ct}>
                        {ct}
                      </option>
                    ))}
                  </select>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    或输入自定义类型
                  </span>
                </div>
              </div>
              <div className="form-group">
                <textarea
                  className="form-input"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder='{"key": "value"}'
                  style={{
                    minHeight: 150,
                    fontFamily: "var(--mono)",
                    fontSize: "0.8rem",
                    resize: "vertical",
                  }}
                  rows={8}
                />
                {contentType === "application/json" && body.trim() && (
                  <button
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      setBody(tryPrettifyJSON(body));
                    }}
                    style={{ marginTop: 4, fontSize: "0.72rem" }}
                  >
                    🧹 格式化 JSON
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="result-banner result-banner--error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* ── Response ── */}
      {response && (
        <div className="card">
          <div
            className="card__header"
            style={{ flexWrap: "wrap", gap: 8 }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  padding: "4px 12px",
                  borderRadius: "var(--radius-pill)",
                  fontSize: "0.85rem",
                  fontWeight: 650,
                  background: statusBadgeColor,
                  color: responseStatusCode >= 200 && responseStatusCode < 300 ? "var(--bg-deep)" : "#fff",
                  fontFamily: "var(--mono)",
                }}
              >
                {response.status || "—"} {response.status_text || ""}
              </span>
              <span
                style={{
                  padding: "4px 12px",
                  borderRadius: "var(--radius-pill)",
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  background: "var(--bg-surface)",
                  color: "var(--text-muted)",
                  fontFamily: "var(--mono)",
                }}
              >
                ⏱ {formatTiming(response.timing_ms)}
              </span>
              <span
                style={{
                  padding: "4px 12px",
                  borderRadius: "var(--radius-pill)",
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  background: "var(--bg-surface)",
                  color: "var(--text-muted)",
                  fontFamily: "var(--mono)",
                }}
              >
                📦 {formatBytes(response.body)}
              </span>
            </div>

            <button className="btn btn--ghost btn--sm" onClick={handleClear}>
              ✕ 清除
            </button>
          </div>

          {/* Response tabs */}
          <div style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--border)", marginBottom: 10 }}>
            {(["body", "headers"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setResponseTab(tab)}
                style={{
                  padding: "6px 14px",
                  background: "transparent",
                  border: "none",
                  borderBottom: responseTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                  color: responseTab === tab ? "var(--text-heading)" : "var(--text-muted)",
                  fontWeight: responseTab === tab ? 600 : 400,
                  cursor: "pointer",
                  fontSize: "0.82rem",
                  fontFamily: "var(--sans)",
                  transition: "color 140ms var(--ease-out), border-color 140ms var(--ease-out)",
                }}
              >
                {tab === "body" ? "Body" : "Headers"}
                {tab === "headers" && (
                  <span style={{ marginLeft: 6, fontSize: "0.7rem", opacity: 0.7 }}>
                    ({Object.keys(response.headers).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Response tab content */}
          {responseTab === "body" && (
            <pre
              style={{
                maxHeight: 500,
                overflow: "auto",
                fontFamily: "var(--mono)",
                fontSize: "0.78rem",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                padding: 12,
                background: "var(--bg-surface)",
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
              }}
            >
              {tryPrettifyJSON(response.body) || "(空响应)"}
            </pre>
          )}

          {responseTab === "headers" && (
            <div style={{ maxHeight: 400, overflow: "auto" }}>
              <table style={{ width: "100%", fontSize: "0.78rem" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", padding: "6px 12px", width: "35%" }}>Key</th>
                    <th style={{ textAlign: "left", padding: "6px 12px" }}>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(response.headers).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ padding: "4px 12px", fontFamily: "var(--mono)", fontSize: "0.75rem", color: "var(--text-heading)" }}>
                        {k}
                      </td>
                      <td style={{ padding: "4px 12px", fontFamily: "var(--mono)", fontSize: "0.75rem", wordBreak: "break-all" }}>
                        {v}
                      </td>
                    </tr>
                  ))}
                  {Object.keys(response.headers).length === 0 && (
                    <tr>
                      <td colSpan={2} style={{ padding: "12px", color: "var(--text-muted)", textAlign: "center" }}>
                        无响应头
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── History ── */}
      {history.length > 0 && (
        <details
          className="card"
          style={{ cursor: "pointer", marginTop: 16 }}
          open={showHistory}
          onToggle={(e) => setShowHistory((e.target as HTMLDetailsElement).open)}
        >
          <summary style={{ fontWeight: 600, fontSize: "0.9rem", padding: 4 }}>
            🕓 历史记录 ({history.length})
          </summary>
          <div style={{ maxHeight: 350, overflow: "auto", marginTop: 8 }}>
            {history.map((entry) => (
              <div
                key={entry.id}
                onClick={() => loadFromHistory(entry)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 12px",
                  borderRadius: "var(--radius)",
                  cursor: "pointer",
                  marginBottom: 2,
                  transition: "background 120ms var(--ease-out)",
                }}
                className="api-history-row"
              >
                <span
                  style={{
                    display: "inline-flex",
                    padding: "2px 8px",
                    borderRadius: "var(--radius-pill)",
                    fontSize: "0.68rem",
                    fontWeight: 700,
                    background: METHOD_COLORS[entry.method] || "var(--text-muted)",
                    color: "#fff",
                    minWidth: 52,
                    justifyContent: "center",
                    fontFamily: "var(--mono)",
                    flexShrink: 0,
                  }}
                >
                  {entry.method}
                </span>
                <code
                  style={{
                    flex: 1,
                    fontFamily: "var(--mono)",
                    fontSize: "0.75rem",
                    color: "var(--text-heading)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {entry.url}
                </code>
                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", flexShrink: 0 }}>
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
          <button
            className="btn btn--danger btn--sm"
            onClick={(e) => {
              e.stopPropagation();
              setHistory([]);
              saveHistory([]);
            }}
            style={{ marginTop: 8, fontSize: "0.72rem" }}
          >
            🗑 清空历史
          </button>
        </details>
      )}

      {/* History row hover style */}
      <style>{`
        .api-history-row:hover {
          background: var(--bg-surface);
        }
      `}</style>
    </div>
  );
}
