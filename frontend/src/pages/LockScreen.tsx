import { useState } from "react";
import { useAuthStore } from "../stores/auth";

export default function LockScreen() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const unlock = useAuthStore((s) => s.unlock);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!unlock(password)) {
      setError("密码错误");
      setPassword("");
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-deep)",
        padding: "clamp(16px, 4vw, 32px)",
      }}
    >
      <div style={{ width: "100%", maxWidth: 380 }}>
        {/* Branding */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 10,
              fontSize: "1.4rem",
              fontWeight: 650,
              color: "var(--text-heading)",
              letterSpacing: "-0.3px",
            }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: "var(--accent)",
                boxShadow: "0 0 14px var(--accent-glow)",
              }}
            />
            mix-agent
          </div>
          <p style={{ marginTop: 12, color: "var(--text-muted)", fontSize: "0.85rem" }}>
            屏幕已锁定
          </p>
        </div>

        {/* Unlock form */}
        <div className="card">
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">输入密码解锁</label>
              <input
                className="form-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="锁屏密码"
                autoFocus
              />
            </div>

            {error && (
              <div className="error-message" style={{ marginBottom: 16 }}>
                {error}
              </div>
            )}

            <button type="submit" className="btn btn--primary btn--lg btn--block">
              解锁
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
