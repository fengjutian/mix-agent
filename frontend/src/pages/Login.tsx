import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await login(username, password);
      navigate("/");
    } catch (err: any) {
      setError(err.message || "Login failed");
    }
  };

  return (
    <div className="page-shell">
      <div style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "clamp(16px, 4vw, 32px)",
      }}>
        <div style={{ width: "100%", maxWidth: 400 }}>
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 10,
              fontSize: "1.4rem",
              fontWeight: 650,
              color: "var(--text-heading)",
              letterSpacing: "-0.3px",
            }}>
              <span style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: "var(--accent)",
                boxShadow: "0 0 14px var(--accent-glow)",
              }} />
              mix-agent
            </div>
          </div>

          <div className="card">
            <h2 style={{ textAlign: "center", marginTop: 0 }}>Sign In</h2>

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input
                  className="form-input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin / auditor / developer"
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label className="form-label">Password</label>
                <input
                  className="form-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}

              <button type="submit" className="btn btn--primary btn--lg btn--block">
                Sign In
              </button>
            </form>
          </div>

          <p style={{
            textAlign: "center",
            marginTop: 20,
            color: "var(--text-muted)",
            fontSize: "0.8rem",
          }}>
            Demo: admin/admin123, auditor/auditor123, developer/dev123
          </p>
        </div>
      </div>
    </div>
  );
}
