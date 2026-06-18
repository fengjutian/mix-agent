import { useQuery } from "@tanstack/react-query";
import { getCostOverview, getCostBreakdown } from "../api/client";

export default function SettingsPage() {
  const overviewQ = useQuery({ queryKey: ["cost-overview"], queryFn: getCostOverview });
  const breakdownQ = useQuery({ queryKey: ["cost-breakdown"], queryFn: getCostBreakdown });

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", padding: 24 }}>
      <h1>Cost Dashboard</h1>

      {overviewQ.data && (
        <div style={{ background: "#f5f5f5", padding: 16, borderRadius: 8, marginBottom: 24 }}>
          <h2>Overview</h2>
          <p><strong>Total Cost:</strong> ${overviewQ.data.total_cost}</p>
          <p><strong>Total Calls:</strong> {overviewQ.data.total_calls}</p>
          <p><strong>Prompt Tokens:</strong> {overviewQ.data.total_prompt_tokens?.toLocaleString()}</p>
          <p><strong>Completion Tokens:</strong> {overviewQ.data.total_completion_tokens?.toLocaleString()}</p>
          <p><strong>Active Tasks:</strong> {overviewQ.data.active_tasks} / {overviewQ.data.total_tasks}</p>
        </div>
      )}

      {breakdownQ.data && (
        <div>
          <h2>By Task</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#eee" }}>
                <th style={{ padding: 8, textAlign: "left" }}>Task</th>
                <th style={{ padding: 8, textAlign: "right" }}>Cost</th>
                <th style={{ padding: 8, textAlign: "right" }}>Calls</th>
                <th style={{ padding: 8, textAlign: "right" }}>Usage</th>
              </tr>
            </thead>
            <tbody>
              {breakdownQ.data.tasks?.map((t: any) => (
                <tr key={t.task_id} style={{ borderBottom: "1px solid #ddd" }}>
                  <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}>
                    {t.task_id.slice(0, 12)}...
                  </td>
                  <td style={{ padding: 8, textAlign: "right" }}>${t.cost}</td>
                  <td style={{ padding: 8, textAlign: "right" }}>{t.calls}</td>
                  <td style={{ padding: 8, textAlign: "right", color: t.is_over_budget ? "red" : t.needs_downgrade ? "orange" : "green" }}>
                    {t.usage_pct}%
                  </td>
                </tr>
              ))}
              {(!breakdownQ.data.tasks || breakdownQ.data.tasks.length === 0) && (
                <tr><td colSpan={4} style={{ padding: 16, textAlign: "center", color: "#999" }}>No tasks yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
