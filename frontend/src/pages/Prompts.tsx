import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPrompts, updatePrompt, resetPrompt } from "../api/client";
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

  const resetMutation = useMutation({
    mutationFn: (agent: string) => resetPrompt(agent),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["prompts"] }),
  });

  const [editing, setEditing] = useState<string | null>(null);
  const [editSystem, setEditSystem] = useState("");
  const [editUserTemplate, setEditUserTemplate] = useState("");
  const [feedback, setFeedback] = useState<{ agent: string; ok: boolean; msg: string } | null>(null);

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
  };

  const handleReset = async (agent: string) => {
    const result = await resetMutation.mutateAsync(agent);
    if (result.ok) {
      setEditing(null);
      showFeedback(agent, true, "Reset to default");
    } else {
      showFeedback(agent, false, result.error || "Failed");
    }
  };

  const agentOrder = [
    "parse_requirement",
    "orchestrator",
    "code_review",
    "sql_risk_explain",
    "summary",
    "api_path",
    "auto_fix",
    "compliance",
  ];

  return (
    <div>
      <h1>Prompt Configuration</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        Edit system prompts and user templates for each agent. Changes are persisted to disk and take effect immediately.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {agentOrder.map((agent) => {
          const p = data.prompts.find((x) => x.agent === agent);
          if (!p) return null;

          const isEditing = editing === agent;
          const label = AGENT_LABELS[agent] || agent;

          return (
            <div key={agent} className="card">
              <div className="card__header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <h3 style={{ margin: 0 }}>{label}</h3>
                  <code style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{agent}</code>
                  {p.overridden && (
                    <span className="badge badge--warning" style={{ fontSize: "0.65rem" }}>edited</span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {!isEditing ? (
                    <button
                      className="btn btn--secondary btn--sm"
                      onClick={() => startEdit(agent, p.system, p.user_template)}
                    >
                      Edit
                    </button>
                  ) : (
                    <>
                      <button className="btn btn--primary btn--sm" onClick={() => saveEdit(agent)} disabled={updateMutation.isPending}>
                        {updateMutation.isPending ? "Saving…" : "Save"}
                      </button>
                      <button className="btn btn--secondary btn--sm" onClick={cancelEdit}>
                        Cancel
                      </button>
                      <button className="btn btn--danger btn--sm" onClick={() => handleReset(agent)} disabled={resetMutation.isPending}>
                        Reset
                      </button>
                    </>
                  )}
                  {feedback?.agent === agent && (
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
