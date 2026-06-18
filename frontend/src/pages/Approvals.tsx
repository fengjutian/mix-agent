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

  if (isLoading) return <p>Loading...</p>;
  if (error) return <p style={{ color: "red" }}>{(error as Error).message}</p>;

  const items = data?.items || [];

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", padding: 24 }}>
      <h1>Pending Approvals ({data?.total || 0})</h1>
      {items.length === 0 && <p>No pending approvals.</p>}
      {items.map((item: any, i: number) => (
        <div key={i} style={{
          padding: 16, marginBottom: 12, borderRadius: 8,
          background: "#fff3e0", border: "1px solid #ff9800"
        }}>
          <p><strong>Task:</strong> {item.task_id}</p>
          <p><strong>Node:</strong> {item.node_name}</p>
          <p>{item.prompt}</p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              onClick={() => mutation.mutate({ taskId: item.task_id, decision: "approve" })}
              style={{ padding: "8px 20px", background: "#4caf50", color: "#fff", border: "none", borderRadius: 4 }}
            >
              Approve
            </button>
            <button
              onClick={() => mutation.mutate({ taskId: item.task_id, decision: "reject" })}
              style={{ padding: "8px 20px", background: "#f44336", color: "#fff", border: "none", borderRadius: 4 }}
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
