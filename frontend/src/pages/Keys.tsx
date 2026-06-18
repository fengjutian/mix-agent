import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getKeys, setKey, deleteKey } from "../api/client";
import { useState } from "react";

export default function KeysPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["keys"],
    queryFn: getKeys,
  });

  const setMutation = useMutation({
    mutationFn: ({
      provider,
      api_key,
      base_url,
      model,
    }: {
      provider: string;
      api_key: string;
      base_url: string;
      model: string;
    }) => setKey(provider, api_key, base_url, model),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["keys"] });
      queryClient.invalidateQueries({ queryKey: ["models"] });
      setAddOpen(false);
      setEditingProvider(null);
      setAddFeedback({ ok: true, msg: editingProvider ? "密钥已更新" : "密钥已保存" });
      setTimeout(() => setAddFeedback(null), 2500);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (provider: string) => deleteKey(provider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["keys"] });
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const [addOpen, setAddOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [addFeedback, setAddFeedback] = useState<{
    ok: boolean;
    msg: string;
  } | null>(null);
  const [formProvider, setFormProvider] = useState("");
  const [formKey, setFormKey] = useState("");
  const [formBaseUrl, setFormBaseUrl] = useState("");
  const [formModel, setFormModel] = useState("");
  const [showKey, setShowKey] = useState(false);

  if (isLoading) return <div className="loading">加载密钥中…</div>;
  if (error) return <div className="error-message">加载 API 密钥失败</div>;
  if (!data) return null;

  const handleSave = () => {
    const provider = formProvider.trim();
    const key = formKey.trim();
    if (!provider) return;
    // 添加模式必须填密钥；编辑模式允许留空（仅更新 base_url / model）
    if (!editingProvider && !key) return;
    // 编辑模式下密钥留空则后端保留原值
    setMutation.mutate({
      provider,
      api_key: key,
      base_url: formBaseUrl.trim(),
      model: formModel.trim(),
    });
  };

  const handleDelete = (provider: string) => {
    if (window.confirm(`确定删除 "${provider}" 的 API 密钥？`)) {
      deleteMutation.mutate(provider);
    }
  };

  const resetForm = () => {
    setFormProvider("");
    setFormKey("");
    setFormBaseUrl("");
    setFormModel("");
    setShowKey(false);
    setEditingProvider(null);
  };

  const startEdit = (k: {
    provider: string;
    base_url: string;
    model: string;
  }) => {
    setFormProvider(k.provider);
    setFormKey("");
    setFormBaseUrl(k.base_url || "");
    setFormModel(k.model || "");
    setShowKey(false);
    setEditingProvider(k.provider);
    setAddOpen(true);
  };

  return (
    <div>
      <h1>API 密钥</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        管理 LLM 提供商的 API 密钥。密钥保存至{" "}
        <code>config/provider_keys.json</code>，启动时与{" "}
        <code>.env</code> 一同加载。
      </p>

      {/* ── Key list ── */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card__header">
          <h3 style={{ margin: 0 }}>已配置的提供商</h3>
          <button
            className="btn btn--primary btn--sm"
            onClick={() => {
              resetForm();
              setAddOpen(true);
            }}
          >
            + 添加密钥
          </button>
        </div>

        {data.keys.length === 0 && (
          <p className="empty-state">
            未配置 API 密钥，添加一个开始吧。
          </p>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.keys.map((k) => (
            <div
              key={k.provider}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 14px",
                borderRadius: "var(--radius)",
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
              }}
            >
              <div>
                <strong style={{ color: "var(--text-heading)" }}>
                  {k.provider}
                </strong>
                {k.model && (
                  <span
                    style={{
                      marginLeft: 10,
                      color: "var(--text-muted)",
                      fontSize: "0.85rem",
                      fontFamily: "var(--mono)",
                    }}
                  >
                    {k.model}
                  </span>
                )}
                {k.base_url && (
                  <span
                    style={{
                      marginLeft: 10,
                      color: "var(--text-muted)",
                      fontSize: "0.75rem",
                    }}
                  >
                    ({k.base_url})
                  </span>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <code
                  style={{
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                    fontFamily: "var(--mono)",
                  }}
                >
                  {k.api_key_masked || "（空）"}
                </code>
                <span
                  className={`badge ${k.has_key ? "badge--success" : "badge--warning"}`}
                  style={{ fontSize: "0.65rem" }}
                >
                  {k.has_key ? "已设置" : "无密钥"}
                </span>
                <button
                  className="btn btn--ghost btn--sm"
                  style={{ padding: "2px 8px" }}
                  onClick={() => startEdit(k)}
                >
                  编辑
                </button>
                <button
                  className="btn btn--ghost btn--sm"
                  style={{ color: "var(--danger)", padding: "2px 8px" }}
                  onClick={() => handleDelete(k.provider)}
                  disabled={deleteMutation.isPending}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Add / Edit form ── */}
      {addOpen && (
        <div className="card">
          <div className="card__header">
            <h3 style={{ margin: 0 }}>
              {editingProvider ? `编辑 API 密钥 — ${editingProvider}` : "添加 API 密钥"}
            </h3>
          </div>

          {addFeedback && (
            <div
              style={{
                padding: "8px 14px",
                marginBottom: 12,
                borderRadius: "var(--radius)",
                fontSize: "0.85rem",
                background: addFeedback.ok
                  ? "var(--success-bg, #e6ffed)"
                  : "var(--danger-bg, #ffeef0)",
                color: addFeedback.ok ? "var(--success)" : "var(--danger)",
              }}
            >
              {addFeedback.msg}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">提供商 *</label>
            <input
              className="form-input"
              placeholder="e.g. openai, anthropic, minimax"
              value={formProvider}
              onChange={(e) => setFormProvider(e.target.value)}
              disabled={!!editingProvider}
            />
          </div>

          <div className="form-group">
            <label className="form-label">
              API 密钥{editingProvider ? "（留空则不修改）" : " *"}
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="form-input"
                type={showKey ? "text" : "password"}
                placeholder="sk-…"
                value={formKey}
                onChange={(e) => setFormKey(e.target.value)}
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setShowKey(!showKey)}
                style={{ whiteSpace: "nowrap" }}
              >
                {showKey ? "隐藏" : "显示"}
              </button>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Base URL</label>
              <input
                className="form-input"
                placeholder="https://api.openai.com/v1"
                value={formBaseUrl}
                onChange={(e) => setFormBaseUrl(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">模型</label>
              <input
                className="form-input"
                placeholder="gpt-4o"
                value={formModel}
                onChange={(e) => setFormModel(e.target.value)}
              />
            </div>
          </div>

          <div
            style={{
              display: "flex",
              gap: 8,
              justifyContent: "flex-end",
              marginTop: 12,
            }}
          >
            <button
              className="btn btn--secondary btn--sm"
              onClick={() => {
                setAddOpen(false);
                setAddFeedback(null);
                setEditingProvider(null);
              }}
            >
              取消
            </button>
            <button
              className="btn btn--primary"
              onClick={handleSave}
              disabled={
                setMutation.isPending ||
                !formProvider.trim() ||
                (!editingProvider && !formKey.trim())
              }
            >
              {setMutation.isPending
                ? "保存中…"
                : editingProvider
                  ? "更新密钥"
                  : "保存密钥"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
