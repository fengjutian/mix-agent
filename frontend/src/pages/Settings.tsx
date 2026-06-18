import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCostOverview, getCostBreakdown } from "../api/client";
import { useAuthStore } from "../stores/auth";

export default function SettingsPage() {
  const overviewQ = useQuery({ queryKey: ["cost-overview"], queryFn: getCostOverview });
  const breakdownQ = useQuery({ queryKey: ["cost-breakdown"], queryFn: getCostBreakdown });

  const overview = overviewQ.data;
  const breakdown = breakdownQ.data;

  return (
    <div>
      <h1>设置</h1>

      {/* ── Lock Screen Password ── */}
      <LockPasswordSection />

      <h1 style={{ marginTop: 40 }}>成本概览</h1>

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

// ── Lock Screen Password Section ──

type LockMode = "view" | "set" | "change" | "remove";

interface LockFormProps {
  error: string;
  onCancel: () => void;
}

function SetPasswordForm({ error, onCancel, onSubmit }: LockFormProps & { onSubmit: (password: string, confirm: string) => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(password, confirm); }}>
      <div className="form-group">
        <label className="form-label">新密码</label>
        <input className="form-input" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)} autoFocus />
      </div>
      <div className="form-group">
        <label className="form-label">确认密码</label>
        <input className="form-input" type="password" value={confirm}
          onChange={(e) => setConfirm(e.target.value)} />
      </div>
      {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn btn--primary btn--sm">确认</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>取消</button>
      </div>
    </form>
  );
}

function ChangePasswordForm({ error, onCancel, onSubmit }: LockFormProps & { onSubmit: (current: string, next: string, confirm: string) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(current, next, confirm); }}>
      <div className="form-group">
        <label className="form-label">当前密码</label>
        <input className="form-input" type="password" value={current}
          onChange={(e) => setCurrent(e.target.value)} autoFocus />
      </div>
      <div className="form-group">
        <label className="form-label">新密码</label>
        <input className="form-input" type="password" value={next}
          onChange={(e) => setNext(e.target.value)} />
      </div>
      <div className="form-group">
        <label className="form-label">确认新密码</label>
        <input className="form-input" type="password" value={confirm}
          onChange={(e) => setConfirm(e.target.value)} />
      </div>
      {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn btn--primary btn--sm">确认</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>取消</button>
      </div>
    </form>
  );
}

function RemovePasswordForm({ error, onCancel, onSubmit }: LockFormProps & { onSubmit: (current: string) => void }) {
  const [current, setCurrent] = useState("");

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(current); }}>
      <div className="form-group">
        <label className="form-label">输入当前密码以确认移除</label>
        <input className="form-input" type="password" value={current}
          onChange={(e) => setCurrent(e.target.value)} autoFocus />
      </div>
      {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" className="btn btn--danger btn--sm">确认移除</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>取消</button>
      </div>
    </form>
  );
}

function LockPasswordSection() {
  const { hasPassword, setPassword, changePassword, removePassword } = useAuthStore();

  const [mode, setMode] = useState<LockMode>("view");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const reset = () => {
    setError("");
    setOk("");
  };

  return (
    <div className="card">
      <div className="card__header">
        <h2 style={{ margin: 0 }}>锁屏密码</h2>
      </div>

      {ok && (
        <div className="result-banner result-banner--success" style={{ marginBottom: 16 }}>
          {ok}
        </div>
      )}

      {mode === "view" && (
        <div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
            {hasPassword
              ? "锁屏密码已设置。锁定屏幕后需要输入密码才能解锁。"
              : "尚未设置锁屏密码。设置后可通过顶部「锁定屏幕」按钮锁屏。"}
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            {!hasPassword ? (
              <button className="btn btn--primary btn--sm" onClick={() => { reset(); setMode("set"); }}>
                设置密码
              </button>
            ) : (
              <>
                <button className="btn btn--secondary btn--sm" onClick={() => { reset(); setMode("change"); }}>
                  修改密码
                </button>
                <button className="btn btn--danger btn--sm" onClick={() => { reset(); setMode("remove"); }}>
                  移除密码
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {mode === "set" && (
        <SetPasswordForm
          error={error}
          onCancel={() => { setMode("view"); reset(); }}
          onSubmit={(password, confirm) => {
            setError("");
            if (!password || password.length < 1) { setError("密码不能为空"); return; }
            if (password !== confirm) { setError("两次输入不一致"); return; }
            const result = setPassword(password);
            if (!result.ok) { setError(result.error ?? "设置失败"); return; }
            setOk("锁屏密码已设置");
            setMode("view");
            reset();
          }}
        />
      )}

      {mode === "change" && (
        <ChangePasswordForm
          error={error}
          onCancel={() => { setMode("view"); reset(); }}
          onSubmit={(current, next, confirm) => {
            setError("");
            if (!next || next.length < 1) { setError("新密码不能为空"); return; }
            if (next !== confirm) { setError("两次输入不一致"); return; }
            const result = changePassword(current, next);
            if (!result.ok) { setError(result.error ?? "修改失败"); return; }
            setOk("密码已更改");
            setMode("view");
            reset();
          }}
        />
      )}

      {mode === "remove" && (
        <RemovePasswordForm
          error={error}
          onCancel={() => { setMode("view"); reset(); }}
          onSubmit={(current) => {
            setError("");
            const result = removePassword(current);
            if (!result.ok) { setError(result.error ?? "移除失败"); return; }
            setOk("锁屏密码已移除");
            setMode("view");
            reset();
          }}
        />
      )}
    </div>
  );
}
