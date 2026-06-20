import { useState, useEffect, useCallback, useRef } from "react";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
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
  openInVSCode,
  aiReviewCommits,
  aiReviewResult,
} from "../api/client";
import DirectoryPicker from "../components/DirectoryPicker";
import { Input } from "../components/ui/input";
import { Checkbox, CheckboxIndicator } from "../components/ui/checkbox";
import { Badge } from "../components/ui/badge";
import { Select, SelectTrigger, SelectValue, SelectPopup, SelectItem } from "../components/ui/select";
import { Dialog, DialogContent, DialogTitle, DialogClose } from "../components/ui/dialog";
import { Button } from "../components/ui/button";

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

  // ── Multi-commit selection & AI review ──
  const [selectedCommits, setSelectedCommits] = useState<Set<string>>(new Set());
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewReport, setReviewReport] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewMeta, setReviewMeta] = useState<{
    commit_infos?: Array<{ sha: string; short_sha: string; author: string; message: string }>;
    changed_files?: Array<{ file_path: string; change_type: string; additions: number; deletions: number }>;
    total_additions?: number;
    total_deletions?: number;
    model?: string;
    tokens?: { prompt: number; completion: number; total: number };
  } | null>(null);
  const pendingExportUrl = useRef<string | null>(null);

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
        setCommitsLoading(true);
        const commitData = await listCommits({ branch: data.current, max_count: 50, repo_path: rp });
        setCommits(commitData.commits);
      }
    } catch (e: any) {
      setBranchError(e?.message || String(e));
      console.error("[Review] loadBranches FAIL", e);
    } finally {
      setCommitsLoading(false);
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

  // ── Multi-commit selection ──
  const toggleCommitSelection = (sha: string) => {
    setSelectedCommits(prev => {
      const next = new Set(prev);
      if (next.has(sha)) next.delete(sha); else next.add(sha);
      return next;
    });
  };

  const clearSelection = () => setSelectedCommits(new Set());

  // ── AI Review handler (async: submit → poll) ──
  const handleAiReview = async () => {
    if (selectedCommits.size === 0) return;
    setReviewModalOpen(true);
    setReviewLoading(true);
    setReviewReport(null);
    setReviewError(null);
    setReviewMeta(null);
    try {
      // 1) Submit review task
      const { task_id } = await aiReviewCommits({
        commit_shas: Array.from(selectedCommits),
        repo_path: repoPathRef.current,
      });

      // 2) Poll for result (max 120s)
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 2000));  // 2s interval
        const data = await aiReviewResult(task_id);
        if (data.status === "processing") continue;

        // Completed or failed
        if (data.ok && data.report) {
          setReviewReport(data.report);
          setReviewMeta({
            commit_infos: data.commit_infos,
            changed_files: data.changed_files,
            total_additions: data.total_additions,
            total_deletions: data.total_deletions,
            model: data.model,
            tokens: data.tokens,
          });
        } else {
          setReviewError(data.error || "AI 评审返回空结果");
        }
        setReviewLoading(false);
        return;
      }

      // timeout
      setReviewError("AI 评审超时（120s），请稍后重试或减少审查的提交数量");
    } catch (e: any) {
      setReviewError(e?.message || String(e));
    } finally {
      setReviewLoading(false);
    }
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

  const handleOpenInVSCode = async (fpath: string) => {
    if (!fpath) return;
    try {
      await openInVSCode(fpath, repoPath);
    } catch (e: any) {
      console.error("Failed to open in VS Code:", e);
      alert(
        `无法在 VS Code 中打开文件: ${e.message}\n\n` +
        "请确保已安装 VS Code 并将其加入系统 PATH（code 命令可用）。"
      );
    }
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
            <Select value={currentBranch} onValueChange={(value: string) => handleCheckout(value)}>
              <SelectTrigger className="text-xs h-7 w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectPopup>
                {branches.map((b) => (
                  <SelectItem key={b.name} value={b.name}>
                    {b.name}{b.is_current ? " (current)" : ""}{b.is_remote ? " [remote]" : ""}
                  </SelectItem>
                ))}
              </SelectPopup>
            </Select>
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
            <Input className="flex-1 text-xs h-7"
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
            <Checkbox checked={sideBySide} onCheckedChange={(checked) => setSideBySide(!!checked)}>
              <CheckboxIndicator />
            </Checkbox>
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
        <Input className="w-[100px] text-xs h-7 font-mono"
          placeholder="base" value={compareBase} onChange={(e) => setCompareBase(e.target.value)} />
        <span style={{ fontSize: "0.75rem" }}>..</span>
        <Input className="w-[100px] text-xs h-7 font-mono"
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
              <div style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: "0.8rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>提交 ({commits.length})</span>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {commitsLoading && <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>...</span>}
                  {selectedCommits.size > 0 && (
                    <>
                      <span style={{ fontSize: "0.7rem", color: "var(--accent)", fontWeight: 400 }}>
                        已选 {selectedCommits.size}
                      </span>
                      <button className="btn btn--ghost btn--sm" onClick={clearSelection}
                        style={{ fontSize: "0.65rem", padding: "1px 6px" }}>
                        取消
                      </button>
                      <button onClick={handleAiReview}
                        style={{ fontSize: "0.7rem", padding: "2px 10px", background: "var(--accent)", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", whiteSpace: "nowrap" }}>
                        🤖 AI 评审
                      </button>
                    </>
                  )}
                </div>
              </div>
              {commits.map((commit) => (
                <div key={commit.sha} onClick={() => handleSelectCommit(commit)}
                  style={{ padding: "8px 10px 8px 4px", cursor: "pointer", borderBottom: "1px solid var(--border)",
                    display: "flex", alignItems: "flex-start", gap: 4,
                    background: selectedCommit?.sha === commit.sha ? "var(--bg-active)" : "transparent" }}>
                  <div style={{ paddingTop: 1, flexShrink: 0 }}>
                    <Checkbox checked={selectedCommits.has(commit.sha)}
                      onCheckedChange={() => toggleCommitSelection(commit.sha)}
                      className="border-[var(--text-muted)] bg-[var(--bg-surface)] hover:border-[var(--accent)]"
                      style={{ borderRadius: 3 }}>
                      <CheckboxIndicator />
                    </Checkbox>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", gap: 6, marginBottom: 2 }}>
                      <Badge variant="info" className="font-mono text-[0.7rem]">{commit.short_sha}</Badge>
                      {commit.refs.length > 0 && <Badge variant="warning" className="text-[0.6rem]">{commit.refs.join(", ")}</Badge>}
                    </div>
                    <div style={{ fontSize: "0.8rem", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{commit.message}</div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
                      <span>{commit.author}</span><span>{commit.date?.slice(0, 10)}</span>
                    </div>
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
                          <Checkbox checked={reviewedFiles.has(cf.file_path)}
                            onCheckedChange={() => toggleReviewed(cf.file_path)}
                            title="标记已审查">
                            <CheckboxIndicator />
                          </Checkbox>
                          <Badge variant={cf.change_type === "added" ? "success" : cf.change_type === "deleted" ? "destructive" : cf.change_type === "renamed" ? "warning" : "info"}
                            className="text-[0.6rem] min-w-[40px] justify-center">{cf.change_type}</Badge>
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
                      <Checkbox checked={checkedItems.has(item.id)}
                        onCheckedChange={() => {
                          setCheckedItems(prev => { const n = new Set(prev); n.has(item.id) ? n.delete(item.id) : n.add(item.id); return n; });
                        }}>
                        <CheckboxIndicator />
                      </Checkbox>
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
                <Input className="flex-1 text-xs h-7 font-mono"
                  placeholder="文件路径" value={filePath}
                  onChange={(e) => setFilePath(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleOpenInVSCode(filePath)} />
                <Input className="w-[100px] text-xs h-7"
                  placeholder="revision" value={fileRevision} onChange={(e) => setFileRevision(e.target.value)} />
                <button className="btn btn--primary btn--sm" disabled={!filePath}
                  onClick={() => handleOpenInVSCode(filePath)}>在 VS Code 中打开</button>
              </div>
              {fileContent ? (
                <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
                  <div id="blame-gutter" style={{ width: 320, minWidth: 320, overflow: "hidden", borderRight: "1px solid var(--border)",
                    background: "var(--bg-surface)", fontFamily: "monospace", fontSize: 10, lineHeight: "18px" }}>
                    {blameLines.length > 0 ? blameLines.map((line) => (
                      <div key={line.line_number} style={{ display: "flex", padding: "0 4px", height: 18, borderBottom: "1px solid rgba(255,255,255,0.02)", gap: 4 }}>
                        <span style={{ fontWeight: 600, color: "var(--accent)", minWidth: 55, fontSize: 9 }}>{line.short_sha}</span>
                        <span style={{ color: "var(--text-muted)", fontSize: 9, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}
                          title={`${line.author} · ${line.date}`}>{line.author?.slice(0, 10)}</span>
                        <span style={{ color: "var(--text-muted)", fontSize: 9, whiteSpace: "nowrap" }} title={line.date}>{line.date ? new Date(Number(line.date) * 1000).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).replace(/\//g, '-') : ''}</span>
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

      {/* ── AI Review Modal ── */}
      <Dialog open={reviewModalOpen} onOpenChange={(open) => {
        setReviewModalOpen(open);
        if (!open) {
          // If dialog closed for export, trigger download now (no modal lock)
          if (pendingExportUrl.current) {
            const url = pendingExportUrl.current;
            pendingExportUrl.current = null;
            const a = document.createElement("a");
            a.href = url;
            a.download = `ai-review-report-${new Date().toISOString().slice(0, 10)}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 5000);
          }
          setReviewReport(null);
          setReviewError(null);
          setReviewMeta(null);
        }
      }}>
        <DialogContent className="sm:max-w-[1100px] max-h-[85vh] overflow-hidden flex flex-col" style={{ maxWidth: "min(1100px, calc(100vw - 40px))", background: "rgba(24, 24, 34, 0.95)" }}>
          <DialogTitle style={{ fontSize: "1rem", fontWeight: 600, paddingRight: 24 }}>
            {reviewLoading ? "🤖 AI 评审中..." : "🤖 AI 代码审查报告"}
          </DialogTitle>
          {reviewMeta && !reviewLoading && (
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 8, display: "flex", gap: 16, flexWrap: "wrap" }}>
              <span>提交数: {reviewMeta.commit_infos?.length || 0}</span>
              <span>文件数: {reviewMeta.changed_files?.length || 0}</span>
              <span style={{ color: "var(--success)" }}>+{reviewMeta.total_additions || 0}</span>
              <span style={{ color: "var(--danger)" }}>-{reviewMeta.total_deletions || 0}</span>
              {reviewMeta.model && <span>模型: {reviewMeta.model}</span>}
              {reviewMeta.tokens && <span>Token: {reviewMeta.tokens.total}</span>}
            </div>
          )}
          <div style={{ flex: 1, overflow: "auto", padding: "8px 0", minHeight: 200 }}>
            {reviewLoading && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 40, gap: 12 }}>
                <div style={{ width: 32, height: 32, border: "3px solid var(--border)", borderTopColor: "var(--accent)", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>正在分析代码变更，请稍候...</span>
              </div>
            )}
            {reviewError && (
              <div style={{ padding: 16, color: "var(--danger)", fontSize: "0.85rem" }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>❌ 评审失败</div>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.75rem", background: "rgba(255,0,0,0.05)", padding: 12, borderRadius: 6 }}>{reviewError}</pre>
              </div>
            )}
            {reviewReport && !reviewLoading && (
              <div className="markdown-body" style={{ fontSize: "0.82rem", lineHeight: 1.6 }}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeSanitize]}
                >
                  {reviewReport}
                </ReactMarkdown>
              </div>
            )}
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, borderTop: "1px solid var(--border)", paddingTop: 8, marginTop: 4 }}>
            <DialogClose render={<Button variant="outline" size="sm" />}>关闭</DialogClose>
            {reviewReport && (
              <button
                type="button"
                className="group/button inline-flex shrink-0 items-center justify-center rounded-[min(var(--radius-md),12px)] border border-transparent bg-primary text-primary-foreground hover:bg-primary/80 h-7 gap-1 px-2.5 text-[0.8rem] font-medium cursor-pointer"
                onClick={async () => {
                  const content = reviewReport;
                  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
                  const filename = `ai-review-report-${new Date().toISOString().slice(0, 10)}.md`;

                  // Modern File System Access API (Chrome/Edge/Tauri WebView2)
                  if ("showSaveFilePicker" in window) {
                    try {
                      const handle = await window.showSaveFilePicker({
                        suggestedName: filename,
                        types: [{ description: "Markdown", accept: { "text/markdown": [".md"] } }],
                      });
                      const writable = await handle.createWritable();
                      await writable.write(blob);
                      await writable.close();
                    } catch (err: any) {
                      if (err?.name !== "AbortError") {
                        alert("保存失败: " + (err?.message || err));
                      }
                    }
                    return;
                  }

                  // Fallback: close dialog, then download
                  const url = URL.createObjectURL(blob);
                  pendingExportUrl.current = url;
                  setReviewModalOpen(false);
                }}
              >
                导出 Markdown
              </button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
