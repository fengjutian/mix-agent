import { useState, useEffect, useCallback, useRef } from "react";
import Editor from "@monaco-editor/react";
import { MIX_AGENT_DARK, registerMixAgentTheme } from "../monacoTheme";
import {
  listBranches,
  checkoutBranch,
  listCommits,
  getCommitDetail,
  readFile,
  blameFile,
  getDiffs,
  getRepoStatus,
} from "../api/client";
import DirectoryPicker from "../components/DirectoryPicker";

type RightTab = "diff" | "file";

interface Branch {
  name: string;
  is_current: boolean;
  is_remote: boolean;
  last_commit_short: string;
  last_commit_message: string;
}

interface Commit {
  sha: string;
  short_sha: string;
  author: string;
  date: string;
  message: string;
  refs: string[];
}

interface ChangedFile {
  file_path: string;
  change_type: string;
  additions: number;
  deletions: number;
}

interface BlameLine {
  line_number: number;
  content: string;
  short_sha: string;
  author: string;
  date: string;
  summary: string;
}

export default function ReviewPage() {
  // ── State ──
  const [repoPath, setRepoPath] = useState(".");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [currentBranch, setCurrentBranch] = useState("");
  const [commits, setCommits] = useState<Commit[]>([]);
  const [commitsLoading, setCommitsLoading] = useState(false);
  const [selectedCommit, setSelectedCommit] = useState<Commit | null>(null);
  const [commitDetail, setCommitDetail] = useState<{
    changed_files: ChangedFile[];
    total_additions: number;
    total_deletions: number;
    raw_diff: string;
  } | null>(null);

  // Right panel
  const [rightTab, setRightTab] = useState<RightTab>("diff");
  const [filePath, setFilePath] = useState("");
  const [fileContent, setFileContent] = useState("");
  const [fileRevision, setFileRevision] = useState("HEAD");
  const [fileLoading, setFileLoading] = useState(false);
  const [blameLines, setBlameLines] = useState<BlameLine[]>([]);

  // Status
  const [statusDirty, setStatusDirty] = useState(false);
  const [statusItems, setStatusItems] = useState<Array<{ file_path: string; status: string; staged: boolean }>>([]);
  const [branchError, setBranchError] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const repoPathRef = useRef(repoPath);
  repoPathRef.current = repoPath;  // 始终保持最新值

  // ── Load branches ── (成功后自动触发 loadCommits)
  const loadBranches = useCallback(async (caller = "") => {
    const rp = repoPathRef.current;
    console.log("[Review] loadBranches called by:", caller, "| repoPathRef:", rp);
    try {
      setBranchError("");
      const data = await listBranches(false, rp);
      console.log("[Review] loadBranches OK | path:", rp, "| branches:", data.total, "| current:", data.current, "| list:", data.branches.map(b => b.name));
      setBranches(data.branches);
      setCurrentBranch(data.current);
      // 分支加载成功后立即加载提交历史（即使是同一个分支名，仓库不同也需要刷新）
      setCommits([]);
      if (data.current) {
        const commitData = await listCommits({ branch: data.current, max_count: 50, repo_path: rp });
        setCommits(commitData.commits);
      }
    } catch (e: any) {
      const msg = e?.message || String(e);
      console.error("[Review] loadBranches FAIL | path:", rp, "| error:", msg);
      setBranchError(msg);
    }
  }, []);

  // ── Load commits ──
  const loadCommits = useCallback(async () => {
    setCommitsLoading(true);
    try {
      const data = await listCommits({ branch: currentBranch || "HEAD", max_count: 50, repo_path: repoPathRef.current });
      setCommits(data.commits);
    } catch (e) {
      console.error("Failed to load commits", e);
    } finally {
      setCommitsLoading(false);
    }
  }, [currentBranch]);

  // ── Load status ──
  const loadStatus = useCallback(async (caller = "") => {
    const rp = repoPathRef.current;
    console.log("[Review] loadStatus called by:", caller, "| repoPathRef:", rp);
    try {
      const data = await getRepoStatus(rp);
      console.log("[Review] loadStatus OK | dirty:", !data.is_clean, "| items:", data.status_items.length);
      setStatusDirty(!data.is_clean);
      setStatusItems(data.status_items);
    } catch (e) {
      console.error("[Review] loadStatus FAIL", e);
    }
  }, []);

  useEffect(() => {
    console.log("[Review] Mount — initial load");
    loadBranches("mount");
    loadStatus("mount");
  }, [loadBranches, loadStatus]);

  // 组件卸载时清理防抖定时器
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // ── Handlers ──
  const handleCheckout = async (branch: string) => {
    if (statusDirty && !window.confirm("工作区有未提交的变更，切换分支可能丢失进度。确定切换吗？")) {
      return;
    }
    try {
      await checkoutBranch(branch, false, repoPath);
      await loadBranches();
      await loadStatus();
    } catch (e: any) {
      alert("切换分支失败: " + e.message);
    }
  };

  const handleSelectCommit = async (commit: Commit) => {
    setSelectedCommit(commit);
    setRightTab("diff");
    try {
      const data = await getCommitDetail(commit.sha, repoPath);
      setCommitDetail({
        changed_files: data.commit.changed_files,
        total_additions: data.commit.total_additions,
        total_deletions: data.commit.total_deletions,
        raw_diff: data.raw_diff,
      });
    } catch {
      setCommitDetail(null);
    }
  };

  // ── Unified: 打开文件（同时加载内容和 blame） ──
  const handleOpenFile = async (fpath: string) => {
    setFilePath(fpath);
    setRightTab("file");
    setFileLoading(true);
    setBlameLines([]);
    try {
      const [fileData, blameData] = await Promise.all([
        readFile(fpath, fileRevision, repoPath),
        blameFile(fpath, fileRevision, undefined, undefined, repoPath),
      ]);
      setFileContent(fileData.content);
      setBlameLines(blameData.lines);
    } catch (e: any) {
      setFileContent(`// Error: ${e.message}`);
    } finally {
      setFileLoading(false);
    }
  };

  const handleDiffCurrent = async () => {
    setSelectedCommit(null);
    setRightTab("diff");
    try {
      const data = await getDiffs("HEAD", currentBranch || "main", repoPath);
      setCommitDetail({
        changed_files: data.changed_files,
        total_additions: data.total_additions,
        total_deletions: data.total_deletions,
        raw_diff: data.raw_diff,
      });
    } catch {
      setCommitDetail(null);
    }
  };

  const detectLang = (fpath: string): string => {
    if (fpath.endsWith(".py")) return "python";
    if (fpath.endsWith(".ts") || fpath.endsWith(".tsx")) return "typescript";
    if (fpath.endsWith(".js") || fpath.endsWith(".jsx")) return "javascript";
    if (fpath.endsWith(".rs")) return "rust";
    if (fpath.endsWith(".toml") || fpath.endsWith(".lock")) return "ini";
    if (fpath.endsWith(".json")) return "json";
    if (fpath.endsWith(".sql")) return "sql";
    if (fpath.endsWith(".yaml") || fpath.endsWith(".yml")) return "yaml";
    if (fpath.endsWith(".css")) return "css";
    if (fpath.endsWith(".html")) return "html";
    if (fpath.endsWith(".md")) return "markdown";
    if (fpath.endsWith(".sh") || fpath.endsWith(".ps1")) return "shell";
    if (fpath.endsWith(".dockerfile") || fpath.includes("Dockerfile")) return "dockerfile";
    return "plaintext";
  };

  // ── Render ──
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* ── Toolbar ── */}
      <div className="card" style={{ marginBottom: 12, padding: "12px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          {/* Repo path */}
          <div className="form-group" style={{ margin: 0, flex: "0 0 280px" }}>
            <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: 2 }}>
              仓库路径
            </label>
            <DirectoryPicker
              value={repoPath}
              onChange={(newPath) => {
                console.log("[Review] onChange (type) | newPath:", newPath);
                setRepoPath(newPath);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => {
                  console.log("[Review] debounce fired | path:", newPath);
                  loadBranches("debounce");
                  loadStatus("debounce");
                }, 600);
              }}
              onSelectRepo={(repo) => {
                console.log("[Review] onSelectRepo FIRED | repo:", repo);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                setRepoPath(repo);
                repoPathRef.current = repo;
                loadBranches("onSelectRepo");
                loadStatus("onSelectRepo");
              }}
            />
          </div>

          {/* Branch selector */}
          <div className="form-group" style={{ margin: 0, flex: "0 0 200px" }}>
            <label className="form-label" style={{ fontSize: "0.75rem", marginBottom: 2 }}>
              分支 {statusDirty && <span style={{ color: "var(--danger)" }}>● 有未提交变更</span>}
              {branchError && <span style={{ color: "var(--danger)", fontSize: "0.72rem", marginLeft: 8 }}>⚠ {branchError}</span>}
            </label>
            <select
              className="form-input"
              style={{ padding: "4px 8px", fontSize: "0.82rem" }}
              value={currentBranch}
              onChange={(e) => handleCheckout(e.target.value)}
            >
              {branches.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}{b.is_current ? " (current)" : ""}{b.is_remote ? " [remote]" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Actions */}
          <div style={{ flex: 1 }} />
          <button className="btn btn--ghost btn--sm" onClick={handleDiffCurrent}>
            📊 当前 Diff
          </button>
          <button className="btn btn--ghost btn--sm" onClick={() => { loadBranches(); loadCommits(); loadStatus(); }}>
            🔄 刷新
          </button>
        </div>
      </div>

      {/* ── Main content: left commits + right detail ── */}
      <div style={{ flex: 1, display: "flex", gap: 12, minHeight: 0 }}>
        {/* ── Left: Commit list ── */}
        <div
          className="card"
          style={{
            width: 360,
            minWidth: 280,
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
              display: "flex",
              justifyContent: "space-between",
            }}
          >
            <span>提交历史 ({commits.length})</span>
            {commitsLoading && <span style={{ color: "var(--text-muted)" }}>加载中...</span>}
          </div>
          <div style={{ flex: 1, overflow: "auto" }}>
            {commits.map((commit) => (
              <div
                key={commit.sha}
                onClick={() => handleSelectCommit(commit)}
                className="list-item"
                style={{
                  cursor: "pointer",
                  padding: "10px 14px",
                  borderBottom: "1px solid var(--border)",
                  background:
                    selectedCommit?.sha === commit.sha
                      ? "var(--bg-active)"
                      : "transparent",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span
                    className="badge badge--info"
                    style={{ fontFamily: "monospace", fontSize: "0.75rem" }}
                  >
                    {commit.short_sha}
                  </span>
                  {commit.refs.length > 0 && (
                    <span className="badge badge--warning" style={{ fontSize: "0.7rem" }}>
                      {commit.refs.join(", ")}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "0.85rem", fontWeight: 500, marginBottom: 2 }}>
                  {commit.message}
                </div>
                <div
                  style={{
                    fontSize: "0.72rem",
                    color: "var(--text-muted)",
                    display: "flex",
                    justifyContent: "space-between",
                  }}
                >
                  <span>{commit.author}</span>
                  <span>{commit.date?.slice(0, 10)}</span>
                </div>
              </div>
            ))}
            {commits.length === 0 && !commitsLoading && (
              <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                暂无提交记录
              </div>
            )}
          </div>
        </div>

        {/* ── Right: Detail panel with tabs ── */}
        <div
          className="card"
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* Tabs */}
          <div
            style={{
              display: "flex",
              borderBottom: "1px solid var(--border)",
              padding: "0 8px",
            }}
          >
            {(["diff", "file"] as RightTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                className="btn btn--ghost btn--sm"
                style={{
                  borderBottom:
                    rightTab === tab
                      ? "2px solid var(--accent)"
                      : "2px solid transparent",
                  borderRadius: 0,
                  marginBottom: -1,
                  fontWeight: rightTab === tab ? 600 : 400,
                }}
              >
                {tab === "diff" ? "差异对比" : "文件查看"}
              </button>
            ))}
          </div>

          {/* Diff Tab */}
          {rightTab === "diff" && (
            <div style={{ flex: 1, overflow: "auto" }}>
              {selectedCommit ? (
                <div>
                  {/* Commit info */}
                  <div
                    style={{
                      padding: "12px 16px",
                      borderBottom: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: "0.95rem", marginBottom: 4 }}>
                      {selectedCommit.message}
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "flex", gap: 16 }}>
                      <span>{selectedCommit.short_sha}</span>
                      <span>{selectedCommit.author}</span>
                      <span>{selectedCommit.date?.slice(0, 19).replace("T", " ")}</span>
                    </div>
                    {commitDetail && (
                      <div style={{ marginTop: 8, fontSize: "0.78rem", display: "flex", gap: 12 }}>
                        <span style={{ color: "var(--success)" }}>+{commitDetail.total_additions}</span>
                        <span style={{ color: "var(--danger)" }}>-{commitDetail.total_deletions}</span>
                        <span style={{ color: "var(--text-muted)" }}>
                          {commitDetail.changed_files.length} 个文件
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Changed files list */}
                  {commitDetail && (
                    <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border)" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.82rem", marginBottom: 6 }}>
                        变更文件
                      </div>
                      {commitDetail.changed_files.map((cf, i) => (
                        <div
                          key={i}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "3px 0",
                            fontSize: "0.82rem",
                          }}
                        >
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
                            style={{ fontSize: "0.65rem", minWidth: 50, textAlign: "center" }}
                          >
                            {cf.change_type}
                          </span>
                          <span
                            style={{
                              flex: 1,
                              cursor: "pointer",
                              color: "var(--text-link)",
                              fontFamily: "monospace",
                              fontSize: "0.8rem",
                            }}
                            onClick={() => handleOpenFile(cf.file_path)}
                            title="点击查看文件（含 Blame）"
                          >
                            {cf.file_path}
                          </span>
                          <span style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                            <span style={{ color: "var(--success)" }}>+{cf.additions}</span>/
                            <span style={{ color: "var(--danger)" }}>-{cf.deletions}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Diff content */}
                  <div style={{ padding: 0 }}>
                    {commitDetail?.raw_diff ? (
                      <Editor
                        height="calc(100vh - 420px)"
                        language="diff"
                        value={commitDetail.raw_diff}
                        theme={MIX_AGENT_DARK}
                        beforeMount={registerMixAgentTheme}
                        options={{
                          readOnly: true,
                          minimap: { enabled: false },
                          fontSize: 12,
                          lineNumbers: "on",
                          scrollBeyondLastLine: false,
                          wordWrap: "on",
                          // 统一 diff 着色
                          renderWhitespace: "none",
                        }}
                      />
                    ) : (
                      <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                        选择一个 commit 查看差异，或点击「当前 Diff」查看工作区变更
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                  选择左侧提交查看详情，或点击「当前 Diff」查看工作区变更
                </div>
              )}
            </div>
          )}

          {/* File Tab — 统一视图：左侧 Blame + 右侧代码 */}
          {rightTab === "file" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              {/* Toolbar */}
              <div
                style={{
                  padding: "8px 16px",
                  borderBottom: "1px solid var(--border)",
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                }}
              >
                <input
                  className="form-input"
                  style={{ flex: 1, padding: "4px 8px", fontSize: "0.82rem", fontFamily: "monospace" }}
                  placeholder="文件路径，如 src/mix_agent/main.py"
                  value={filePath}
                  onChange={(e) => setFilePath(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleOpenFile(filePath)}
                />
                <input
                  className="form-input"
                  style={{ width: 120, padding: "4px 8px", fontSize: "0.82rem" }}
                  placeholder="revision"
                  value={fileRevision}
                  onChange={(e) => setFileRevision(e.target.value)}
                />
                <button
                  className="btn btn--primary btn--sm"
                  disabled={!filePath || fileLoading}
                  onClick={() => handleOpenFile(filePath)}
                >
                  {fileLoading ? "加载中..." : "打开"}
                </button>
              </div>

              {/* Content area */}
              {fileContent ? (
                <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
                  {/* Blame gutter — left */}
                  <div
                    id="blame-gutter"
                    style={{
                      width: 200,
                      minWidth: 200,
                      overflow: "hidden",
                      borderRight: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                      fontFamily: "monospace",
                      fontSize: 11,
                      lineHeight: "18px",
                    }}
                  >
                    {blameLines.length > 0 ? (
                      blameLines.map((line) => (
                        <div
                          key={line.line_number}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            padding: "0 6px",
                            height: 18,
                            borderBottom: "1px solid rgba(255,255,255,0.03)",
                          }}
                        >
                          <span
                            style={{
                              fontWeight: 600,
                              color: "var(--accent)",
                              marginRight: 6,
                              minWidth: 60,
                              fontSize: 10,
                            }}
                          >
                            {line.short_sha}
                          </span>
                          <span
                            style={{
                              color: "var(--text-muted)",
                              fontSize: 10,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                            title={`${line.author} · ${line.date}`}
                          >
                            {line.author?.slice(0, 14)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div style={{ padding: "10px 6px", color: "var(--text-muted)", fontSize: 10 }}>
                        加载 blame...
                      </div>
                    )}
                  </div>

                  {/* Code editor — right */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Editor
                      height="calc(100vh - 340px)"
                      language={detectLang(filePath)}
                      value={fileContent}
                      theme="vs-dark"
                      onMount={(editor) => {
                        // 同步滚动：编辑器滚动时更新 blame gutter
                        editor.onDidScrollChange((e) => {
                          const gutter = document.getElementById("blame-gutter");
                          if (gutter) {
                            gutter.scrollTop = e.scrollTop;
                          }
                        });
                      }}
                      options={{
                        readOnly: true,
                        minimap: { enabled: false },
                        fontSize: 13,
                        lineNumbers: "on",
                        scrollBeyondLastLine: false,
                        wordWrap: "off",
                      }}
                    />
                  </div>
                </div>
              ) : (
                <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                  输入文件路径并点击「打开」，或从提交详情中点击文件名
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Status bar info ── */}
      {statusDirty && (
        <div
          style={{
            marginTop: 8,
            padding: "6px 12px",
            background: "var(--bg-surface)",
            borderRadius: 6,
            fontSize: "0.78rem",
            color: "var(--text-muted)",
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontWeight: 600, color: "var(--warning)" }}>⚠ 工作区有未提交变更：</span>
          {statusItems.slice(0, 10).map((item, i) => (
            <span key={i}>
              {item.status} {item.file_path}
            </span>
          ))}
          {statusItems.length > 10 && <span>...以及其他 {statusItems.length - 10} 项</span>}
        </div>
      )}
    </div>
  );
}
