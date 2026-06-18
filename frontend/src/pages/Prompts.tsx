import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPrompts, createPrompt, updatePrompt, deletePrompt, aiGeneratePrompt } from "../api/client";
import { useState } from "react";

const AGENT_LABELS: Record<string, string> = {
  parse_requirement: "需求解析",
  orchestrator: "编排路由",
  code_review: "代码审查",
  sql_risk_explain: "SQL 风险解释",
  summary: "汇总报告",
  api_path: "API 路径扫描",
  auto_fix: "自动修复",
  compliance: "合规检查",
  review: "Git 审查",
};

export default function PromptsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["prompts"],
    queryFn: getPrompts,
  });

  const updateMutation = useMutation({
    mutationFn: ({ agent, system, user_template }: { agent: string; system?: string; user_template?: string }) =>
      updatePrompt(agent, system, user_template),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompts"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (agent: string) => deletePrompt(agent),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompts"] }),
  });

  const createMutation = useMutation({
    mutationFn: ({ agent, system, user_template }: { agent: string; system: string; user_template: string }) =>
      createPrompt(agent, system, user_template),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompts"] }),
  });

  const aiMutation = useMutation({
    mutationFn: (description: string) => aiGeneratePrompt(description),
  });

  const [editing, setEditing] = useState<string | null>(null);
  const [editSystem, setEditSystem] = useState("");
  const [editUserTemplate, setEditUserTemplate] = useState("");
  const [feedback, setFeedback] = useState<{ agent: string; ok: boolean; msg: string } | null>(null);

  // ── New prompt modal state ──
  const [showNewModal, setShowNewModal] = useState(false);
  const [newAgent, setNewAgent] = useState("");
  const [newSystem, setNewSystem] = useState("");
  const [newUserTemplate, setNewUserTemplate] = useState("{input}");
  const [aiDescription, setAiDescription] = useState("");
  const [aiResult, setAiResult] = useState<{ system: string; user_template: string; suggested_agent: string } | null>(null);
  const [aiError, setAiError] = useState("");

  // ── Delete confirm state ──
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  if (isLoading) return <div className="loading">Loading prompts…</div>;
  if (error) return <div className="error-message">Failed to load prompts.</div>;
  if (!data) return null;

  const showFeedback = (agent: string, ok: boolean, msg: string) => {
    setFeedback({ agent, ok, msg });
    setTimeout(() => setFeedback(null), 2500);
  };

  const startEdit = (agent: string, system: string, userTemplate: string) => {
    setEditing(agent);
    setEditSystem(system);
    setEditUserTemplate(userTemplate);
  };

  const cancelEdit = () => setEditing(null);

  const saveEdit = async (agent: string) => {
    try {
      const result = await updateMutation.mutateAsync({
        agent,
        system: editSystem,
        user_template: editUserTemplate,
      });
      if (result.ok) {
        setEditing(null);
        showFeedback(agent, true, "Saved");
      } else {
        showFeedback(agent, false, result.error || "Failed");
      }
    } catch {
      showFeedback(agent, false, "Network error");
    }
  };

  const handleDelete = async (agent: string) => {
    try {
      const result = await deleteMutation.mutateAsync(agent);
      if (result.ok) {
        setDeleteTarget(null);
        showFeedback(agent, true, result.message || "Deleted");
      } else {
        showFeedback(agent, false, result.error || "Failed");
      }
    } catch {
      showFeedback(agent, false, "Network error");
    }
  };

  const handleCreate = async () => {
    if (!newAgent.trim()) return;
    try {
      const result = await createMutation.mutateAsync({
        agent: newAgent.trim(),
        system: newSystem,
        user_template: newUserTemplate,
      });
      if (result.ok) {
        setShowNewModal(false);
        resetNewForm();
        showFeedback(result.agent, true, "Created");
      } else {
        showFeedback(newAgent, false, result.error || "Failed");
      }
    } catch {
      showFeedback(newAgent, false, "Network error");
    }
  };

  const handleAIGenerate = async () => {
    if (!aiDescription.trim()) return;
    setAiError("");
    setAiResult(null);
    const result = await aiMutation.mutateAsync(aiDescription.trim());
    if (result.ok) {
      setAiResult({
        system: result.system || "",
        user_template: result.user_template || "{input}",
        suggested_agent: result.suggested_agent || "custom_agent",
      });
      // Auto-fill the form
      setNewAgent(result.suggested_agent || "custom_agent");
      setNewSystem(result.system || "");
      setNewUserTemplate(result.user_template || "{input}");
    } else {
      setAiError(result.error || "AI generation failed");
    }
  };

  const resetNewForm = () => {
    setNewAgent("");
    setNewSystem("");
    setNewUserTemplate("{input}");
    setAiDescription("");
    setAiResult(null);
    setAiError("");
  };

  const openNewModal = () => {
    resetNewForm();
    setShowNewModal(true);
  };

  // Sort: built-in first (by agent list order), then custom alphabetically
  const builtInOrder = [
    "parse_requirement", "orchestrator", "code_review", "sql_risk_explain",
    "summary", "api_path", "auto_fix", "compliance", "review",
  ];
  const builtIns = data.prompts.filter((p) => !p.is_custom);
  const customs = data.prompts.filter((p) => p.is_custom);
  builtIns.sort((a, b) => builtInOrder.indexOf(a.agent) - builtInOrder.indexOf(b.agent));
  customs.sort((a, b) => a.agent.localeCompare(b.agent));
  const sortedPrompts = [...builtIns, ...customs];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h1>Prompt Configuration</h1>
        <button className="btn btn--primary btn--sm" onClick={openNewModal}>
          + New Prompt
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        Edit system prompts and user templates for each agent. Changes are persisted to disk and take effect immediately.
      </p>

      {/* ── New Prompt Modal ── */}
      {showNewModal && (
        <div className="modal-overlay" onClick={() => setShowNewModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 700, maxHeight: "90vh", overflow: "auto" }}>
            <div className="modal__header">
              <h2 style={{ margin: 0 }}>New Prompt</h2>
              <button className="btn btn--ghost btn--sm" onClick={() => setShowNewModal(false)}>✕</button>
            </div>
            <div className="modal__body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* AI Assist section */}
              <div className="card" style={{ background: "var(--bg-surface)", border: "1px solid var(--accent-soft)" }}>
                <h4 style={{ margin: "0 0 8px", color: "var(--accent)" }}>🤖 AI 辅助生成</h4>
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", margin: "0 0 8px" }}>
                  用自然语言描述你需要的 Agent，AI 将自动生成 System Prompt 和 User Template。
                </p>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    className="form-input"
                    placeholder="例如：一个用于检查 Dockerfile 安全配置的 agent"
                    value={aiDescription}
                    onChange={(e) => setAiDescription(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAIGenerate()}
                    style={{ flex: 1 }}
                  />
                  <button
                    className="btn btn--primary btn--sm"
                    onClick={handleAIGenerate}
                    disabled={aiMutation.isPending || !aiDescription.trim()}
                  >
                    {aiMutation.isPending ? "Generating…" : "生成"}
                  </button>
                </div>
                {aiError && (
                  <div className="error-message" style={{ marginTop: 8, fontSize: "0.8rem" }}>{aiError}</div>
                )}
                {aiResult && (
                  <div className="result-banner result-banner--success" style={{ marginTop: 8, fontSize: "0.8rem" }}>
                    ✓ AI 已生成模板，已自动填入下方表单，请检查后保存。
                  </div>
                )}
              </div>

              {/* Manual form */}
              <div className="form-group">
                <label className="form-label">Agent 标识符</label>
                <input
                  className="form-input"
                  placeholder="my_custom_agent"
                  value={newAgent}
                  onChange={(e) => setNewAgent(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">System Prompt</label>
                <textarea
                  className="form-input"
                  style={{ minHeight: 200, fontFamily: "var(--mono)", fontSize: "0.8rem", resize: "vertical" }}
                  value={newSystem}
                  onChange={(e) => setNewSystem(e.target.value)}
                  placeholder="定义 agent 的角色、输入输出格式和分析维度…"
                />
              </div>
              <div className="form-group">
                <label className="form-label">User Template</label>
                <input
                  className="form-input"
                  value={newUserTemplate}
                  onChange={(e) => setNewUserTemplate(e.target.value)}
                  placeholder="{input}"
                />
              </div>
            </div>
            <div className="modal__footer" style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 16 }}>
              <button className="btn btn--secondary btn--sm" onClick={() => setShowNewModal(false)}>Cancel</button>
              <button
                className="btn btn--primary btn--sm"
                onClick={handleCreate}
                disabled={createMutation.isPending || !newAgent.trim() || !newSystem.trim()}
              >
                {createMutation.isPending ? "Creating…" : "Create Prompt"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete Confirm Modal ── */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <div className="modal__header">
              <h3 style={{ margin: 0 }}>确认删除</h3>
            </div>
            <div className="modal__body">
              <p>
                确定要删除 <strong>{deleteTarget}</strong> 的 prompt 吗？
                {data.prompts.find((p) => p.agent === deleteTarget && !p.is_custom)
                  ? " 内置 agent 将恢复为默认值。"
                  : " 此操作不可撤销。"}
              </p>
            </div>
            <div className="modal__footer" style={{ display: "flex", gap: 8, justifyContent: "flex-end", paddingTop: 12 }}>
              <button className="btn btn--secondary btn--sm" onClick={() => setDeleteTarget(null)}>Cancel</button>
              <button
                className="btn btn--danger btn--sm"
                onClick={() => handleDelete(deleteTarget)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Prompt Cards ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {sortedPrompts.map((p) => {
          const isEditing = editing === p.agent;
          const label = AGENT_LABELS[p.agent] || p.agent;

          return (
            <div key={p.agent} className="card">
              <div className="card__header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <h3 style={{ margin: 0 }}>{label}</h3>
                  <code style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{p.agent}</code>
                  {p.is_custom && (
                    <span className="badge badge--info" style={{ fontSize: "0.65rem" }}>custom</span>
                  )}
                  {p.overridden && !p.is_custom && (
                    <span className="badge badge--warning" style={{ fontSize: "0.65rem" }}>edited</span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {!isEditing ? (
                    <>
                      <button
                        className="btn btn--secondary btn--sm"
                        onClick={() => startEdit(p.agent, p.system, p.user_template)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn--danger btn--sm"
                        onClick={() => setDeleteTarget(p.agent)}
                      >
                        Delete
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn--primary btn--sm" onClick={() => saveEdit(p.agent)} disabled={updateMutation.isPending}>
                        {updateMutation.isPending ? "Saving…" : "Save"}
                      </button>
                      <button className="btn btn--secondary btn--sm" onClick={cancelEdit}>
                        Cancel
                      </button>
                    </>
                  )}
                  {feedback?.agent === p.agent && (
                    <span style={{ fontSize: "0.78rem", color: feedback.ok ? "var(--success)" : "var(--danger)", alignSelf: "center" }}>
                      {feedback.ok ? "✓" : "✗"} {feedback.msg}
                    </span>
                  )}
                </div>
              </div>

              {isEditing ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 12 }}>
                  <div>
                    <label style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 4, display: "block" }}>
                      System Prompt
                    </label>
                    <textarea
                      className="form-input"
                      style={{ width: "100%", minHeight: 200, fontFamily: "var(--mono)", fontSize: "0.8rem", lineHeight: 1.5, resize: "vertical" }}
                      value={editSystem}
                      onChange={(e) => setEditSystem(e.target.value)}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 4, display: "block" }}>
                      User Template
                    </label>
                    <textarea
                      className="form-input"
                      style={{ width: "100%", minHeight: 48, fontFamily: "var(--mono)", fontSize: "0.8rem", resize: "vertical" }}
                      value={editUserTemplate}
                      onChange={(e) => setEditUserTemplate(e.target.value)}
                    />
                  </div>
                </div>
              ) : (
                <div style={{ paddingTop: 8 }}>
                  <pre style={{
                    fontSize: "0.78rem",
                    fontFamily: "var(--mono)",
                    color: "var(--text-muted)",
                    whiteSpace: "pre-wrap",
                    maxHeight: 120,
                    overflow: "hidden",
                    background: "var(--bg-surface)",
                    padding: "8px 12px",
                    borderRadius: "var(--radius)",
                    margin: 0,
                  }}>
                    {p.system.slice(0, 300)}{p.system.length > 300 ? "…" : ""}
                  </pre>
                  {p.user_template !== "{input}" && (
                    <div style={{ marginTop: 8, fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      User template: <code>{p.user_template}</code>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
