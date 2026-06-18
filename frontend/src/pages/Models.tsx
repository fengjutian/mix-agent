import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getModels, assignModel } from "../api/client";
import { useState } from "react";

export default function ModelsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
  });

  const mutation = useMutation({
    mutationFn: ({ node, provider }: { node: string; provider: string }) =>
      assignModel(node, provider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const [feedback, setFeedback] = useState<{ node: string; ok: boolean } | null>(null);

  if (isLoading) return <div className="loading">Loading models…</div>;
  if (error) return <div className="error-message">Failed to load model config.</div>;
  if (!data) return null;

  const handleAssign = async (node: string, provider: string) => {
    const result = await mutation.mutateAsync({ node, provider });
    setFeedback({ node, ok: result.ok });
    setTimeout(() => setFeedback(null), 2500);
  };

  const providerOptions = data.models.map((m) => m.provider);
  // Also include providers from node assignments that might not be in models (e.g. unconfigured ones)
  const allProviders = [...new Set([...providerOptions, ...data.nodes.map((n) => n.provider)])];

  return (
    <div>
      <h1>Model Configuration</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        Assign each agent node to a registered LLM provider. Changes take effect immediately.
      </p>

      {/* Registered models */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card__header">
          <h3 style={{ margin: 0 }}>Registered Providers</h3>
        </div>
        {data.models.length === 0 && (
          <p className="empty-state">No models registered. Set API keys in .env.</p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.models.map((m) => (
            <div
              key={m.provider}
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
                <strong style={{ color: "var(--text-heading)" }}>{m.provider}</strong>
                <span style={{ marginLeft: 10, color: "var(--text-muted)", fontSize: "0.85rem", fontFamily: "var(--mono)" }}>
                  {m.model}
                </span>
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                ${m.input_price_per_m.toFixed(2)} / ${m.output_price_per_m.toFixed(2)} per 1M tokens
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Node assignments */}
      <div className="card">
        <div className="card__header">
          <h3 style={{ margin: 0 }}>Agent Node Assignments</h3>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            {data.nodes.filter((n) => n.overridden).length} overridden
          </span>
        </div>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Node</th>
                <th>Current Provider</th>
                <th>Model</th>
                <th style={{ width: 180 }}>Switch To</th>
              </tr>
            </thead>
            <tbody>
              {data.nodes.map((node) => (
                <tr key={node.node}>
                  <td>
                    <code>{node.node}</code>
                    {node.overridden && (
                      <span
                        className="badge badge--warning"
                        style={{ marginLeft: 8, fontSize: "0.65rem" }}
                      >
                        edited
                      </span>
                    )}
                  </td>
                  <td style={{ color: "var(--text-heading)", fontWeight: 600 }}>
                    {node.provider}
                  </td>
                  <td style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "0.82rem" }}>
                    {node.model}
                  </td>
                  <td>
                    <select
                      className="form-input"
                      style={{ padding: "4px 8px", fontSize: "0.82rem" }}
                      value={node.provider}
                      onChange={(e) => handleAssign(node.node, e.target.value)}
                      disabled={mutation.isPending}
                    >
                      {allProviders.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                    {feedback?.node === node.node && (
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: "0.72rem",
                          color: feedback.ok ? "var(--success)" : "var(--danger)",
                        }}
                      >
                        {feedback.ok ? "✓" : "✗"}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
