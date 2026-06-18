import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPendingApprovals, respondApproval } from "../api/client";

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["approvals"],
    queryFn: getPendingApprovals,
    refetchInterval: 5000,
  });

  const mutation = useMutation({
    mutationFn: ({ taskId, decision }: { taskId: string; decision: string }) =>
      respondApproval(taskId, decision, ""),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
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
        </div>
      ))}
    </div>
  );
}
