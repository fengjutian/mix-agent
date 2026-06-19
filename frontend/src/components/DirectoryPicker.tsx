import { useState, useEffect, useCallback } from "react";
import { listDirs } from "../api/client";

interface DirectoryEntry {
  name: string;
  path: string;
  is_git_repo: boolean;
}

interface DirectoryPickerProps {
  value: string;
  onChange: (path: string) => void;        // 每次输入变化
  onSelectRepo?: (path: string) => void;    // 选择 Git 仓库/目录时立即触发
  placeholder?: string;
}

export default function DirectoryPicker({
  value,
  onChange,
  onSelectRepo,
  placeholder = "仓库路径",
}: DirectoryPickerProps) {
  const [open, setOpen] = useState(false);
  const [currentPath, setCurrentPath] = useState(value || ".");
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [roots, setRoots] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (path: string) => {
    console.log("[DirPicker] load | path:", path);
    setLoading(true);
    setError("");
    try {
      const data = await listDirs(path);
      console.log("[DirPicker] load OK | entries:", data.entries.length, "| roots:", data.roots, "| parent:", data.parent);
      setEntries(data.entries);
      setParent(data.parent);
      setRoots(data.roots || []);
      setCurrentPath(data.path);
    } catch (e: any) {
      console.error("[DirPicker] load FAIL", e);
      setError(e?.message || String(e));
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      load(currentPath);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelect = (entry: DirectoryEntry) => {
    console.log("[DirPicker] handleSelect | name:", entry.name, "| path:", entry.path, "| isGit:", entry.is_git_repo);
    if (entry.is_git_repo) {
      console.log("[DirPicker] → firing onChange + onSelectRepo for:", entry.path);
      onChange(entry.path);
      onSelectRepo?.(entry.path);
      setOpen(false);
    } else {
      load(entry.path);
    }
  };

  const handleGoUp = () => {
    if (parent) load(parent);
  };

  const handleSelectCurrent = () => {
    console.log("[DirPicker] handleSelectCurrent | path:", currentPath);
    onChange(currentPath);
    onSelectRepo?.(currentPath);
    setOpen(false);
  };

  // Format path for display — show last 2 segments
  const displayPath = (p: string): string => {
    const parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
    if (parts.length <= 2) return p;
    return ".../" + parts.slice(-2).join("/");
  };

  return (
    <div style={{ position: "relative" }}>
      {/* Trigger */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          cursor: "pointer",
        }}
      >
        <input
          className="form-input"
          style={{ padding: "4px 8px", fontSize: "0.82rem", flex: 1 }}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setOpen(true)}
        />
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          style={{ padding: "4px 6px", flexShrink: 0 }}
          onClick={() => {
            const p = value || ".";
            console.log("[DirPicker] open button | value:", value, "| will load:", p);
            setCurrentPath(p);
            setOpen(!open);
          }}
          title="浏览目录"
        >
          📂
        </button>
      </div>

      {/* Dropdown */}
      {open && (
        <>
          {/* Backdrop */}
          <div
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 998,
            }}
            onClick={() => setOpen(false)}
          />

          {/* Panel */}
          <div
            style={{
              position: "absolute",
              top: "100%",
              left: 0,
              zIndex: 999,
              marginTop: 4,
              width: 380,
              maxHeight: 320,
              display: "flex",
              flexDirection: "column",
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
              overflow: "hidden",
            }}
          >
            {/* Header: current path + select button */}
            <div
              style={{
                padding: "8px 10px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{
                  fontSize: "0.72rem",
                  color: "var(--text-muted)",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  fontFamily: "monospace",
                }}
                title={currentPath}
              >
                {displayPath(currentPath)}
              </span>
              <button
                className="btn btn--primary btn--sm"
                style={{ padding: "2px 10px", fontSize: "0.72rem" }}
                onClick={handleSelectCurrent}
              >
                选择此目录
              </button>
            </div>

            {/* Entries */}
            <div style={{ flex: 1, overflow: "auto" }}>
              {error && (
                <div
                  style={{
                    padding: "10px 12px",
                    color: "var(--danger)",
                    fontSize: "0.78rem",
                  }}
                >
                  {error}
                </div>
              )}

              {loading && (
                <div
                  style={{
                    padding: "16px",
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: "0.8rem",
                  }}
                >
                  加载中...
                </div>
              )}

              {/* Root / drive switcher — always visible when we have roots */}
              {!loading && !error && roots.length > 0 && (
                <div
                  style={{
                    padding: "6px 10px",
                    borderBottom: "1px solid rgba(255,255,255,0.06)",
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginRight: 2, flexShrink: 0 }}>
                    💿
                  </span>
                  {roots.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className="btn btn--ghost btn--sm"
                      style={{
                        padding: "2px 10px",
                        fontSize: "0.72rem",
                        fontFamily: "monospace",
                        background:
                          currentPath.toUpperCase() === r.toUpperCase() || currentPath.toUpperCase().startsWith(r.toUpperCase())
                            ? "rgba(255,255,255,0.1)"
                            : undefined,
                      }}
                      onClick={() => load(r)}
                    >
                      {r.replace(/\\/g, "").replace(/:$/, ":/")}
                    </button>
                  ))}
                </div>
              )}

              {/* Parent directory */}
              {parent && (
                <div
                  onClick={handleGoUp}
                  style={{
                    padding: "7px 12px",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: "0.82rem",
                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                    color: "var(--text-muted)",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background =
                      "rgba(255,255,255,0.04)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background =
                      "transparent";
                  }}
                >
                  <span>📁</span>
                  <span>..</span>
                </div>
              )}

              {!loading && !error && entries.length === 0 && (
                <div
                  style={{
                    padding: "16px",
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: "0.8rem",
                  }}
                >
                  此目录下无子目录
                </div>
              )}

              {entries.map((entry) => (
                <div
                  key={entry.path}
                  onClick={() => handleSelect(entry)}
                  style={{
                    padding: "7px 12px",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: "0.82rem",
                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background =
                      "rgba(255,255,255,0.06)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLDivElement).style.background =
                      "transparent";
                  }}
                >
                  <span>{entry.is_git_repo ? "📦" : "📁"}</span>
                  <span style={{ flex: 1 }}>{entry.name}</span>
                  {entry.is_git_repo && (
                    <span
                      className="badge badge--success"
                      style={{ fontSize: "0.62rem", padding: "1px 6px" }}
                    >
                      Git
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
