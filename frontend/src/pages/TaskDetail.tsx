import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTask, getFindings, getReport } from "../api/client";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();

  const taskQ = useQuery({ queryKey: ["task", id], queryFn: () => getTask(id!) });
  const findingsQ = useQuery({ queryKey: ["findings", id], queryFn: () => getFindings(id!) });
  const reportQ = useQuery({ queryKey: ["report", id], queryFn: () => getReport(id!) });

  if (taskQ.isLoading) return <p>Loading...</p>;
  if (taskQ.error) return <p style={{ color: "red" }}>{(taskQ.error as Error).message}</p>;

  const task = taskQ.data;
  const findings = findingsQ.data?.findings || [];
  const report = reportQ.data;

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 24 }}>
      <h1>Task Detail</h1>
      <div style={{ background: "#f5f5f5", padding: 16, borderRadius: 8, marginBottom: 16 }}>
        <p><strong>ID:</strong> {task?.task_id}</p>
        <p><strong>Status:</strong> <span style={{
          color: task?.status === "completed" ? "green" :
                 task?.status === "failed" ? "red" : "orange"
        }}>{task?.status}</span></p>
        <p><strong>Branch:</strong> {task?.base_branch} → {task?.target_branch}</p>
      </div>

      <h2>Findings ({findingsQ.data?.total || 0})</h2>
      {findings.map((f: any, i: number) => (
        <div key={i} style={{
          padding: 12, marginBottom: 8, borderRadius: 6,
          borderLeft: `4px solid ${f.risk_level === "danger" ? "red" : f.risk_level === "warning" ? "orange" : "green"}`,
          background: "#fafafa"
        }}>
          <strong>[{f.risk_level?.toUpperCase()}]</strong> {f.agent}/{f.finding_type}
          <p style={{ margin: "4px 0 0", color: "#555" }}>{f.description}</p>
          {f.file_path && <small>{f.file_path}:{f.line_number}</small>}
        </div>
      ))}
      {findings.length === 0 && <p>No findings yet.</p>}

      {report && (
        <div style={{ marginTop: 24 }}>
          <h2>Report</h2>
          <pre style={{ background: "#f5f5f5", padding: 16, borderRadius: 8, overflow: "auto", maxHeight: 400 }}>
            {JSON.stringify(report, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
