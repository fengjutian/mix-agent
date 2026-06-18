import { useRef, useState } from "react";
import Editor from "@monaco-editor/react";

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
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 8
      }}>
        <h4 style={{ margin: 0 }}>Diff View</h4>
        {onApply && (
          <button
            onClick={handleApply}
            disabled={applied}
            style={{
              padding: "6px 16px",
              background: applied ? "#ccc" : "#4caf50",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: applied ? "default" : "pointer",
            }}
          >
            {applied ? "Applied ✓" : "Apply Fix"}
          </button>
        )}
      </div>
      <div style={{ border: "1px solid #ddd", borderRadius: 4, overflow: "hidden" }}>
        <Editor
          height="300px"
          language={language}
          original={original}
          modified={modified}
          theme="vs-dark"
          options={{
            readOnly: true,
            renderSideBySide: true,
            minimap: { enabled: false },
            fontSize: 13,
          }}
        />
      </div>
    </div>
  );
}
