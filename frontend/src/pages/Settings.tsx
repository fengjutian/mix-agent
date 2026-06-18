import { useQuery } from "@tanstack/react-query";
import { getCostOverview, getCostBreakdown } from "../api/client";

export default function SettingsPage() {
  const overviewQ = useQuery({ queryKey: ["cost-overview"], queryFn: getCostOverview });
  const breakdownQ = useQuery({ queryKey: ["cost-breakdown"], queryFn: getCostBreakdown });

  const overview = overviewQ.data;
  const breakdown = breakdownQ.data;

  return (
    <div>
      <h1>成本概览</h1>

      {/* ── Overview Stats ── */}
      {overview && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 14,
          marginBottom: 32,
        }}>
          <StatCard label="总成本" value={`$${overview.total_cost}`} />
          <StatCard label="总调用次数" value={overview.total_calls?.toLocaleString()} />
          <StatCard label="提示 Token" value={overview.total_prompt_tokens?.toLocaleString()} />
          <StatCard label="补全 Token" value={overview.total_completion_tokens?.toLocaleString()} />
          <StatCard
            label="活跃任务"
            value={`${overview.active_tasks} / ${overview.total_tasks}`}
          />
        </div>
      )}

      {/* ── Breakdown Table ── */}
      {breakdown && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>按任务</h2>
          <div className="divider" style={{ margin: "12px 0 0" }} />
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th style={{ textAlign: "right" }}>成本</th>
                  <th style={{ textAlign: "right" }}>调用</th>
                  <th style={{ textAlign: "right" }}>用量</th>
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
                        <p>暂无任务</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {overviewQ.isLoading && <div className="loading">加载成本数据中...</div>}
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
