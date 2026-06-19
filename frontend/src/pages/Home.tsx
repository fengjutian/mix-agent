import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createTask, runAgent, getAgentResult } from "../api/client";
import DirectoryPicker from "../components/DirectoryPicker";

type Mode = "scan" | "agent";

export default function HomePage() {
  const [mode, setMode] = useState<Mode>("agent");
  const [repo, setRepo] = useState(".");
  const [target, setTarget] = useState("HEAD");
  const [base, setBase] = useState("main");
  const [desc, setDesc] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [agentDetail, setAgentDetail] = useState<any>(null);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setAgentDetail(null);

    try {
      if (mode === "agent") {
        // Phase 2: AI Agent
        const data = await runAgent({
          description: desc || "请分析代码变更的安全性",
          target_branch: target,
          base_branch: base,
          repo_path: repo,
        });
        setResult(data);

        // If completed, fetch full result
        if (data.task_id && data.status !== "failed") {
          try {
            const detail = await getAgentResult(data.task_id);
            setAgentDetail(detail);
          } catch {
            // detail fetch is best-effort
          }
        }
      } else {
        // Phase 1: Fast Scan
        const data = await createTask({
          description: desc || `Scan ${base}..${target}`,
          target_branch: target,
          base_branch: base,
          repo_path: repo,
        });
        setResult(data);
        if (data.task_id) navigate(`/tasks/${data.task_id}`);
      }
    } catch (err: any) {
      setResult({ error: err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>新建审计任务</h1>

      {/* ── Mode toggle ── */}
      <div style={{ display: "flex", gap: 0, marginBottom: 20 }}>
        <button
          type="button"
          className={`btn btn--sm ${mode === "agent" ? "btn--primary" : "btn--ghost"}`}
          style={{
            borderTopRightRadius: 0,
            borderBottomRightRadius: 0,
            borderRight: mode === "agent" ? undefined : "1px solid var(--border)",
          }}
          onClick={() => setMode("agent")}
        >
          🤖 AI 智能审计
        </button>
        <button
          type="button"
          className={`btn btn--sm ${mode === "scan" ? "btn--primary" : "btn--ghost"}`}
          style={{
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0,
          }}
          onClick={() => setMode("scan")}
        >
          ⚡ 快速扫描
        </button>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">仓库路径</label>
            <DirectoryPicker value={repo} onChange={setRepo} />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">目标分支</label>
              <input
                className="form-input"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">基准分支</label>
              <input
                className="form-input"
                value={base}
                onChange={(e) => setBase(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              {mode === "agent" ? "自然语言描述" : "描述"}
              <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>
                {mode === "agent" ? " (LLM 理解模糊需求)" : " (可选)"}
              </span>
            </label>
            <input
              className="form-input"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder={
                mode === "agent"
                  ? "e.g. 重点检查数据库的 SQL 注入和权限问题"
                  : "例如：检查数据库 SQL 安全性"
              }
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary btn--lg btn--block"
            disabled={loading}
          >
            {loading
              ? mode === "agent"
                ? "AI 分析中..."
                : "扫描中..."
              : mode === "agent"
                ? "开始 AI 审计"
                : "开始扫描"}
          </button>
        </form>
      </div>

      {/* ── Result ── */}
      {result && (
        <div style={{ marginTop: 20 }}>
          {result.error ? (
            <div className="result-banner result-banner--error">{result.error}</div>
          ) : (
            <div className="result-banner result-banner--success">
              Task created: <strong>{result.task_id}</strong> — 状态：{" "}
              <span
                className={`badge ${
                  result.status === "awaiting_approval" ? "badge--warning" : "badge--info"
                }`}
              >
                {result.status}
              </span>
              {result.message && (
                <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>
                  — {result.message}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── AI Agent Detail ── */}
      {agentDetail && agentDetail.result && (
        <div style={{ marginTop: 24 }}>
          {/* Parse Result — how AI understood the requirement */}
          {agentDetail.result.parse_result?.task_name && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0, fontSize: "1rem" }}>
                🧠 AI 理解的需求
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", fontSize: "0.88rem" }}>
                <span style={{ color: "var(--text-muted)" }}>任务名</span>
                <span style={{ fontWeight: 600 }}>{agentDetail.result.parse_result.task_name}</span>

                <span style={{ color: "var(--text-muted)" }}>描述</span>
                <span>{agentDetail.result.parse_result.description}</span>

                <span style={{ color: "var(--text-muted)" }}>审计范围</span>
                <span>{agentDetail.result.parse_result.scope}</span>

                <span style={{ color: "var(--text-muted)" }}>关注领域</span>
                <span>
                  {(agentDetail.result.parse_result.focus_areas || []).map((a: string) => (
                    <span key={a} className="badge badge--info" style={{ marginRight: 4 }}>
                      {a}
                    </span>
                  ))}
                </span>

                {agentDetail.result.parse_result.constraints?.length > 0 && (
                  <>
                    <span style={{ color: "var(--text-muted)" }}>约束</span>
                    <span>
                      {agentDetail.result.parse_result.constraints.map((c: string, i: number) => (
                        <span key={i} className="badge badge--warning" style={{ marginRight: 4 }}>
                          {c}
                        </span>
                      ))}
                    </span>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Orchestrator */}
          {agentDetail.result.orchestrator_result?.activated_agents && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0, fontSize: "1rem" }}>
                🎯 激活的 Agent
              </h3>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                {(agentDetail.result.orchestrator_result.activated_agents || []).map((a: string) => (
                  <span key={a} className="badge badge--success" style={{ fontSize: "0.85rem" }}>
                    {a}
                  </span>
                ))}
              </div>
              {agentDetail.result.orchestrator_result.reasoning && (
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  {agentDetail.result.orchestrator_result.reasoning}
                </p>
              )}
            </div>
          )}

          {/* Summary */}
          {agentDetail.result.summary_result?.title && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0, fontSize: "1rem" }}>
                📋 {agentDetail.result.summary_result.title}
              </h3>
              <p style={{ fontSize: "0.9rem", whiteSpace: "pre-wrap" }}>
                {agentDetail.result.summary_result.summary}
              </p>

              {agentDetail.result.summary_result.risk_summary && (
                <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
                  {(["danger", "warning", "safe"] as const).map((level) => {
                    const count = agentDetail.result.summary_result.risk_summary[level] ?? 0;
                    const badge = level === "danger" ? "badge--danger" : level === "warning" ? "badge--warning" : "badge--success";
                    return (
                      <span key={level} className={`badge ${badge}`}>
                        {level}: {count}
                      </span>
                    );
                  })}
                </div>
              )}

              {agentDetail.result.summary_result.top_recommendations?.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <strong style={{ fontSize: "0.85rem" }}>首要建议：</strong>
                  <ul style={{ margin: "4px 0 0 0", paddingLeft: 20, fontSize: "0.85rem" }}>
                    {agentDetail.result.summary_result.top_recommendations.map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              {agentDetail.result.summary_result.conclusion && (
                <p style={{ marginTop: 12, padding: "8px 12px", background: "var(--bg-surface)", borderRadius: 6, fontSize: "0.88rem", borderLeft: "3px solid var(--accent)" }}>
                  {agentDetail.result.summary_result.conclusion}
                </p>
              )}
            </div>
          )}

          {/* Code Review findings */}
          {agentDetail.result.code_review_result?.findings?.length > 0 && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0, fontSize: "1rem" }}>🔍 代码审查发现</h3>
              {agentDetail.result.code_review_result.findings.map((f: any, i: number) => (
                <div key={i} className="finding-item" data-risk={f.severity || "info"}>
                  <div className="finding-item__header">
                    <span className={`badge ${f.severity === "danger" ? "badge--danger" : f.severity === "warning" ? "badge--warning" : "badge--info"}`}>
                      {f.severity?.toUpperCase() || "INFO"}
                    </span>
                    <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                      {f.category}
                    </span>
                  </div>
                  <p className="finding-item__desc">{f.summary}</p>
                  {f.file && (
                    <span className="finding-item__file">
                      {f.file}{f.line ? `:${f.line}` : ""}
                    </span>
                  )}
                  {f.recommendation && (
                    <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: 4 }}>
                      💡 {f.recommendation}
                    </p>
                  )}
                </div>
              ))}
              {agentDetail.result.code_review_result.overall_assessment && (
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: 8, fontStyle: "italic" }}>
                  {agentDetail.result.code_review_result.overall_assessment}
                </p>
              )}
            </div>
          )}

          {/* Token usage */}
          {agentDetail.result.accumulated_tokens > 0 && (
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", textAlign: "right" }}>
              💰 LLM Token 用量：{agentDetail.result.accumulated_tokens.toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
