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
    setResult(null);
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
    <div>
      <h1>New Audit Task</h1>

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Repository Path</label>
            <input
              className="form-input"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Target Branch</label>
              <input
                className="form-input"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Base Branch</label>
              <input
                className="form-input"
                value={base}
                onChange={(e) => setBase(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Description <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(optional)</span></label>
            <input
              className="form-input"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="e.g. Check user module SQL security"
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary btn--lg btn--block"
            disabled={loading}
          >
            {loading ? "Scanning..." : "Start Scan"}
          </button>
        </form>
      </div>

      {result && (
        <div style={{ marginTop: 20 }}>
          {result.error ? (
            <div className="result-banner result-banner--error">{result.error}</div>
          ) : (
            <div className="result-banner result-banner--success">
              Task created: <strong>{result.task_id}</strong> — Status:{" "}
              <span className="badge badge--info">{result.status}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
