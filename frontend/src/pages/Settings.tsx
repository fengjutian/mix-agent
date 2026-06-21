import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCostOverview, getCostBreakdown, getGlobalSettings, updateGlobalSettings } from "../api/client";
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

      {/* ── Global Application Settings ── */}
      <GlobalSettingsSection />

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

// ── Global Application Settings Section ──

const SETTING_FIELDS: Array<{
  key: string;
  label: string;
  hint: string;
  type: "number" | "boolean" | "text";
  min?: number;
  step?: number;
}> = [
  { key: "token_burst_limit", label: "Token 突发限制", hint: "短时间允许的最大 token 消耗量", type: "number", min: 1000, step: 1000 },
  { key: "token_refill_rate", label: "Token 补充速率", hint: "每秒补充的 token 数量", type: "number", min: 100, step: 100 },
  { key: "sandbox_timeout", label: "沙箱超时 (秒)", hint: "Docker 沙箱执行超时时间", type: "number", min: 5, step: 5 },
  { key: "sandbox_cpu_limit", label: "沙箱 CPU 限制", hint: "每个沙箱容器的 CPU 核数", type: "number", min: 0.5, step: 0.5 },
  { key: "sandbox_memory_limit", label: "沙箱内存限制", hint: "例如 512m、1g", type: "text" },
  { key: "sqlguard_enabled", label: "SQL 安全门禁", hint: "是否启用 SQL 安全检查", type: "boolean" },
  { key: "sqlguard_block_ddl", label: "阻断 DDL", hint: "是否阻断数据定义语句（DROP/ALTER/TRUNCATE）", type: "boolean" },
  { key: "sqlguard_block_unconditional_dml", label: "阻断无条件 DML", hint: "是否阻断无条件更新/删除", type: "boolean" },
  { key: "agent_max_concurrency", label: "Agent 最大并发", hint: "同时运行的最大 Agent 任务数", type: "number", min: 1, step: 1 },
  { key: "default_project_dir", label: "默认项目目录", hint: "AI 分析等功能的默认项目根目录", type: "text" },
];

function GlobalSettingsSection() {
  const queryClient = useQueryClient();
  const settingsQ = useQuery({ queryKey: ["global-settings"], queryFn: getGlobalSettings });
  const mutation = useMutation({
    mutationFn: updateGlobalSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["global-settings"] });
    },
  });

  const [editValues, setEditValues] = useState<Record<string, any>>({});
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [error, setError] = useState("");

  const data = settingsQ.data?.data;

  const resetEdit = () => {
    setEditValues({});
    setEditingKey(null);
    setError("");
  };

  const startEdit = (key: string) => {
    if (data && (data as Record<string, any>)[key] !== undefined) {
      setEditValues({ [key]: (data as Record<string, any>)[key] });
      setEditingKey(key);
      setError("");
    }
  };

  const saveEdit = async () => {
    if (!editingKey) return;
    setError("");
    try {
      await mutation.mutateAsync(editValues);
      resetEdit();
    } catch (e: any) {
      setError(e?.message ?? "保存失败");
    }
  };

  const toggleBoolean = async (key: string, current: boolean) => {
    setError("");
    try {
      await mutation.mutateAsync({ [key]: !current });
    } catch (e: any) {
      setError(e?.message ?? "保存失败");
    }
  };

  return (
    <div className="card" style={{ marginTop: 28 }}>
      <div className="card__header">
        <h2 style={{ margin: 0 }}>全局应用设置</h2>
      </div>

      {error && (
        <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>
      )}

      {settingsQ.isLoading && <div className="loading">加载设置中...</div>}
      {settingsQ.error && <div className="error-message">{(settingsQ.error as Error).message}</div>}

      {data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {SETTING_FIELDS.map((f) => {
            const value = (data as Record<string, any>)[f.key];
            const isEditing = editingKey === f.key;

            if (f.type === "boolean") {
              return (
                <div
                  key={f.key}
                  className="settings-row"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 0",
                    borderTop: "1px solid var(--border-subtle)",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{f.label}</div>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{f.hint}</div>
                  </div>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={!!value}
                      onChange={() => toggleBoolean(f.key, !!value)}
                      disabled={mutation.isPending}
                    />
                    <span className="toggle__slider" />
                  </label>
                </div>
              );
            }

            // number / text
            return (
              <div
                key={f.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 0",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{f.label}</div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{f.hint}</div>
                </div>

                {isEditing ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input
                      className="form-input"
                      style={{ width: 140, padding: "4px 8px", fontSize: "0.85rem" }}
                      type={f.type === "number" ? "number" : "text"}
                      min={f.min}
                      step={f.step}
                      value={editValues[f.key] ?? ""}
                      onChange={(e) => {
                        const raw = e.target.value;
                        setEditValues({
                          [f.key]: f.type === "number" ? (raw === "" ? "" : Number(raw)) : raw,
                        });
                      }}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEdit();
                        if (e.key === "Escape") resetEdit();
                      }}
                    />
                    <button
                      className="btn btn--primary btn--sm"
                      onClick={saveEdit}
                      disabled={mutation.isPending}
                      style={{ padding: "4px 10px" }}
                    >
                      ✓
                    </button>
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={resetEdit}
                      style={{ padding: "4px 10px" }}
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <code style={{ fontSize: "0.88rem" }}>
                      {value ?? "—"}
                    </code>
                    <button
                      className="btn btn--ghost btn--sm"
                      onClick={() => startEdit(f.key)}
                      style={{ padding: "2px 8px", fontSize: "0.75rem" }}
                    >
                      编辑
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {settingsQ.data?.updated_at && (
        <div style={{
          marginTop: 16,
          color: "var(--text-muted)",
          fontSize: "0.75rem",
        }}>
          最后更新: {new Date(settingsQ.data.updated_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}
