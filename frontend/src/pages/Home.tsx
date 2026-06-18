import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createTask } from "../api/client";

export default function HomePage() {
  const [repo, setRepo] = useState(".");
  const [target, setTarget] = useState("HEAD");
  const [base, setBase] = useState("main");
  const [desc, setDesc] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await createTask({
        description: desc || `Scan ${base}..${target}`,
        target_branch: target,
        base_branch: base,
        repo_path: repo,
      });
      setResult(data);
      if (data.task_id) navigate(`/tasks/${data.task_id}`);
    } catch (err: any) {
      setResult({ error: err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: "40px auto", padding: 24 }}>
      <h1>New Audit Task</h1>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 12 }}>
          <label>Repository Path</label>
          <input value={repo} onChange={(e) => setRepo(e.target.value)}
            style={{ width: "100%", padding: 8, marginTop: 4 }} />
        </div>
        <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <label>Target Branch</label>
            <input value={target} onChange={(e) => setTarget(e.target.value)}
              style={{ width: "100%", padding: 8, marginTop: 4 }} />
          </div>
          <div style={{ flex: 1 }}>
            <label>Base Branch</label>
            <input value={base} onChange={(e) => setBase(e.target.value)}
              style={{ width: "100%", padding: 8, marginTop: 4 }} />
          </div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label>Description (optional)</label>
          <input value={desc} onChange={(e) => setDesc(e.target.value)}
            placeholder="e.g. Check user module SQL security"
            style={{ width: "100%", padding: 8, marginTop: 4 }} />
        </div>
        <button type="submit" disabled={loading}
          style={{ width: "100%", padding: 10, fontSize: 16 }}>
          {loading ? "Scanning..." : "Start Scan"}
        </button>
      </form>
      {result && (
        <div style={{ marginTop: 16, padding: 12, background: "#f0f0f0", borderRadius: 8 }}>
          {result.error ? (
            <p style={{ color: "red" }}>{result.error}</p>
          ) : (
            <p>Task created: <strong>{result.task_id}</strong> — Status: {result.status}</p>
          )}
        </div>
      )}
    </div>
  );
}
