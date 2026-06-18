import { useState } from "react";
import { DiffEditor } from "@monaco-editor/react";

interface DiffViewerProps {
  original: string;
  modified: string;
  language?: string;
  onApply?: () => void;
}

export default function DiffViewer({
  original,
  modified,
  language = "python",
  onApply,
}: DiffViewerProps) {
  const [applied, setApplied] = useState(false);

  const handleApply = () => {
    setApplied(true);
    onApply?.();
  };

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "12px 16px",
        borderBottom: "1px solid var(--border)",
      }}>
        <h4 style={{ margin: 0, fontSize: "0.92rem" }}>差异对比</h4>
        {onApply && (
          <button
            onClick={handleApply}
            disabled={applied}
            className={applied ? "btn btn--secondary btn--sm" : "btn btn--primary btn--sm"}
          >
            {applied ? "已应用 ✓" : "应用修复"}
          </button>
        )}
      </div>
      <DiffEditor
        height="320px"
        language={language}
        original={original}
        modified={modified}
        theme="vs-dark"
        options={{
          readOnly: true,
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: "on" as any,
          scrollBeyondLastLine: false,
          renderSideBySide: true,
        } as any}
      />
    </div>
  );
}
