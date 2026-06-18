import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTask, getFindings, getReport } from "../api/client";

const riskLabel: Record<string, { label: string; badge: string }> = {
  danger:  { label: "DANGER",  badge: "badge--danger" },
  warning: { label: "WARNING", badge: "badge--warning" },
  info:    { label: "INFO",    badge: "badge--info" },
};

const statusBadge: Record<string, string> = {
  completed: "badge--success",
  failed:    "badge--danger",
  running:   "badge--info",
  pending:   "badge--warning",
};

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();

  const taskQ = useQuery({ queryKey: ["task", id], queryFn: () => getTask(id!) });
  const findingsQ = useQuery({ queryKey: ["findings", id], queryFn: () => getFindings(id!) });
  const reportQ = useQuery({ queryKey: ["report", id], queryFn: () => getReport(id!) });

  if (taskQ.isLoading) return <div className="loading">Loading task...</div>;
  if (taskQ.error) return <div className="error-message">{(taskQ.error as Error).message}</div>;

  const task = taskQ.data;
  const findings = findingsQ.data?.findings || [];
  const report = reportQ.data;

  return (
    <div>
      <h1>Task Detail</h1>

      {/* ── Task Info Card ── */}
      <div className="card">
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 20px", fontSize: "0.92rem" }}>
          <span style={{ color: "var(--text-muted)" }}>ID</span>
          <span style={{ fontFamily: "var(--mono)", color: "var(--text-heading)" }}>{task?.task_id}</span>

          <span style={{ color: "var(--text-muted)" }}>Status</span>
          <span>
            <span className={`badge ${statusBadge[task?.status ?? ""] || "badge--info"}`}>
              {task?.status}
            </span>
          </span>

          <span style={{ color: "var(--text-muted)" }}>Branch</span>
          <span style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}>
            {task?.base_branch} → {task?.target_branch}
          </span>
        </div>
      </div>

      {/* ── Findings ── */}
      <h2 style={{ marginTop: 32 }}>
        Findings
        {findingsQ.data?.total != null && (
          <span style={{
            marginLeft: 10,
            fontSize: "0.85rem",
            color: "var(--text-muted)",
            fontWeight: 400,
          }}>
            ({findingsQ.data.total})
          </span>
        )}
      </h2>

      {findingsQ.isLoading && <div className="loading">Loading findings...</div>}

      {!findingsQ.isLoading && findings.length === 0 && (
        <div className="empty-state">
          <div className="empty-state__icon">🔍</div>
          <p>No findings yet.</p>
        </div>
      )}

      {findings.map((f: any, i: number) => {
        const risk = riskLabel[f.risk_level] || riskLabel.info;
        return (
          <div key={i} className="finding-item" data-risk={f.risk_level}>
            <div className="finding-item__header">
              <span className={`badge ${risk.badge}`}>{risk.label}</span>
              <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                {f.agent}/{f.finding_type}
              </span>
            </div>
            <p className="finding-item__desc">{f.description}</p>
            {f.file_path && (
              <span className="finding-item__file">
                {f.file_path}{f.line_number ? `:${f.line_number}` : ""}
              </span>
            )}
          </div>
        );
      })}

      {/* ── Report ── */}
      {report && (
        <>
          <div className="divider" />
          <h2>Report</h2>
          <pre style={{ maxHeight: 420 }}>{JSON.stringify(report, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
