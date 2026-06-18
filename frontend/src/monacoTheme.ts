/**
 * Monaco Editor 自定义主题 — 增强 diff 增删代码行的视觉对比度。
 *
 * 基于 vs-dark，针对以下场景优化：
 *  - DiffEditor (DiffViewer.tsx)：左右分栏 diff
 *  - Editor + language="diff" (Review.tsx)：unified diff 文本
 */

import type { editor } from "monaco-editor";

export const MIX_AGENT_DARK = "mix-agent-dark";

const theme: editor.IStandaloneThemeData = {
  base: "vs-dark",
  inherit: true,
  rules: [
    // ── Diff 语法高亮 (unified diff in plain Editor) ──
    // Added line header: @@ ... @@ 或 +++
    { token: "meta.diff.header", foreground: "569CD6", fontStyle: "bold" },
    // Added line range info (@@ -1,3 +1,4 @@)
    { token: "meta.diff.range", foreground: "C586C0", fontStyle: "bold" },
    // Added line: lines starting with +
    { token: "markup.inserted", foreground: "73C991" },
    // Deleted line: lines starting with -
    { token: "markup.deleted", foreground: "F14C4C" },
    // Added line (alternative token)
    { token: "diff.inserted", foreground: "73C991" },
    // Deleted line (alternative token)
    { token: "diff.deleted", foreground: "F14C4C" },
  ],
  colors: {
    // ── Diff Editor (side-by-side) ──
    // Background for added lines
    "diffEditor.insertedTextBackground": "#1a3a2a88",
    // Border for added lines
    "diffEditor.insertedTextBorder": "#2ea04344",
    // Background for removed lines
    "diffEditor.removedTextBackground": "#3a1a2a88",
    // Border for removed lines
    "diffEditor.removedTextBorder": "#f8514944",
    // Gutter background for added lines
    "diffEditorGutter.insertedLineBackground": "#2ea04366",
    // Gutter background for removed lines
    "diffEditorGutter.removedLineBackground": "#f8514966",
    // ── Editor line highlighting ──
    "editor.lineHighlightBackground": "#ffffff08",
    "editor.lineHighlightBorder": "#ffffff00",
  },
};

/** 向 Monaco 注册自定义主题（幂等 — 重复调用会被 Monaco 忽略）。 */
export function registerMixAgentTheme(monaco: any) {
  try {
    monaco.editor.defineTheme(MIX_AGENT_DARK, theme);
  } catch {
    // 主题已注册，忽略
  }
}
