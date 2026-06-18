import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPendingApprovals, getPendingApproval, respondApproval } from "../api/client";

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["approvals"],
    queryFn: getPendingApprovals,
    refetchInterval: 5000,
  });

  const [expandedId, setExpandedId] = useState<string | null>(null);

  const detailQ = useQuery({
    queryKey: ["approval-detail", expandedId],
    queryFn: () => getPendingApproval(expandedId!),
    enabled: !!expandedId,
  });

  const mutation = useMutation({
    mutationFn: ({ taskId, decision }: { taskId: string; decision: string }) =>
      respondApproval(taskId, decision, ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
      setExpandedId(null);
    },
  });

  if (isLoading) return <div className="loading">Loading approvals...</div>;
  if (error) return <div className="error-message">{(error as Error).message}</div>;

  const items = data?.items || [];

  return (
    <div>
      <h1>
        Pending Approvals
        {data?.total != null && (
          <span style={{
            marginLeft: 10,
            fontSize: "0.85rem",
            color: "var(--text-muted)",
            fontWeight: 400,
          }}>
            ({data.total})
          </span>
        )}
      </h1>

      {items.length === 0 && (
        <div className="empty-state">
          <div className="empty-state__icon">✅</div>
          <p>No pending approvals.</p>
        </div>
      )}

      {items.map((item: any, i: number) => (
        <div key={i} className="approval-card">
          <div className="approval-card__meta">
            <span><strong>Task:</strong> <code>{item.task_id?.slice(0, 14)}...</code></span>
            <span><strong>Node:</strong> {item.node_name}</span>
          </div>
          <p className="approval-card__prompt">{item.prompt}</p>
          <div className="approval-card__actions">
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => setExpandedId(expandedId === item.task_id ? null : item.task_id)}
            >
              {expandedId === item.task_id ? "Collapse" : "Details"}
            </button>
            <button
              className="btn btn--primary btn--sm"
              onClick={() => mutation.mutate({ taskId: item.task_id, decision: "approve" })}
              disabled={mutation.isPending}
            >
              Approve
            </button>
            <button
              className="btn btn--danger btn--sm"
              onClick={() => mutation.mutate({ taskId: item.task_id, decision: "reject" })}
              disabled={mutation.isPending}
            >
              Reject
            </button>
          </div>

          {/* ── Detail drill-down ── */}
          {expandedId === item.task_id && (
            <div style={{ marginTop: 12, padding: "12px 0 0 0", borderTop: "1px solid var(--border)" }}>
              {detailQ.isLoading && <span style={{ color: "var(--text-muted)" }}>Loading details...</span>}
              {detailQ.isError && (
                <span style={{ color: "var(--danger)" }}>{(detailQ.error as Error).message}</span>
              )}
              {detailQ.data && (
                <>
                  <p style={{ margin: "0 0 8px 0", fontSize: "0.85rem", fontWeight: 600 }}>
                    Danger items ({detailQ.data.context?.danger_count ?? 0}):
                  </p>
                  {(detailQ.data.context?.items || []).map((ri: any, j: number) => (
                    <div
                      key={j}
                      style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        padding: "8px 12px",
                        marginBottom: 6,
                        fontSize: "0.82rem",
                      }}
                    >
                      <div style={{ fontFamily: "var(--mono)", color: "var(--text-heading)", marginBottom: 4 }}>
                        {ri.file}
                      </div>
                      <code
                        style={{
                          display: "block",
                          background: "var(--bg-code)",
                          padding: "4px 8px",
                          borderRadius: 4,
                          fontSize: "0.78rem",
                          marginBottom: 4,
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-all",
                        }}
                      >
                        {ri.sql}
                      </code>
                      {ri.reasons?.length > 0 && (
                        <div style={{ color: "var(--danger)", fontSize: "0.78rem" }}>
                          {ri.reasons.join("; ")}
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
