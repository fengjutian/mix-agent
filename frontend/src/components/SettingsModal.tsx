import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getGlobalSettings, updateGlobalSettings } from "../api/client";

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

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function SettingsModal({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const overlayRef = useRef<HTMLDivElement>(null);

  const settingsQ = useQuery({
    queryKey: ["global-settings"],
    queryFn: getGlobalSettings,
    enabled: open,
  });

  const mutation = useMutation({
    mutationFn: updateGlobalSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["global-settings"] });
    },
  });

  const [editKey, setEditKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");
  const [error, setError] = useState("");

  const data = settingsQ.data?.data;

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Close on overlay click
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  // ── Actions ──

  const resetEdit = () => {
    setEditKey(null);
    setEditValue("");
    setError("");
  };

  const startEdit = (key: string, current: any) => {
    setEditKey(key);
    setEditValue(String(current ?? ""));
    setError("");
  };

  const saveEdit = async () => {
    if (!editKey) return;
    setError("");
    const field = SETTING_FIELDS.find((f) => f.key === editKey);
    if (!field) return;
    let val: any = editValue;
    if (field.type === "number") {
      val = Number(editValue);
      if (isNaN(val)) { setError("请输入有效数字"); return; }
    }
    try {
      await mutation.mutateAsync({ [editKey]: val });
      resetEdit();
    } catch (e: any) {
      setError(e?.message ?? "保存失败");
    }
  };

  const toggleBoolean = async (key: string, current: boolean) => {
    try {
      await mutation.mutateAsync({ [key]: !current });
    } catch (e: any) {
      setError(e?.message ?? "保存失败");
    }
  };

  if (!open) return null;

  return (
    <div className="settings-modal-overlay" ref={overlayRef} onClick={handleOverlayClick}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="settings-modal__header">
          <h2 className="settings-modal__title">设置</h2>
          <button className="settings-modal__close" onClick={onClose} aria-label="关闭">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="settings-modal__error">{error}</div>
        )}

        {/* Body */}
        <div className="settings-modal__body">
          {settingsQ.isLoading && <div className="loading">加载设置中...</div>}
          {settingsQ.error && <div className="error-message">{(settingsQ.error as Error).message}</div>}

          {data && SETTING_FIELDS.map((f) => {
            const value = (data as Record<string, any>)[f.key];
            const isEditing = editKey === f.key;

            return (
              <div key={f.key} className="settings-row">
                <div className="settings-row__info">
                  <span className="settings-row__label">{f.label}</span>
                  <span className="settings-row__hint">{f.hint}</span>
                </div>

                <div className="settings-row__control">
                  {f.type === "boolean" ? (
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={!!value}
                        onChange={() => toggleBoolean(f.key, !!value)}
                        disabled={mutation.isPending}
                      />
                      <span className="toggle__slider" />
                    </label>
                  ) : isEditing ? (
                    <div className="settings-row__edit">
                      <input
                        className="form-input"
                        type={f.type === "number" ? "number" : "text"}
                        min={f.min}
                        step={f.step}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveEdit();
                          if (e.key === "Escape") resetEdit();
                        }}
                        autoFocus
                      />
                      <button className="btn btn--primary btn--sm" onClick={saveEdit} disabled={mutation.isPending}>
                        ✓
                      </button>
                      <button className="btn btn--ghost btn--sm" onClick={resetEdit}>
                        ✕
                      </button>
                    </div>
                  ) : (
                    <div className="settings-row__display">
                      <code>{String(value ?? "—")}</code>
                      <button className="btn btn--ghost btn--sm settings-row__edit-btn" onClick={() => startEdit(f.key, value)}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        {settingsQ.data?.updated_at && (
          <div className="settings-modal__footer">
            最后更新: {new Date(settingsQ.data.updated_at).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}
