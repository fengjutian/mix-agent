import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getMCPServers,
  addMCPServer,
  updateMCPServer,
  deleteMCPServer,
  testMCPServer,
} from "../api/client";
import { useState } from "react";

interface MCPServer {
  name: string;
  transport: string;
  enabled: boolean;
  command: string;
  args: string[];
  env: Record<string, string>;
  url: string;
  headers: Record<string, string>;
}

interface TestResult {
  ok: boolean;
  server_name: string;
  server_version: string;
  tools: Array<{ name: string; description: string; input_schema: any }>;
  error: string;
}

const TRANSPORT_LABELS: Record<string, string> = {
  stdio: "标准 I/O（子进程）",
  http: "HTTP（可流式）",
  sse: "SSE（服务器推送事件）",
};

export default function MCPServersPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: getMCPServers,
    refetchInterval: 30_000,
  });

  const addMutation = useMutation({
    mutationFn: addMCPServer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ name, updates }: { name: string; updates: Record<string, any> }) =>
      updateMCPServer(name, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMCPServer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mcp-servers"] }),
  });

  const [showAdd, setShowAdd] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState<string | null>(null);

  // Add form state
  const [form, setForm] = useState({
    name: "",
    transport: "stdio",
    command: "",
    args: "",
    env: "",
    url: "",
    headers: "",
  });

  const resetForm = () =>
    setForm({ name: "", transport: "stdio", command: "", args: "", env: "", url: "", headers: "" });

  if (isLoading) return <div className="loading">正在加载 MCP 服务器…</div>;
  if (error) return <div className="error-message">无法加载 MCP 服务器。</div>;
  if (!data) return null;

  const handleAdd = async () => {
    if (!form.name.trim()) return;
    const result = await addMutation.mutateAsync({
      name: form.name.trim(),
      transport: form.transport,
      command: form.command.trim(),
      args: form.args.split("\n").filter(Boolean),
      env: parseKeyValue(form.env),
      url: form.url.trim(),
      headers: parseKeyValue(form.headers),
    });
    if (result.ok) {
      resetForm();
      setShowAdd(false);
    } else {
      alert(result.error || "添加服务器失败");
    }
  };

  const handleToggle = async (s: MCPServer) => {
    await updateMutation.mutateAsync({ name: s.name, updates: { enabled: !s.enabled } });
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`确定要删除 MCP 服务器 "${name}" 吗？`)) return;
    await deleteMutation.mutateAsync(name);
  };

  const handleTest = async (name: string) => {
    setTesting(name);
    setTestResult(null);
    try {
      const res = await testMCPServer(name);
      setTestResult(res);
    } catch (e: any) {
      setTestResult({ ok: false, server_name: "", server_version: "", tools: [], error: e.message });
    } finally {
      setTesting(null);
    }
  };

  return (
    <div>
      <h1>MCP 服务器</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        配置外部 MCP（模型上下文协议）服务器，代理可连接这些服务器以获取工具访问权限。
        支持 stdio（子进程）、HTTP 和 SSE 传输方式。
      </p>

      <div style={{ marginBottom: 16 }}>
        <button
          className="btn btn--primary btn--sm"
          onClick={() => { resetForm(); setShowAdd(!showAdd); setEditingName(null); setTestResult(null); }}
        >
          {showAdd ? "取消" : "+ 添加服务器"}
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card__header"><h3 style={{ margin: 0 }}>添加 MCP 服务器</h3></div>
          <MCPServerForm
            form={form}
            setForm={setForm}
            onSave={handleAdd}
            saving={addMutation.isPending}
            saveLabel="添加"
          />
        </div>
      )}

      {/* Edit form */}
      {editingName && (() => {
        const s = data.servers.find((x) => x.name === editingName);
        if (!s) return null;
        const editForm = {
          name: s.name,
          transport: s.transport,
          command: s.command,
          args: s.args.join("\n"),
          env: dictToLines(s.env),
          url: s.url,
          headers: dictToLines(s.headers),
        };
        return (
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card__header"><h3 style={{ margin: 0 }}>编辑：{s.name}</h3></div>
            <MCPServerForm
              form={editForm}
              setForm={(f) => {
                setForm(f);
              }}
              onSave={async () => {
                const result = await updateMutation.mutateAsync({
                  name: editingName,
                  updates: {
                    transport: editForm.transport,
                    command: editForm.command.trim(),
                    args: editForm.args.split("\n").filter(Boolean),
                    env: parseKeyValue(editForm.env),
                    url: editForm.url.trim(),
                    headers: parseKeyValue(editForm.headers),
                  },
                });
                if (result.ok) setEditingName(null);
                else alert(result.error || "失败");
              }}
              saving={updateMutation.isPending}
              saveLabel="保存"
            />
          </div>
        );
      })()}

      {/* Test result */}
      {testResult && (
        <div className="card" style={{ marginBottom: 20, borderColor: testResult.ok ? "var(--success)" : "var(--danger)" }}>
          <div className="card__header">
            <h3 style={{ margin: 0, color: testResult.ok ? "var(--success)" : "var(--danger)" }}>
              {testResult.ok ? "✓ 连接成功" : "✗ 连接失败"}
            </h3>
            <button className="btn btn--secondary btn--sm" onClick={() => setTestResult(null)}>关闭</button>
          </div>
          {testResult.ok ? (
            <div>
              <p>
                <strong>{testResult.server_name}</strong> v{testResult.server_version}
              </p>
              {testResult.tools.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4, fontSize: "0.82rem" }}>
                    可用工具 ({testResult.tools.length})
                  </div>
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>工具</th>
                          <th>描述</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testResult.tools.map((t) => (
                          <tr key={t.name}>
                            <td><code>{t.name}</code></td>
                            <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                              {t.description}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              {testResult.tools.length === 0 && (
                <p style={{ color: "var(--text-muted)" }}>此服务器未暴露任何工具。</p>
              )}
            </div>
          ) : (
            <p style={{ color: "var(--danger)" }}>{testResult.error}</p>
          )}
        </div>
      )}

      {/* Server list */}
      {data.servers.length === 0 && !showAdd && (
        <p className="empty-state">未配置 MCP 服务器。点击 "+ 添加服务器" 添加一个。</p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {data.servers.map((s) => (
          <div
            key={s.name}
            className="card"
            style={{ opacity: s.enabled ? 1 : 0.55 }}
          >
            <div className="card__header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <h3 style={{ margin: 0 }}>{s.name}</h3>
                <span style={{
                  fontSize: "0.7rem",
                  padding: "1px 8px",
                  borderRadius: 99,
                  background: s.transport === "stdio" ? "var(--accent)" : s.transport === "http" ? "#7c3aed" : "#db2777",
                  color: "#fff",
                  fontFamily: "var(--mono)",
                }}>
                  {s.transport}
                </span>
                <span className={`badge ${s.enabled ? "badge--success" : "badge--warning"}`} style={{ fontSize: "0.65rem" }}>
                  {s.enabled ? "已启用" : "已禁用"}
                </span>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  className="btn btn--secondary btn--sm"
                  onClick={() => handleToggle(s)}
                  disabled={updateMutation.isPending}
                >
                  {s.enabled ? "禁用" : "启用"}
                </button>
                <button
                  className="btn btn--secondary btn--sm"
                  onClick={() => handleTest(s.name)}
                  disabled={testing === s.name}
                >
                  {testing === s.name ? "测试中…" : "测试"}
                </button>
                <button
                  className="btn btn--secondary btn--sm"
                  onClick={() => { setEditingName(s.name); setShowAdd(false); setTestResult(null); }}
                >
                  编辑
                </button>
                <button
                  className="btn btn--danger btn--sm"
                  onClick={() => handleDelete(s.name)}
                  disabled={deleteMutation.isPending}
                >
                  删除
                </button>
              </div>
            </div>
            <div style={{ display: "flex", gap: 24, fontSize: "0.78rem", color: "var(--text-muted)", paddingTop: 4 }}>
              {s.transport === "stdio" && s.command && (
                <span><strong>命令：</strong> <code>{s.command} {s.args.join(" ")}</code></span>
              )}
              {(s.transport === "http" || s.transport === "sse") && s.url && (
                <span><strong>网址：</strong> <code>{s.url}</code></span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Reusable form for add/edit ── */

function MCPServerForm({
  form,
  setForm,
  onSave,
  saving,
  saveLabel,
}: {
  form: { name: string; transport: string; command: string; args: string; env: string; url: string; headers: string };
  setForm: (f: typeof form) => void;
  onSave: () => void;
  saving: boolean;
  saveLabel: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <label className="field-label">名称</label>
          <input
            className="form-input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. stripe, github"
            disabled={saveLabel === "保存"}
          />
        </div>
        <div>
          <label className="field-label">传输方式</label>
          <select
            className="form-input"
            value={form.transport}
            onChange={(e) => setForm({ ...form, transport: e.target.value })}
          >
            <option value="stdio">stdio（子进程）</option>
            <option value="http">http（可流式 HTTP）</option>
            <option value="sse">sse（服务器推送事件）</option>
          </select>
        </div>
      </div>

      {form.transport === "stdio" && (
        <>
          <div>
            <label className="field-label">命令</label>
            <input
              className="form-input"
              value={form.command}
              onChange={(e) => setForm({ ...form, command: e.target.value })}
              placeholder="e.g. npx, python, uvx"
            />
          </div>
          <div>
            <label className="field-label">参数（每行一个）</label>
            <textarea
              className="form-input"
              style={{ minHeight: 50, fontFamily: "var(--mono)", fontSize: "0.8rem" }}
              value={form.args}
              onChange={(e) => setForm({ ...form, args: e.target.value })}
              placeholder={"-y\n@anthropic/mcp-server-stripe"}
            />
          </div>
          <div>
            <label className="field-label">环境变量（KEY=VALUE，每行一个）</label>
            <textarea
              className="form-input"
              style={{ minHeight: 50, fontFamily: "var(--mono)", fontSize: "0.8rem" }}
              value={form.env}
              onChange={(e) => setForm({ ...form, env: e.target.value })}
              placeholder={"STRIPE_KEY=sk_xxx\nDEBUG=true"}
            />
          </div>
        </>
      )}

      {(form.transport === "http" || form.transport === "sse") && (
        <>
          <div>
            <label className="field-label">网址</label>
            <input
              className="form-input"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="https://mcp.example.com"
            />
          </div>
          <div>
            <label className="field-label">请求头（Key=Value，每行一个）</label>
            <textarea
              className="form-input"
              style={{ minHeight: 50, fontFamily: "var(--mono)", fontSize: "0.8rem" }}
              value={form.headers}
              onChange={(e) => setForm({ ...form, headers: e.target.value })}
              placeholder={"Authorization=Bearer ${TOKEN}\nX-Custom=value"}
            />
          </div>
        </>
      )}

      <div>
        <button className="btn btn--primary btn--sm" onClick={onSave} disabled={saving}>
          {saving ? "保存中…" : saveLabel}
        </button>
      </div>
    </div>
  );
}

/* ── helpers ── */

function parseKeyValue(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const idx = line.indexOf("=");
    if (idx > 0) {
      result[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    }
  }
  return result;
}

function dictToLines(d: Record<string, string>): string {
  return Object.entries(d)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
}
