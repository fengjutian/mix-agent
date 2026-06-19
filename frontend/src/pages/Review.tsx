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
  getFileTree,
  searchCode,
  getChecklists,
} from "../api/client";
import DirectoryPicker from "../components/DirectoryPicker";

type LeftTab = "tree" | "commits";
type RightTab = "diff" | "file";

interface Branch {
  name: string; is_current: boolean; is_remote: boolean;
  last_commit_short: string; last_commit_message: string;
}
interface Commit {
  sha: string; short_sha: string; author: string; date: string;
  message: string; refs: string[];
}
interface ChangedFile {
  file_path: string; change_type: string; additions: number; deletions: number;
}
interface BlameLine {
  line_number: number; content: string; short_sha: string;
  author: string; date: string; summary: string;
}
interface TreeEntry {
  name: string; path: string; is_dir: boolean;
}
interface SearchResult {
  file: string; line: number | string; content: string;
}
interface ChecklistItem {
  id: string; label: string; hint: string;
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
    changed_files: ChangedFile[]; total_additions: number;
    total_deletions: number; raw_diff: string;
  } | null>(null);

  // Right panel
  const [rightTab, setRightTab] = useState<RightTab>("diff");
  const [leftTab, setLeftTab] = useState<LeftTab>("commits");
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
  repoPathRef.current = repoPath;

  // ── New features state ──
  const [sideBySide, setSideBySide] = useState(false);
  const [reviewedFiles, setReviewedFiles] = useState<Set<string>>(new Set());
  const [compareBase, setCompareBase] = useState("main");
  const [compareTarget, setCompareTarget] = useState("HEAD");
  // File tree
  const [treeEntries, setTreeEntries] = useState<TreeEntry[]>([]);
  const [treePath, setTreePath] = useState("");
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  // Search
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  // Checklist
  const [checklist, setChecklist] = useState<ChecklistItem[]>([]);
  const [checkedItems, setCheckedItems] = useState<Set<string>>(new Set());
  // File history
  const [fileHistory, setFileHistory] = useState<Commit[]>([]);
  const [showFileHistory, setShowFileHistory] = useState("");

  // ── Load branches ──
  const loadBranches = useCallback(async (caller = "") => {
    const rp = repoPathRef.current;
    console.log("[Review] loadBranches called by:", caller, "| repoPathRef:", rp);
    try {
      setBranchError("");
      const data = await listBranches(false, rp);
      console.log("[Review] loadBranches OK | path:", rp, "| branches:", data.total, "| current:", data.current);
      setBranches(data.branches);
      setCurrentBranch(data.current);
      setCommits([]);
      if (data.current) {
        const commitData = await listCommits({ branch: data.current, max_count: 50, repo_path: rp });
        setCommits(commitData.commits);
      }
    } catch (e: any) {
      setBranchError(e?.message || String(e));
      console.error("[Review] loadBranches FAIL", e);
    }
  }, []);

  const loadStatus = useCallback(async (caller = "") => {
    const rp = repoPathRef.current;
    try {
      const data = await getRepoStatus(rp);
      setStatusDirty(!data.is_clean);
      setStatusItems(data.status_items);
    } catch (e) { console.error("[Review] loadStatus FAIL", e); }
  }, []);

  useEffect(() => { loadBranches("mount"); loadStatus("mount"); }, [loadBranches, loadStatus]);
  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  // ── File Tree ──
  const loadTree = useCallback(async (dir: string = "") => {
    try {
      const data = await getFileTree(dir, "HEAD", repoPathRef.current);
      setTreeEntries(data.entries);
      setTreePath(dir);
    } catch { /* best effort */ }
  }, []);

  const toggleDir = async (entry: TreeEntry) => {
    const key = entry.path;
    if (expandedDirs.has(key)) {
      setExpandedDirs(prev => { const n = new Set(prev); n.delete(key); return n; });
    } else {
      setExpandedDirs(prev => new Set(prev).add(key));
      // Load sub-tree — just expand, tree is flat-loaded
    }
  };

  // ── Code Search ──
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const data = await searchCode(searchQuery.trim(), repoPathRef.current);
      setSearchResults(data.results);
    } catch { setSearchResults([]); }
    finally { setSearchLoading(false); }
  };

  // ── Review Progress ──
  const toggleReviewed = (fpath: string) => {
    setReviewedFiles(prev => {
      const n = new Set(prev);
      n.has(fpath) ? n.delete(fpath) : n.add(fpath);
      return n;
    });
  };
  const totalFiles = commitDetail?.changed_files.length || 0;
  const progressPct = totalFiles > 0 ? Math.round((reviewedFiles.size / totalFiles) * 100) : 0;

  // ── Report Export ──
  const handleExport = (format: "md" | "json") => {
    if (!commitDetail) return;
    let content = "";
    if (format === "json") {
      content = JSON.stringify({
        repo: repoPathRef.current,
        commit: selectedCommit,
        files: commitDetail.changed_files.map(f => ({
          ...f, reviewed: reviewedFiles.has(f.file_path)
        })),
        checklist: checklist.map(c => ({ ...c, checked: checkedItems.has(c.id) })),
        exported_at: new Date().toISOString(),
      }, null, 2);
    } else {
      content = `# 审查报告\n\n**仓库**: ${repoPathRef.current}\n**提交**: ${selectedCommit?.short_sha} ${selectedCommit?.message}\n**时间**: ${new Date().toLocaleString()}\n\n## 变更文件 (${commitDetail.changed_files.length})\n\n`;
      commitDetail.changed_files.forEach(f => {
        content += `- [${reviewedFiles.has(f.file_path) ? "x" : " "}] \`${f.file_path}\` (+${f.additions}/-${f.deletions})\n`;
      });
      if (checklist.length > 0) {
        content += `\n## 审查清单\n\n`;
        checklist.forEach(c => {
          content += `- [${checkedItems.has(c.id) ? "x" : " "}] ${c.label}\n`;
        });
      }
    }
    const blob = new Blob([content], { type: format === "json" ? "application/json" : "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `review-report.${format}`; a.click();
    URL.revokeObjectURL(url);
  };

  // ── File History ──
  const handleFileHistory = async (fpath: string) => {
    setShowFileHistory(fpath);
    try {
      const data = await listCommits({ file_path: fpath, max_count: 50, repo_path: repoPathRef.current });
      setFileHistory(data.commits);
    } catch { setFileHistory([]); }
  };

  // ── Load Checklist ──
  useEffect(() => {
    getChecklists().then(d => {
      const dl = d.checklists?.["default"] || d.checklists?.[Object.keys(d.checklists)[0]];
      if (dl?.items) setChecklist(dl.items);
    }).catch(() => {});
  }, []);

  // ── Handlers ──
  const handleCheckout = async (branch: string) => {
    if (statusDirty && !window.confirm("工作区有未提交变更，确定切换吗？")) return;
    try {
      await checkoutBranch(branch, false, repoPath);
      await loadBranches();
      await loadStatus();
    } catch (e: any) { alert("切换分支失败: " + e.message); }
  };

  const handleSelectCommit = async (commit: Commit) => {
    setSelectedCommit(commit);
    setRightTab("diff");
    setReviewedFiles(new Set());
    try {
      const data = await getCommitDetail(commit.sha, repoPath);
      setCommitDetail({
        changed_files: data.commit.changed_files,
        total_additions: data.commit.total_additions,
        total_deletions: data.commit.total_deletions,
        raw_diff: data.raw_diff,
      });
    } catch { setCommitDetail(null); }
  };

  const handleOpenFile = async (fpath: string) => {
    setFilePath(fpath); setRightTab("file"); setFileLoading(true); setBlameLines([]);
    try {
      const [fileData, blameData] = await Promise.all([
        readFile(fpath, fileRevision, repoPath),
        blameFile(fpath, fileRevision, undefined, undefined, repoPath),
      ]);
      setFileContent(fileData.content); setBlameLines(blameData.lines);
    } catch (e: any) { setFileContent(`// Error: ${e.message}`); }
    finally { setFileLoading(false); }
  };

  const handleDiffCurrent = async () => {
    setSelectedCommit(null); setRightTab("diff"); setReviewedFiles(new Set());
    try {
      const data = await getDiffs("HEAD", currentBranch || "main", repoPath);
      setCommitDetail({
        changed_files: data.changed_files, total_additions: data.total_additions,
        total_deletions: data.total_deletions, raw_diff: data.raw_diff,
      });
    } catch { setCommitDetail(null); }
  };

  const handleCompareCommits = async () => {
    setSelectedCommit(null); setRightTab("diff"); setReviewedFiles(new Set());
    try {
      const data = await getDiffs(compareTarget, compareBase, repoPath);
      setCommitDetail({
        changed_files: data.changed_files, total_additions: data.total_additions,
        total_deletions: data.total_deletions, raw_diff: data.raw_diff,
      });
    } catch { setCommitDetail(null); }
  };

  const detectLang = (fpath: string): string => {
    if (fpath.endsWith(".py")) return "python";
    if (fpath.endsWith(".ts") || fpath.endsWith(".tsx")) return "typescript";
    if (fpath.endsWith(".js") || fpath.endsWith(".jsx")) return "javascript";
    if (fpath.endsWith(".json")) return "json";
    if (fpath.endsWith(".sql")) return "sql";
    if (fpath.endsWith(".css")) return "css";
    if (fpath.endsWith(".html")) return "html";
    if (fpath.endsWith(".yaml") || fpath.endsWith(".yml")) return "yaml";
    if (fpath.endsWith(".md")) return "markdown";
    return "plaintext";
  };

  // ── Render ──
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* ── Toolbar ── */}
      <div className="card" style={{ marginBottom: 8, padding: "8px 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div className="form-group" style={{ margin: 0, flex: "0 0 250px" }}>
            <label className="form-label" style={{ fontSize: "0.7rem", marginBottom: 1 }}>仓库路径</label>
            <DirectoryPicker
              value={repoPath}
              onChange={(newPath) => {
                setRepoPath(newPath);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => { loadBranches("debounce"); loadStatus("debounce"); }, 600);
              }}
              onSelectRepo={(repo) => {
                if (debounceRef.current) clearTimeout(debounceRef.current);
                setRepoPath(repo); repoPathRef.current = repo;
                loadBranches("onSelectRepo"); loadStatus("onSelectRepo");
              }}
            />
          </div>
          <div className="form-group" style={{ margin: 0, flex: "0 0 160px" }}>
            <label className="form-label" style={{ fontSize: "0.7rem", marginBottom: 1 }}>
              分支 {statusDirty && <span style={{ color: "var(--danger)" }}>●</span>}
            </label>
            <select className="form-input" style={{ padding: "3px 6px", fontSize: "0.8rem" }} value={currentBranch}
              onChange={(e) => handleCheckout(e.target.value)}>
              {branches.map((b) => (
                <option key={b.name} value={b.name}>{b.name}{b.is_current ? " (current)" : ""}{b.is_remote ? " [remote]" : ""}</option>
              ))}
            </select>
          </div>
          {branchError && <span style={{ color: "var(--danger)", fontSize: "0.7rem" }}>⚠ {branchError}</span>}
          <div style={{ flex: 1 }} />
          <button className="btn btn--ghost btn--sm" onClick={handleDiffCurrent}>📊 当前 Diff</button>
          <button className="btn btn--ghost btn--sm" onClick={() => { loadBranches(); loadStatus(); }}>🔄 刷新</button>
          {commitDetail && (
            <>
              <button className="btn btn--ghost btn--sm" onClick={() => handleExport("md")}>📥 MD</button>
              <button className="btn btn--ghost btn--sm" onClick={() => handleExport("json")}>📥 JSON</button>
            </>
          )}
        </div>

        {/* Row 2: Search + side-by-side toggle + progress */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 4, flex: "0 0 260px" }}>
            <input className="form-input" style={{ padding: "3px 8px", fontSize: "0.78rem", flex: 1 }}
              placeholder="搜索代码... (Enter)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button className="btn btn--ghost btn--sm" onClick={handleSearch} disabled={searchLoading}>
              {searchLoading ? "..." : "🔍"}
            </button>
          </div>
          <label style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
            <input type="checkbox" checked={sideBySide} onChange={(e) => setSideBySide(e.target.checked)} />
            并排 Diff
          </label>
          {progressPct > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.72rem" }}>
              <span style={{ color: "var(--text-muted)" }}>进度</span>
              <div style={{ width: 100, height: 8, background: "rgba(255,255,255,0.08)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${progressPct}%`, height: "100%", background: "var(--accent)", borderRadius: 4, transition: "width 200ms" }} />
              </div>
              <span>{reviewedFiles.size}/{totalFiles}</span>
            </div>
          )}
        </div>

        {/* Search results */}
        {searchResults.length > 0 && (
          <div style={{ marginTop: 6, maxHeight: 150, overflow: "auto", background: "var(--bg-surface)", borderRadius: 6, padding: "4px 8px" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>
              搜索结果 ({searchResults.length})
              <button className="btn btn--ghost btn--sm" style={{ marginLeft: 8 }} onClick={() => setSearchResults([])}>✕</button>
            </div>
            {searchResults.map((r, i) => (
              <div key={i} style={{ display: "flex", gap: 8, padding: "2px 0", fontSize: "0.75rem", fontFamily: "monospace", cursor: "pointer" }}
                onClick={() => { setFilePath(r.file); handleOpenFile(r.file); setSearchResults([]); }}>
                <span style={{ color: "var(--text-link)" }}>{r.file}:{r.line}</span>
                <span style={{ color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.content}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Commit Comparison ── */}
      <div className="card" style={{ marginBottom: 8, padding: "6px 12px", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>提交对比</span>
        <input className="form-input" style={{ padding: "2px 6px", fontSize: "0.75rem", width: 100, fontFamily: "monospace" }}
          placeholder="base" value={compareBase} onChange={(e) => setCompareBase(e.target.value)} />
        <span style={{ fontSize: "0.75rem" }}>..</span>
        <input className="form-input" style={{ padding: "2px 6px", fontSize: "0.75rem", width: 100, fontFamily: "monospace" }}
          placeholder="target" value={compareTarget} onChange={(e) => setCompareTarget(e.target.value)} />
        <button className="btn btn--primary btn--sm" onClick={handleCompareCommits}>对比</button>
      </div>

      {/* ── Main content ── */}
      <div style={{ flex: 1, display: "flex", gap: 8, minHeight: 0 }}>
        {/* ── Left Panel ── */}
        <div className="card" style={{ width: 300, minWidth: 220, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Left Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", padding: "0 6px", flexShrink: 0 }}>
            {(["commits", "tree"] as LeftTab[]).map((tab) => (
              <button key={tab} onClick={() => { setLeftTab(tab); if (tab === "tree") loadTree(); }}
                className="btn btn--ghost btn--sm"
                style={{
                  borderBottom: leftTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                  borderRadius: 0, marginBottom: -1, fontWeight: leftTab === tab ? 600 : 400,
                }}>
                {tab === "commits" ? "提交历史" : "文件树"}
              </button>
            ))}
          </div>

          {/* Commits Tab */}
          {leftTab === "commits" && (
            <div style={{ flex: 1, overflow: "auto" }}>
              <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: "0.8rem", display: "flex", justifyContent: "space-between" }}>
                <span>提交 ({commits.length})</span>
                {commitsLoading && <span style={{ color: "var(--text-muted)" }}>...</span>}
              </div>
              {commits.map((commit) => (
                <div key={commit.sha} onClick={() => handleSelectCommit(commit)}
                  style={{ padding: "8px 10px", cursor: "pointer", borderBottom: "1px solid var(--border)",
                    background: selectedCommit?.sha === commit.sha ? "var(--bg-active)" : "transparent" }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 2 }}>
                    <span className="badge badge--info" style={{ fontSize: "0.7rem", fontFamily: "monospace" }}>{commit.short_sha}</span>
                    {commit.refs.length > 0 && <span className="badge badge--warning" style={{ fontSize: "0.6rem" }}>{commit.refs.join(", ")}</span>}
                  </div>
                  <div style={{ fontSize: "0.8rem", fontWeight: 500 }}>{commit.message}</div>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
                    <span>{commit.author}</span><span>{commit.date?.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* File Tree Tab */}
          {leftTab === "tree" && (
            <div style={{ flex: 1, overflow: "auto" }}>
              <div style={{ padding: "4px 8px", borderBottom: "1px solid var(--border)" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "monospace" }}>{treePath || "/"}</span>
                {treePath && (
                  <button className="btn btn--ghost btn--sm" style={{ marginLeft: 6, padding: "0 4px", fontSize: "0.7rem" }}
                    onClick={() => { const parent = treePath.split("/").slice(0, -1).join("/"); loadTree(parent); }}>
                    ↑
                  </button>
                )}
              </div>
              {treeEntries.length === 0 && (
                <div style={{ padding: 12, textAlign: "center", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  点击「文件树」标签加载
                </div>
              )}
              {treeEntries.map((entry) => (
                <div key={entry.path}
                  onClick={entry.is_dir ? () => loadTree(entry.path) : () => handleOpenFile(entry.path)}
                  style={{ padding: "4px 8px 4px " + (8 + (entry.path.split("/").length - 1) * 12) + "px",
                    cursor: "pointer", display: "flex", alignItems: "center", gap: 4, fontSize: "0.78rem",
                    borderBottom: "1px solid rgba(255,255,255,0.02)" }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
                  <span>{entry.is_dir ? "📁" : "📄"}</span>
                  <span style={{ fontFamily: entry.is_dir ? "inherit" : "monospace" }}>{entry.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right Panel ── */}
        <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Right Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", padding: "0 8px", flexShrink: 0 }}>
            {(["diff", "file"] as RightTab[]).map((tab) => (
              <button key={tab} onClick={() => setRightTab(tab)} className="btn btn--ghost btn--sm"
                style={{
                  borderBottom: rightTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
                  borderRadius: 0, marginBottom: -1, fontWeight: rightTab === tab ? 600 : 400,
                }}>
                {tab === "diff" ? "差异对比" : "文件查看"}
              </button>
            ))}
          </div>

          {/* Diff Tab */}
          {rightTab === "diff" && (
            <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
              {/* Diff content */}
              <div style={{ flex: 1, overflow: "auto" }}>
                {commitDetail ? (
                  <div>
                    {/* Commit info */}
                    <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", background: "var(--bg-surface)" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                        {selectedCommit ? `${selectedCommit.short_sha} ${selectedCommit.message}` : `${compareBase}..${compareTarget}`}
                      </div>
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2, display: "flex", gap: 12 }}>
                        {selectedCommit && <><span>{selectedCommit.author}</span><span>{selectedCommit.date?.slice(0, 19).replace("T", " ")}</span></>}
                        <span style={{ color: "var(--success)" }}>+{commitDetail.total_additions}</span>
                        <span style={{ color: "var(--danger)" }}>-{commitDetail.total_deletions}</span>
                        <span>{commitDetail.changed_files.length} 个文件</span>
                      </div>
                    </div>

                    {/* Changed files */}
                    <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border)", maxHeight: 160, overflow: "auto" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.78rem", marginBottom: 4 }}>变更文件</div>
                      {commitDetail.changed_files.map((cf, i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: "2px 0", fontSize: "0.76rem" }}>
                          <input type="checkbox" checked={reviewedFiles.has(cf.file_path)}
                            onChange={() => toggleReviewed(cf.file_path)}
                            style={{ cursor: "pointer", margin: 0 }} title="标记已审查" />
                          <span className={`badge ${cf.change_type === "added" ? "badge--success" : cf.change_type === "deleted" ? "badge--danger" : cf.change_type === "renamed" ? "badge--warning" : "badge--info"}`}
                            style={{ fontSize: "0.6rem", minWidth: 40, textAlign: "center" }}>{cf.change_type}</span>
                          <span style={{ flex: 1, cursor: "pointer", color: "var(--text-link)", fontFamily: "monospace", fontSize: "0.76rem" }}
                            onClick={() => handleOpenFile(cf.file_path)} title="查看文件">{cf.file_path}</span>
                          <span style={{ cursor: "pointer", fontSize: "0.65rem", color: "var(--text-muted)" }}
                            onClick={() => handleFileHistory(cf.file_path)} title="文件历史">📜</span>
                          <span style={{ fontSize: "0.7rem", whiteSpace: "nowrap" }}>
                            <span style={{ color: "var(--success)" }}>+{cf.additions}</span>/<span style={{ color: "var(--danger)" }}>-{cf.deletions}</span>
                          </span>
                        </div>
                      ))}
                    </div>

                    {/* File history popup */}
                    {showFileHistory && (
                      <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border)", background: "var(--bg-surface)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                          <span style={{ fontSize: "0.75rem", fontWeight: 600, fontFamily: "monospace" }}>{showFileHistory} 历史</span>
                          <button className="btn btn--ghost btn--sm" onClick={() => setShowFileHistory("")}>✕</button>
                        </div>
                        <div style={{ maxHeight: 120, overflow: "auto" }}>
                          {fileHistory.map(c => (
                            <div key={c.sha} style={{ fontSize: "0.7rem", padding: "1px 0", fontFamily: "monospace" }}>
                              <span style={{ color: "var(--accent)" }}>{c.short_sha}</span>{" "}
                              <span style={{ color: "var(--text-muted)" }}>{c.message}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Diff */}
                    <div style={{ height: commitDetail.changed_files.length > 5 ? "calc(100vh - 520px)" : "calc(100vh - 380px)" }}>
                      {commitDetail.raw_diff ? (
                        sideBySide ? (
                          <Editor
                            height="100%"
                            language="diff"
                            original={""}
                            modified={commitDetail.raw_diff}
                            theme={MIX_AGENT_DARK}
                            beforeMount={registerMixAgentTheme}
                            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 11, lineNumbers: "on",
                              scrollBeyondLastLine: false, wordWrap: "on", renderSideBySide: true }}
                          />
                        ) : (
                          <Editor
                            height="100%"
                            language="diff"
                            value={commitDetail.raw_diff}
                            theme={MIX_AGENT_DARK}
                            beforeMount={registerMixAgentTheme}
                            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, lineNumbers: "on",
                              scrollBeyondLastLine: false, wordWrap: "on", renderWhitespace: "none" }}
                          />
                        )
                      ) : (
                        <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>选择提交查看差异</div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>选择提交或使用「提交对比」</div>
                )}
              </div>

              {/* Checklist sidebar */}
              {checklist.length > 0 && (
                <div style={{ width: 170, minWidth: 150, borderLeft: "1px solid var(--border)", padding: "8px 10px", overflow: "auto", background: "var(--bg-surface)" }}>
                  <div style={{ fontWeight: 600, fontSize: "0.75rem", marginBottom: 8 }}>审查清单</div>
                  {checklist.map(item => (
                    <label key={item.id} style={{ display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 6, cursor: "pointer", fontSize: "0.72rem" }}
                      title={item.hint}>
                      <input type="checkbox" checked={checkedItems.has(item.id)}
                        onChange={() => {
                          setCheckedItems(prev => { const n = new Set(prev); n.has(item.id) ? n.delete(item.id) : n.add(item.id); return n; });
                        }}
                        style={{ marginTop: 1, flexShrink: 0 }} />
                      <span>{item.label}</span>
                    </label>
                  ))}
                  <div style={{ marginTop: 8, fontSize: "0.65rem", color: "var(--text-muted)" }}>
                    {checkedItems.size}/{checklist.length} 完成
                  </div>
                </div>
              )}
            </div>
          )}

          {/* File Tab */}
          {rightTab === "file" && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div style={{ padding: "6px 12px", borderBottom: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center" }}>
                <input className="form-input" style={{ flex: 1, padding: "4px 8px", fontSize: "0.78rem", fontFamily: "monospace" }}
                  placeholder="文件路径" value={filePath}
                  onChange={(e) => setFilePath(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleOpenFile(filePath)} />
                <input className="form-input" style={{ width: 100, padding: "4px 6px", fontSize: "0.78rem" }}
                  placeholder="revision" value={fileRevision} onChange={(e) => setFileRevision(e.target.value)} />
                <button className="btn btn--primary btn--sm" disabled={!filePath || fileLoading}
                  onClick={() => handleOpenFile(filePath)}>{fileLoading ? "..." : "打开"}</button>
              </div>
              {fileContent ? (
                <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
                  <div id="blame-gutter" style={{ width: 200, minWidth: 200, overflow: "hidden", borderRight: "1px solid var(--border)",
                    background: "var(--bg-surface)", fontFamily: "monospace", fontSize: 10, lineHeight: "18px" }}>
                    {blameLines.length > 0 ? blameLines.map((line) => (
                      <div key={line.line_number} style={{ display: "flex", padding: "0 4px", height: 18, borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                        <span style={{ fontWeight: 600, color: "var(--accent)", minWidth: 55, fontSize: 9 }}>{line.short_sha}</span>
                        <span style={{ color: "var(--text-muted)", fontSize: 9, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                          title={`${line.author} · ${line.date}`}>{line.author?.slice(0, 12)}</span>
                      </div>
                    )) : <div style={{ padding: "8px 4px", color: "var(--text-muted)", fontSize: 9 }}>加载 blame...</div>}
                  </div>
                  <div style={{ flex: 1 }}>
                    <Editor height="calc(100vh - 340px)" language={detectLang(filePath)} value={fileContent} theme="vs-dark"
                      onMount={(editor) => { editor.onDidScrollChange((e) => { const g = document.getElementById("blame-gutter"); if (g) g.scrollTop = e.scrollTop; }); }}
                      options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, lineNumbers: "on", scrollBeyondLastLine: false, wordWrap: "off" }} />
                  </div>
                </div>
              ) : (
                <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                  输入文件路径并点击「打开」
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      {statusDirty && (
        <div style={{ marginTop: 6, padding: "4px 10px", background: "var(--bg-surface)", borderRadius: 4, fontSize: "0.7rem", color: "var(--text-muted)", display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, color: "var(--warning)" }}>⚠ 未提交变更：</span>
          {statusItems.slice(0, 8).map((item, i) => (
            <span key={i}>{item.status} {item.file_path}</span>
          ))}
        </div>
      )}
    </div>
  );
}
