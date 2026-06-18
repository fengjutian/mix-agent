import { useQuery } from "@tanstack/react-query";
import { getCostOverview, getCostBreakdown } from "../api/client";

export default function SettingsPage() {
  const overviewQ = useQuery({ queryKey: ["cost-overview"], queryFn: getCostOverview });
  const breakdownQ = useQuery({ queryKey: ["cost-breakdown"], queryFn: getCostBreakdown });

  const overview = overviewQ.data;
  const breakdown = breakdownQ.data;

  return (
    <div>
      <h1>Cost Dashboard</h1>

      {/* ── Overview Stats ── */}
      {overview && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 14,
          marginBottom: 32,
        }}>
          <StatCard label="Total Cost" value={`$${overview.total_cost}`} />
          <StatCard label="Total Calls" value={overview.total_calls?.toLocaleString()} />
          <StatCard label="Prompt Tokens" value={overview.total_prompt_tokens?.toLocaleString()} />
          <StatCard label="Completion Tokens" value={overview.total_completion_tokens?.toLocaleString()} />
          <StatCard
            label="Active Tasks"
            value={`${overview.active_tasks} / ${overview.total_tasks}`}
          />
        </div>
      )}

      {/* ── Breakdown Table ── */}
      {breakdown && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>By Task</h2>
          <div className="divider" style={{ margin: "12px 0 0" }} />
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th style={{ textAlign: "right" }}>Cost</th>
                  <th style={{ textAlign: "right" }}>Calls</th>
                  <th style={{ textAlign: "right" }}>Usage</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.tasks?.length > 0 ? (
                  breakdown.tasks.map((t: any) => (
                    <tr key={t.task_id}>
                      <td>
                        <code>{t.task_id?.slice(0, 14)}...</code>
                      </td>
                      <td style={{ textAlign: "right", fontFamily: "var(--mono)", fontSize: "0.85rem" }}>
                        ${t.cost}
                      </td>
                      <td style={{ textAlign: "right" }}>{t.calls}</td>
                      <td style={{ textAlign: "right" }}>
                        <span className={`badge ${
                          t.is_over_budget ? "badge--danger" :
                          t.needs_downgrade ? "badge--warning" :
                          "badge--success"
                        }`}>
                          {t.usage_pct}%
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4}>
                      <div className="empty-state" style={{ padding: "32px 0" }}>
                        <p>No tasks yet</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {overviewQ.isLoading && <div className="loading">Loading cost data...</div>}
      {overviewQ.error && <div className="error-message">{(overviewQ.error as Error).message}</div>}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value?: string }) {
  return (
    <div className="card" style={{ textAlign: "center" }}>
      <div style={{
        fontSize: "0.78rem",
        color: "var(--text-muted)",
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        marginBottom: 8,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: "clamp(1.2rem, 2vw, 1.6rem)",
        fontWeight: 650,
        color: "var(--text-heading)",
        fontFamily: "var(--mono)",
      }}>
        {value ?? "—"}
      </div>
    </div>
  );
}
