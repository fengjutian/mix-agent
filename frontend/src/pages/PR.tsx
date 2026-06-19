import { useState } from "react";
import Editor from "@monaco-editor/react";
import { MIX_AGENT_DARK, registerMixAgentTheme } from "../monacoTheme";
import { listPRs, getPRDetail, getGitToken, setGitToken } from "../api/client";

interface PRItem {
  number: number;
  title: string;
  description: string;
  state: string;
  source_branch: string;
  target_branch: string;
  author: string;
  url: string;
  created_at: string;
  updated_at: string;
  platform: string;
}

interface PRDetail {
  number: number;
  title: string;
  description: string;
  state: string;
  source_branch: string;
  target_branch: string;
  author: string;
  url: string;
  platform: string;
  changed_files: Array<{
    file_path: string;
    change_type: string;
    additions: number;
    deletions: number;
  }>;
  raw_diff: string;
  total_additions: number;
  total_deletions: number;
}

export default function PRPage() {
  const [repoUrl, setRepoUrl] = useState("");
  const [prs, setPRs] = useState<PRItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Token
  const [platform, setPlatform] = useState("github");
  const [token, setToken] = useState("");
  const [tokenStatus, setTokenStatus] = useState("");

  // Detail
  const [selectedPR, setSelectedPR] = useState<PRDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const handleLoadPRs = async () => {
    if (!repoUrl.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await listPRs(repoUrl.trim());
      setPRs(data.prs);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleViewPR = async (pr: PRItem) => {
    setDetailLoading(true);
    try {
      const data = await getPRDetail(pr.number, repoUrl.trim());
      setSelectedPR(data.pr);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleSetToken = async () => {
    if (!token.trim()) return;
    try {
      const data = await setGitToken(platform, token.trim());
      if (data.ok) {
        setTokenStatus("Token 已保存");
        setToken("");
      } else {
        setTokenStatus(data.error || "保存失败");
      }
    } catch (e: any) {
      setTokenStatus(e?.message || "Error");
    }
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <h1 style={{ margin: "0 0 16px", fontSize: "1.1rem" }}>PR 监控</h1>

      {/* Token Config */}
      <div className="card" style={{ marginBottom: 16, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>API Token</span>
          <select
            className="form-input"
            style={{ width: 100, padding: "4px 8px", fontSize: "0.82rem" }}
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="github">GitHub</option>
            <option value="gitlab">GitLab</option>
          </select>
          <input
            className="form-input"
            style={{ width: 260, padding: "4px 8px", fontSize: "0.82rem" }}
            placeholder={platform === "github" ? "ghp_xxx" : "glpat-xxx"}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSetToken()}
          />
          <button className="btn btn--primary btn--sm" onClick={handleSetToken}>
            保存
          </button>
          {tokenStatus && (
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {tokenStatus}
            </span>
          )}
        </div>
      </div>

      {/* Repo URL + Load */}
      <div className="card" style={{ marginBottom: 16, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <input
            className="form-input"
            style={{ flex: 1, padding: "6px 10px", fontSize: "0.85rem" }}
            placeholder="仓库 URL，如 https://github.com/owner/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLoadPRs()}
          />
          <button
            className="btn btn--primary"
            disabled={loading || !repoUrl.trim()}
            onClick={handleLoadPRs}
          >
            {loading ? "加载中..." : "加载 PR"}
          </button>
        </div>
        {error && (
          <div style={{ marginTop: 8, color: "var(--danger)", fontSize: "0.82rem" }}>
            {error}
          </div>
        )}
      </div>

      {/* Content: PR list + Detail */}
      <div style={{ flex: 1, display: "flex", gap: 12, minHeight: 0 }}>
        {/* PR List */}
        <div
          className="card"
          style={{
            width: 340,
            minWidth: 260,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
              fontWeight: 600,
              fontSize: "0.88rem",
            }}
          >
            Pull Requests ({prs.length})
          </div>
          <div style={{ flex: 1, overflow: "auto" }}>
            {prs.map((pr) => (
              <div
                key={`${pr.platform}-${pr.number}`}
                onClick={() => handleViewPR(pr)}
                style={{
                  padding: "10px 14px",
                  cursor: "pointer",
                  borderBottom: "1px solid var(--border)",
                  background:
                    selectedPR?.number === pr.number
                      ? "var(--bg-active)"
                      : "transparent",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span
                    className={`badge ${
                      pr.state === "open" ? "badge--success" : pr.state === "merged" ? "badge--info" : "badge--danger"
                    }`}
                    style={{ fontSize: "0.7rem" }}
                  >
                    #{pr.number}
                  </span>
                  <span className="badge badge--warning" style={{ fontSize: "0.65rem" }}>
                    {pr.platform}
                  </span>
                </div>
                <div style={{ fontSize: "0.85rem", fontWeight: 500, marginBottom: 2 }}>
                  {pr.title}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  {pr.source_branch} → {pr.target_branch} · {pr.author}
                </div>
              </div>
            ))}
            {prs.length === 0 && !loading && (
              <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                输入仓库 URL 并点击「加载 PR」
              </div>
            )}
          </div>
        </div>

        {/* PR Detail */}
        <div
          className="card"
          style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}
        >
          {detailLoading ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
              加载中...
            </div>
          ) : selectedPR ? (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              {/* PR Info Header */}
              <div
                style={{
                  padding: "12px 16px",
                  borderBottom: "1px solid var(--border)",
                  background: "var(--bg-surface)",
                }}
              >
                <div style={{ fontWeight: 600, fontSize: "0.95rem", marginBottom: 4 }}>
                  #{selectedPR.number} {selectedPR.title}
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "flex", gap: 16 }}>
                  <span>{selectedPR.author}</span>
                  <span>{selectedPR.source_branch} → {selectedPR.target_branch}</span>
                  <a
                    href={selectedPR.url}
                    target="_blank"
                    rel="noopener"
                    style={{ color: "var(--text-link)" }}
                  >
                    {selectedPR.platform === "github" ? "GitHub" : "GitLab"} ↗
                  </a>
                </div>
                {selectedPR.description && (
                  <div style={{ marginTop: 6, fontSize: "0.82rem", color: "var(--text-muted)", whiteSpace: "pre-wrap" }}>
                    {selectedPR.description.slice(0, 300)}
                    {selectedPR.description.length > 300 && "..."}
                  </div>
                )}
                <div style={{ marginTop: 6, fontSize: "0.78rem", display: "flex", gap: 12 }}>
                  <span style={{ color: "var(--success)" }}>+{selectedPR.total_additions}</span>
                  <span style={{ color: "var(--danger)" }}>-{selectedPR.total_deletions}</span>
                  <span style={{ color: "var(--text-muted)" }}>
                    {selectedPR.changed_files.length} 个文件
                  </span>
                </div>
              </div>

              {/* Changed Files */}
              <div
                style={{
                  padding: "8px 16px",
                  borderBottom: "1px solid var(--border)",
                  maxHeight: 120,
                  overflow: "auto",
                }}
              >
                <div style={{ fontWeight: 600, fontSize: "0.8rem", marginBottom: 4 }}>变更文件</div>
                {selectedPR.changed_files.map((cf, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "2px 0", fontSize: "0.8rem" }}>
                    <span
                      className={`badge ${
                        cf.change_type === "added"
                          ? "badge--success"
                          : cf.change_type === "deleted"
                          ? "badge--danger"
                          : cf.change_type === "renamed"
                          ? "badge--warning"
                          : "badge--info"
                      }`}
                      style={{ fontSize: "0.6rem", minWidth: 45, textAlign: "center" }}
                    >
                      {cf.change_type}
                    </span>
                    <span style={{ flex: 1, fontFamily: "monospace", fontSize: "0.78rem" }}>
                      {cf.file_path}
                    </span>
                    <span style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                      <span style={{ color: "var(--success)" }}>+{cf.additions}</span>/
                      <span style={{ color: "var(--danger)" }}>-{cf.deletions}</span>
                    </span>
                  </div>
                ))}
              </div>

              {/* Diff */}
              <div style={{ flex: 1, minHeight: 0 }}>
                {selectedPR.raw_diff ? (
                  <Editor
                    height="calc(100vh - 420px)"
                    language="diff"
                    value={selectedPR.raw_diff}
                    theme={MIX_AGENT_DARK}
                    beforeMount={registerMixAgentTheme}
                    options={{
                      readOnly: true,
                      minimap: { enabled: false },
                      fontSize: 12,
                      lineNumbers: "on",
                      scrollBeyondLastLine: false,
                      wordWrap: "on",
                      renderWhitespace: "none",
                    }}
                  />
                ) : (
                  <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                    无 diff 数据
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
              选择左侧 PR 查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
