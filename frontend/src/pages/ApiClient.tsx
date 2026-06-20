import { useState, useCallback, useEffect, useMemo, Fragment } from "react";
import { sendProxyRequest, aiAnalyzeRequest, listProjectDirs, type ProxyResponseBody, type AiTraceResult } from "../api/client";
import mermaid from "mermaid";
import { Tabs, TabsList, TabsTab, TabsPanel } from "../components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectPopup, SelectItem, SelectItemIndicator } from "../components/ui/select";
import { Collapsible, CollapsibleTrigger, CollapsiblePanel } from "../components/ui/collapsible";
import { Checkbox, CheckboxIndicator } from "../components/ui/checkbox";
import { Tooltip, TooltipTrigger, TooltipPopup, TooltipProvider } from "../components/ui/tooltip";
import {
  Dialog, DialogTrigger, DialogContent, DialogHeader,
  DialogTitle, DialogFooter, DialogClose,
} from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { cn } from "../lib/utils";

// Initialize mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  securityLevel: "loose",
  fontFamily: "ui-sans-serif, system-ui, sans-serif",
});

/* ═══════════════════════════════════════════════════════════════════════
   API Client — Postman-like HTTP request tool
   Built with @base-ui/react primitives + Tailwind CSS v4
   ═══════════════════════════════════════════════════════════════════════ */

// ── Mermaid sanitize (frontend fallback) ──

function sanitizeMermaid(code: string): string {
  let c = code;
  // Fix unquoted labels: NODE[content] -> NODE["content"]
  c = c.replace(/(\w+)\[([^\]]*?)\]/g, (_m, id, label: string) => {
    if (label.startsWith('"') && label.endsWith('"')) return _m;
    const clean = label.replace(/[/(){}\<\>]/g, " ").replace(/\s+/g, " ").trim();
    return `${id}["${clean}"]`;
  });
  // Remove HTML tags
  c = c.replace(/<br\s*\/?\s*>/gi, ", ");
  c = c.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  return c;
}

// ── Constants ──

const HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] as const;
type HttpMethod = (typeof HTTP_METHODS)[number];
const METHODS_WITH_BODY: HttpMethod[] = ["POST", "PUT", "PATCH", "DELETE"];

const METHOD_COLORS: Record<string, string> = {
  GET: "text-green-400", POST: "text-orange-400", PUT: "text-blue-400",
  DELETE: "text-red-400", PATCH: "text-orange-400",
  HEAD: "text-muted-foreground", OPTIONS: "text-muted-foreground",
};

// ── Helpers ──

function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
function formatTiming(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}
function formatBytes(text: string): string {
  const bytes = new Blob([text]).size;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function tryPrettifyJSON(raw: string): string {
  try { return JSON.stringify(JSON.parse(raw), null, 2); } catch { return raw; }
}
function tryPrettifyXML(raw: string): string {
  try {
    let indent = 0;
    return raw
      .replace(/(<[^/!][^>]*>)([^<]*)(<\/[^>]*>)/g, (_, open, text, close) =>
        "  ".repeat(indent) + open + text + close)
      .replace(/(<[^/!][^>]*>)/g, (m: string) => { const s = "  ".repeat(indent) + m; indent++; return s; })
      .replace(/(<\/[^>]*>)/g, (m: string) => { indent = Math.max(0, indent - 1); return "  ".repeat(indent) + m; });
  } catch { return raw; }
}
function inferContentType(headers: Record<string, string>): string | null {
  const ct = Object.entries(headers).find(([k]) => k.toLowerCase() === "content-type");
  return ct ? ct[1] : null;
}

// ── Environment variable substitution ──

function substituteEnvVars(text: string, env: Record<string, string>): string {
  return text.replace(/\{\{(\w+)\}\}/g, (_, name) => env[name] ?? `{{${name}}}`);
}

// ── Persisted types ──

interface KVPair { key: string; value: string; enabled: boolean; }
type BodyMode = "raw" | "form-data" | "x-www-form-urlencoded";
type AuthType = "none" | "bearer" | "basic";

interface RequestState {
  method: HttpMethod;
  url: string;
  headers: KVPair[];
  queryParams: KVPair[];
  body: string;
  bodyMode: BodyMode;
  contentType: string;
  formData: KVPair[];
  authType: AuthType;
  authBearerToken: string;
  authBasicUser: string;
  authBasicPass: string;
}

interface RequestTab {
  id: string;
  name: string;
  request: RequestState;
  response: ProxyResponseBody | null;
  error: string;
  loading: boolean;
}

interface Collection {
  id: string;
  name: string;
  requests: { name: string; request: RequestState }[];
}

interface Environment {
  id: string;
  name: string;
  variables: Record<string, string>;
}

function defaultRequest(): RequestState {
  return {
    method: "GET", url: "", headers: [], queryParams: [],
    body: "", bodyMode: "raw", contentType: "application/json",
    formData: [], authType: "none", authBearerToken: "",
    authBasicUser: "", authBasicPass: "",
  };
}

function newTab(name?: string): RequestTab {
  return { id: uid(), name: name || "新请求", request: defaultRequest(), response: null, error: "", loading: false };
}

// ── localStorage helpers ──

function lsGet<T>(key: string, fallback: T): T {
  try { const r = localStorage.getItem(key); return r ? JSON.parse(r) : fallback; } catch { return fallback; }
}
function lsSet(key: string, val: unknown) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* ignore */ }
}

// ── cURL parser ──

function parseCurl(curl: string): Partial<RequestState> | null {
  try {
    const s = curl.trim();
    if (!s.startsWith("curl ")) return null;
    const urlMatch = s.match(/(?:--url\s+)?['"]?(https?:\/\/[^\s'"]+)['"]?/);
    const url = urlMatch ? urlMatch[1] : "";
    const methodMatch = s.match(/(?:-X|--request)\s+['"]?(\w+)['"]?/);
    const method = (methodMatch ? methodMatch[1].toUpperCase() : "GET") as HttpMethod;
    const headers: KVPair[] = [];
    const headerRe = /(?:-H|--header)\s+['"]([^'"]+)['"]/g;
    let hm;
    while ((hm = headerRe.exec(s)) !== null) {
      const colon = hm[1].indexOf(":");
      if (colon > 0) headers.push({ key: hm[1].slice(0, colon).trim(), value: hm[1].slice(colon + 1).trim(), enabled: true });
    }
    const dataMatch = s.match(/(?:-d|--data|--data-raw|--data-binary)\s+['"]([^'"]*)['"]/s);
    const body = dataMatch ? dataMatch[1] : "";
    return { method, url, headers, body, authType: "none" };
  } catch { return null; }
}

function toCurl(req: RequestState, env?: Record<string, string>): string {
  const url = env ? substituteEnvVars(req.url, env) : req.url;
  let c = `curl`;
  if (req.method !== "GET") c += ` -X ${req.method}`;
  for (const h of req.headers) {
    if (h.enabled && h.key.trim()) {
      const v = env ? substituteEnvVars(h.value, env) : h.value;
      c += ` -H '${h.key.trim()}: ${v}'`;
    }
  }
  if (req.authType === "bearer" && req.authBearerToken) c += ` -H 'Authorization: Bearer ${req.authBearerToken}'`;
  else if (req.authType === "basic" && req.authBasicUser) c += ` -u '${req.authBasicUser}:${req.authBasicPass}'`;
  if (req.body && METHODS_WITH_BODY.includes(req.method)) c += ` -d '${req.body.replace(/'/g, "'\\''")}'`;
  c += ` '${url}'`;
  return c;
}

// ── Key-Value Editor ──

function KeyValueEditor({ pairs, onChange, showEnableToggle }: {
  pairs: KVPair[]; onChange: (pairs: KVPair[]) => void; showEnableToggle: boolean;
}) {
  const update = (i: number, p: Partial<KVPair>) => {
    const next = [...pairs]; next[i] = { ...next[i], ...p }; onChange(next);
  };
  return (
    <div className="flex flex-col gap-1.5">
      {pairs.map((p, i) => (
        <div key={i} className="flex items-center gap-1.5">
          {showEnableToggle && (
            <Checkbox checked={p.enabled}
              onCheckedChange={(checked) => update(i, { enabled: !!checked })}
            >
              <CheckboxIndicator />
            </Checkbox>
          )}
          <Input value={p.key}
            onChange={(e) => update(i, { key: e.target.value })}
            placeholder="Key"
            className="flex-[1_1_35%] h-7 text-xs font-mono px-2" />
          <Input value={p.value}
            onChange={(e) => update(i, { value: e.target.value })}
            placeholder="Value"
            className="flex-[1_1_65%] h-7 text-xs font-mono px-2" />
          <Button variant="ghost" size="icon-xs"
            onClick={() => onChange(pairs.filter((_, idx) => idx !== i))}
            title="移除"
            className="shrink-0 text-muted-foreground hover:text-destructive"
          >✕</Button>
        </div>
      ))}
      <Button variant="ghost" size="xs" onClick={() => onChange([...pairs, { key: "", value: "", enabled: true }])}
        className="self-start text-xs">
        + 添加
      </Button>
    </div>
  );
}

// ── Request Tab bar ──

function TabBar({ tabs, activeId, onSelect, onClose, onAdd }: {
  tabs: RequestTab[]; activeId: string;
  onSelect: (id: string) => void; onClose: (id: string) => void; onAdd: () => void;
}) {
  return (
    <div className="flex items-center gap-0.5 border-b border-border overflow-x-auto min-h-9 mb-4">
      {tabs.map((tab) => (
        <div key={tab.id} className={cn(
          "group/tab flex items-center gap-1.5 px-2.5 py-1.5 cursor-pointer rounded-t-md border border-transparent text-sm whitespace-nowrap transition-colors",
          activeId === tab.id
            ? "bg-card border-border border-b-card text-foreground font-medium -mb-px"
            : "text-muted-foreground hover:text-foreground"
        )}>
          <span onClick={() => onSelect(tab.id)}
            className="max-w-[140px] overflow-hidden text-ellipsis"
            onDoubleClick={() => {
              const name = prompt("重命名请求标签", tab.name);
              if (name) tab.name = name;
            }}
          >
            {tab.request.method !== "GET" && (
              <span className={cn("text-[0.7rem] font-bold mr-1", METHOD_COLORS[tab.request.method])}>
                {tab.request.method}
              </span>
            )}
            {tab.name}
          </span>
          {tab.loading && <span className="text-[0.65rem] animate-pulse">⏳</span>}
          {tabs.length > 1 && (
            <button onClick={(e) => { e.stopPropagation(); onClose(tab.id); }}
              className="text-muted-foreground hover:text-foreground text-[0.65rem] leading-none p-0.5 rounded-sm opacity-0 group-hover/tab:opacity-100 transition-opacity"
              title="关闭"
            >✕</button>
          )}
        </div>
      ))}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger render={<Button variant="ghost" size="icon-xs" onClick={onAdd}
            className="shrink-0 ml-1 rounded-md text-muted-foreground" title="新建请求标签" />}>
            +
          </TooltipTrigger>
          <TooltipPopup>新建请求标签</TooltipPopup>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

// ═══════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════

export default function ApiClientPage() {
  // ── Tabs ──
  const [tabs, setTabs] = useState<RequestTab[]>(() => {
    const saved = lsGet<RequestTab[]>("api-tabs", []);
    return saved.length > 0 ? saved : [newTab()];
  });
  const [activeTabId, setActiveTabId] = useState(() => tabs[0]?.id ?? "");

  useEffect(() => {
    lsSet("api-tabs", tabs.map(t => ({
      id: t.id, name: t.name, request: t.request, response: null, error: "", loading: false,
    })));
  }, [tabs.map(t => `${t.id}:${t.name}:${JSON.stringify(t.request)}`).join("|")]);

  const activeTab = useMemo(() => tabs.find(t => t.id === activeTabId) ?? tabs[0], [tabs, activeTabId]);
  const req = activeTab?.request ?? defaultRequest();
  const response = activeTab?.response ?? null;
  const thisError = activeTab?.error ?? "";
  const loading = activeTab?.loading ?? false;

  const updateReq = useCallback((patch: Partial<RequestState>) => {
    setTabs(prev => prev.map(t =>
      t.id === activeTabId ? { ...t, request: { ...t.request, ...patch }, error: "", response: null } : t
    ));
  }, [activeTabId]);

  // ── Collections ──
  const [collections, setCollections] = useState<Collection[]>(() => lsGet<Collection[]>("api-collections", []));
  useEffect(() => { lsSet("api-collections", collections); }, [collections]);

  // ── Save dialog ──
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveReqName, setSaveReqName] = useState("");
  const [saveCollName, setSaveCollName] = useState("");

  // ── Environments ──
  const [environments, setEnvironments] = useState<Environment[]>(() => lsGet<Environment[]>("api-envs", []));
  const [activeEnvId, setActiveEnvId] = useState<string>(() => lsGet<string>("api-active-env", ""));
  useEffect(() => { lsSet("api-envs", environments); }, [environments]);
  const activeEnv = useMemo(() => environments.find(e => e.id === activeEnvId), [environments, activeEnvId]);
  const envVars = activeEnv?.variables ?? {};

  // ── cURL import state ──
  const [curlModalOpen, setCurlModalOpen] = useState(false);
  const [curlText, setCurlText] = useState("");
  const [curlError, setCurlError] = useState("");

  // ── UI state ──
  const [sidebarTab, setSidebarTab] = useState<"collections" | "envs">("collections");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [reqConfigTab, setReqConfigTab] = useState("headers");
  const [respTab, setRespTab] = useState("body");
  const [bodyViewMode, setBodyViewMode] = useState<"pretty" | "raw" | "preview">("pretty");

  // ── AI Analysis modal ──
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AiTraceResult | null>(null);
  const [aiError, setAiError] = useState("");
  const [aiSvg, setAiSvg] = useState<string | null>(null);
  const [aiSvgError, setAiSvgError] = useState("");
  const [aiProjectDir, setAiProjectDir] = useState(".");
  const [aiDirList, setAiDirList] = useState<Array<{ name: string; path: string; relative: string }>>([]);
  const [aiDirParents, setAiDirParents] = useState<Array<{ name: string; path: string; relative: string }>>([]);
  const [aiDirShow, setAiDirShow] = useState(false);
  const [expandedCodeRow, setExpandedCodeRow] = useState<number | null>(null);

  const browseProjectDir = useCallback(async (dirPath: string) => {
    try {
      const res = await listProjectDirs(dirPath);
      if (res.ok) {
        setAiDirList(res.dirs);
        setAiDirParents(res.parents);
        setAiDirShow(true);
        setAiProjectDir(res.current);
      }
    } catch { /* ignore */ }
  }, []);

  // Render mermaid when AI result changes
  useEffect(() => {
    if (!aiResult?.ai_swimlane) {
      setAiSvg(null);
      setAiSvgError("");
      return;
    }
    const code = sanitizeMermaid(aiResult.ai_swimlane);
    const id = "ai-swimlane-" + Math.random().toString(36).slice(2);
    mermaid
      .render(id, code)
      .then(({ svg }) => { setAiSvg(svg); setAiSvgError(""); })
      .catch((err) => {
        console.error("Mermaid error:", err);
        setAiSvg(null);
        setAiSvgError(String(err).slice(0, 300));
      });
  }, [aiResult?.ai_swimlane]);

  const openAiModal = useCallback(() => {
    if (!req.url.trim()) {
      setAiError("请先输入 URL");
    } else {
      setAiError("");
    }
    setAiResult(null);
    setAiSvg(null);
    setAiSvgError("");
    setAiModalOpen(true);
  }, [req.url]);

  const startAiAnalyze = useCallback(async () => {
    if (!req.url.trim()) {
      setAiError("请先输入 URL");
      return;
    }
    setAiLoading(true);
    setAiResult(null);
    setAiError("");
    try {
      const result = await aiAnalyzeRequest({
        method: req.method,
        url: req.url,
        headers: Object.fromEntries(
          req.headers.filter(h => h.enabled && h.key.trim()).map(h => [h.key.trim(), h.value])
        ),
        body: req.body,
        source_root: aiProjectDir,
      });
      setAiResult(result);
      if (!result.ok) setAiError(result.error || "分析失败");
    } catch (e: any) {
      setAiError(e.message || "AI 分析请求失败");
    } finally {
      setAiLoading(false);
    }
  }, [req.method, req.url, req.headers, req.body, aiProjectDir]);

  // ── Tab operations ──
  const addTab = useCallback(() => {
    const tab = newTab(); setTabs(prev => [...prev, tab]); setActiveTabId(tab.id);
  }, []);
  const closeTab = useCallback((id: string) => {
    setTabs(prev => {
      if (prev.length <= 1) return prev;
      const next = prev.filter(t => t.id !== id);
      if (id === activeTabId) {
        const idx = prev.findIndex(t => t.id === id);
        const newActive = next[Math.min(idx, next.length - 1)];
        if (newActive) setActiveTabId(newActive.id);
      }
      return next;
    });
  }, [activeTabId]);

  // ── Send request ──
  const handleSend = useCallback(async (tab: RequestTab) => {
    const r = tab.request;
    const substitutedUrl = substituteEnvVars(r.url, envVars);
    if (!substitutedUrl.trim()) {
      setTabs(prev => prev.map(t => t.id === tab.id ? { ...t, error: "请输入 URL" } : t));
      return;
    }
    setTabs(prev => prev.map(t => t.id === tab.id ? { ...t, loading: true, error: "", response: null } : t));
    try {
      const headersMap: Record<string, string> = {};
      for (const h of r.headers) {
        if (h.enabled && h.key.trim()) headersMap[h.key.trim()] = substituteEnvVars(h.value, envVars);
      }
      if (r.authType === "bearer" && r.authBearerToken) {
        headersMap["Authorization"] = `Bearer ${substituteEnvVars(r.authBearerToken, envVars)}`;
      } else if (r.authType === "basic" && r.authBasicUser) {
        const u = substituteEnvVars(r.authBasicUser, envVars);
        const p = substituteEnvVars(r.authBasicPass, envVars);
        headersMap["Authorization"] = `Basic ${btoa(`${u}:${p}`)}`;
      }
      const queryMap: Record<string, string> = {};
      for (const q of r.queryParams) {
        if (q.enabled && q.key.trim()) queryMap[q.key.trim()] = substituteEnvVars(q.value, envVars);
      }
      let bodyStr: string | null = null;
      let ct = r.contentType;
      if (METHODS_WITH_BODY.includes(r.method)) {
        if (r.bodyMode === "raw") {
          bodyStr = substituteEnvVars(r.body, envVars);
        } else {
          const fd = new URLSearchParams();
          for (const f of r.formData) {
            if (f.enabled && f.key.trim()) fd.append(f.key.trim(), substituteEnvVars(f.value, envVars));
          }
          bodyStr = fd.toString();
          ct = "application/x-www-form-urlencoded";
        }
      }
      const res = await sendProxyRequest({
        method: r.method, url: substitutedUrl, headers: headersMap,
        query_params: queryMap, body: bodyStr,
        content_type: bodyStr ? ct : null, timeout_seconds: 30,
        verify_ssl: false,
      });
      setTabs(prev => prev.map(t => t.id === tab.id ? { ...t, response: res, loading: false } : t));
      if (tab.name === "新请求" && res.ok) {
        try {
          const parsed = new URL(substitutedUrl);
          const autoName = `${r.method} ${parsed.pathname}${parsed.search ? "?" + parsed.search.slice(0, 20) : ""}`;
          setTabs(prev => prev.map(t => t.id === tab.id ? { ...t, name: autoName.slice(0, 40) } : t));
        } catch { /* ignore */ }
      }
    } catch (err: any) {
      setTabs(prev => prev.map(t => t.id === tab.id ? { ...t, error: err.message || "请求失败", loading: false } : t));
    }
  }, [envVars]);

  // ── Collection operations ──
  const saveToCollection = useCallback(() => {
    setSaveReqName(activeTab?.name || "请求");
    setSaveCollName("我的集合");
    setSaveDialogOpen(true);
  }, [activeTab]);

  const handleSaveSubmit = useCallback(() => {
    const name = saveReqName.trim();
    const collName = saveCollName.trim();
    if (!name || !collName) return;
    setCollections(prev => {
      let coll = prev.find(c => c.name === collName);
      if (!coll) { coll = { id: uid(), name: collName, requests: [] }; prev = [...prev, coll]; }
      const existingIdx = coll.requests.findIndex(r => r.name === name);
      const reqCopy = JSON.parse(JSON.stringify(activeTab?.request ?? defaultRequest()));
      if (existingIdx >= 0) coll.requests[existingIdx] = { name, request: reqCopy };
      else coll.requests.push({ name, request: reqCopy });
      return prev.map(c => c.id === coll!.id ? { ...coll! } : c);
    });
    setSaveDialogOpen(false);
  }, [saveReqName, saveCollName, activeTab]);

  const loadFromCollection = useCallback((reqState: RequestState, name: string) => {
    const tab = newTab(name); tab.request = JSON.parse(JSON.stringify(reqState));
    setTabs(prev => [...prev, tab]); setActiveTabId(tab.id);
  }, []);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); if (activeTab) handleSend(activeTab); }
      if ((e.ctrlKey || e.metaKey) && e.key === "s" && !e.shiftKey && activeTab) { e.preventDefault(); saveToCollection(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeTab, handleSend, saveToCollection]);

  // ── Derived ──
  const hasBody = METHODS_WITH_BODY.includes(req.method);
  const responseStatusCode = response?.status ?? 0;
  const responseContentType = response ? inferContentType(response.headers) : null;
  const statusColor =
    responseStatusCode >= 200 && responseStatusCode < 300 ? "bg-green-500 text-black"
    : responseStatusCode >= 400 && responseStatusCode < 500 ? "bg-orange-500 text-white"
    : responseStatusCode >= 500 ? "bg-red-500 text-white"
    : responseStatusCode >= 300 ? "bg-blue-500 text-white"
    : "bg-muted text-muted-foreground";

  const formattedBody = useMemo(() => {
    if (!response?.body) return "";
    if (bodyViewMode === "raw") return response.body;
    if (responseContentType?.includes("json")) return tryPrettifyJSON(response.body);
    if (responseContentType?.includes("xml") || responseContentType?.includes("html")) return tryPrettifyXML(response.body);
    return tryPrettifyJSON(response.body);
  }, [response?.body, bodyViewMode, responseContentType]);

  const curlCmd = useMemo(() => toCurl(req, envVars), [
    req.method, req.url, req.headers, req.body, req.authType,
    req.authBearerToken, req.authBasicUser, req.authBasicPass, envVars,
  ]);

  // ── Render ──
  return (
    <TooltipProvider>
      <div className="flex flex-col h-full gap-0">
        {/* ── Header ── */}
        <div className="flex justify-between items-center mb-1">
          <div>
            <h1 className="text-xl font-semibold mb-0.5">📡 API 客户端</h1>
          </div>
          <div className="flex items-center gap-2">
            {/* Environment selector */}
            <Select value={activeEnvId}
              onValueChange={(v) => { setActiveEnvId(v); lsSet("api-active-env", v); }}
            >
              <SelectTrigger className="h-7 text-xs w-32">
                <SelectValue placeholder="无环境" />
              </SelectTrigger>
              <SelectPopup>
                <SelectItem value="">
                  <span className="text-muted-foreground">无环境</span>
                  {!activeEnvId && <SelectItemIndicator />}
                </SelectItem>
                {environments.map(e => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.name}
                    {activeEnvId === e.id && <SelectItemIndicator />}
                  </SelectItem>
                ))}
              </SelectPopup>
            </Select>

            <Tooltip>
              <TooltipTrigger render={<Button variant="ghost" size="xs" onClick={() => { setSidebarOpen(!sidebarOpen); }}
                className="text-[0.7rem]" />}>
                {sidebarOpen ? "◀" : "📁"}
              </TooltipTrigger>
              <TooltipPopup>{sidebarOpen ? "收起侧栏" : "展开侧栏"}</TooltipPopup>
            </Tooltip>

            <Dialog open={curlModalOpen} onOpenChange={setCurlModalOpen}>
              <DialogTrigger>
                <Button variant="outline" size="xs" className="text-[0.7rem]" onClick={() => setCurlModalOpen(true)}>
                  📋 导入 cURL
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>📋 导入 cURL 命令</DialogTitle>
                </DialogHeader>
                <textarea value={curlText}
                  onChange={(e) => { setCurlText(e.target.value); setCurlError(""); }}
                  placeholder={`curl -X POST 'https://api.example.com/data' \\\n  -H 'Content-Type: application/json' \\\n  -d '{"key":"value"}'`}
                  className="flex min-h-[150px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono resize-y outline-none focus-visible:border-ring"
                  rows={8}
                />
                {curlError && <p className="text-xs text-destructive mt-2">{curlError}</p>}
                <DialogFooter>
                  <DialogClose><Button variant="outline" size="sm">取消</Button></DialogClose>
                  <Button size="sm" onClick={() => {
                    const parsed = parseCurl(curlText);
                    if (!parsed) { setCurlError("无法解析 cURL 命令，请检查格式"); return; }
                    const tab = newTab(parsed.url ? parsed.url.slice(0, 40) : "导入的请求");
                    tab.request = { ...defaultRequest(), ...parsed };
                    setTabs(prev => [...prev, tab]); setActiveTabId(tab.id);
                    setCurlModalOpen(false); setCurlText(""); setCurlError("");
                  }}>导入</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* ── Body: Sidebar + Content ── */}
        <div className="flex flex-1 gap-3 min-h-0">
          {/* ── Sidebar (VS Code–style: full panel or icon strip) ── */}
          {sidebarOpen ? (
            <div className="w-[220px] min-w-[220px] overflow-auto border-r border-border pr-2 flex flex-col gap-2">
              {/* Collapse button inside the sidebar */}
              <button
                onClick={() => setSidebarOpen(false)}
                className="self-end p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors text-xs"
                title="折叠侧栏"
              >◀</button>

              <Tabs value={sidebarTab} onValueChange={(v) => setSidebarTab(v as "collections" | "envs")}>
                <TabsList className="w-full">
                  <TabsTab value="collections" className="flex-1 justify-center text-xs">📁 集合</TabsTab>
                  <TabsTab value="envs" className="flex-1 justify-center text-xs">🌐 环境</TabsTab>
                </TabsList>

                <TabsPanel value="collections" className="pt-2">
                  <div className="flex flex-col gap-1.5">
                    {collections.map(coll => (
                      <Collapsible key={coll.id}>
                        <CollapsibleTrigger className="text-xs">
                          {coll.name}
                          <span className="text-muted-foreground ml-1">({coll.requests.length})</span>
                        </CollapsibleTrigger>
                        <CollapsiblePanel>
                          <div className="flex flex-col gap-0.5 ml-2 mt-1">
                            {coll.requests.map((cr, i) => (
                              <div key={i} onClick={() => loadFromCollection(cr.request, cr.name)}
                                className="flex items-center gap-1.5 cursor-pointer px-1.5 py-1 rounded text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                              >
                                <span className={cn("text-[0.6rem] font-bold font-mono", METHOD_COLORS[cr.request.method])}>
                                  {cr.request.method}
                                </span>
                                <span className="truncate">{cr.name}</span>
                              </div>
                            ))}
                            {coll.requests.length === 0 && (
                              <div className="text-[0.7rem] text-muted-foreground px-1.5 py-1">空集合</div>
                            )}
                          </div>
                        </CollapsiblePanel>
                      </Collapsible>
                    ))}
                    {collections.length === 0 && (
                      <div className="text-xs text-muted-foreground p-2">
                        尚未保存任何请求。<br />发送后按 Ctrl+S 保存。
                      </div>
                    )}
                    <Button variant="ghost" size="xs" onClick={saveToCollection} className="self-start text-xs">
                      💾 保存当前请求
                    </Button>

                    <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
                      <DialogContent className="sm:max-w-sm" showCloseButton={false}>
                        <DialogHeader>
                          <DialogTitle>💾 保存当前请求</DialogTitle>
                        </DialogHeader>
                        <div className="flex flex-col gap-3">
                          <div className="flex flex-col gap-1.5">
                            <label className="text-xs font-medium text-foreground">请求名称</label>
                            <Input value={saveReqName} onChange={(e) => setSaveReqName(e.target.value)}
                              placeholder="请求名称" autoFocus
                              onKeyDown={(e) => { if (e.key === "Enter") document.getElementById("save-coll-name")?.focus(); }}
                            />
                          </div>
                          <div className="flex flex-col gap-1.5">
                            <label className="text-xs font-medium text-foreground">集合名称</label>
                            <Input id="save-coll-name" value={saveCollName} onChange={(e) => setSaveCollName(e.target.value)}
                              placeholder="集合名称"
                              onKeyDown={(e) => { if (e.key === "Enter") handleSaveSubmit(); }}
                            />
                            {collections.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-1">
                                {collections.map(c => (
                                  <button key={c.id} type="button" onClick={() => setSaveCollName(c.name)}
                                    className="text-[0.65rem] px-1.5 py-0.5 rounded-full border border-border text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
                                  >{c.name}</button>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                        <DialogFooter>
                          <DialogClose><Button variant="outline" size="sm">取消</Button></DialogClose>
                          <Button size="sm" onClick={handleSaveSubmit}>💾 保存</Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  </div>
                </TabsPanel>

                <TabsPanel value="envs" className="pt-2">
                  <div className="flex flex-col gap-1.5">
                    {environments.map(env => (
                      <div key={env.id} onClick={() => { setActiveEnvId(env.id); lsSet("api-active-env", env.id); }}
                        className={cn(
                          "p-2 rounded-md cursor-pointer text-xs transition-colors",
                          activeEnvId === env.id
                            ? "bg-primary/10 border border-primary/30"
                            : "border border-transparent hover:bg-muted"
                        )}
                      >
                        <div className="flex justify-between items-center">
                          <span className="font-medium text-foreground">{env.name}</span>
                          <Button variant="ghost" size="icon-xs" onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(`删除环境 "${env.name}"？`)) {
                              setEnvironments(prev => prev.filter(x => x.id !== env.id));
                              if (activeEnvId === env.id) { setActiveEnvId(""); lsSet("api-active-env", ""); }
                            }
                          }} className="text-[0.6rem] text-muted-foreground hover:text-destructive">✕</Button>
                        </div>
                        <div className="text-muted-foreground mt-0.5">{Object.keys(env.variables).length} 个变量</div>
                      </div>
                    ))}
                    <Button variant="ghost" size="xs" onClick={() => {
                      const name = prompt("环境名称");
                      if (!name) return;
                      const env: Environment = { id: uid(), name, variables: {} };
                      setEnvironments(prev => [...prev, env]);
                      setActiveEnvId(env.id); lsSet("api-active-env", env.id);
                    }} className="self-start text-xs">+ 新建环境</Button>

                    {activeEnv && (
                      <div className="mt-2 border-t border-border pt-2">
                        <div className="text-xs font-medium text-foreground mb-2">
                          变量: {activeEnv.name}
                        </div>
                        <KeyValueEditor
                          pairs={Object.entries(activeEnv.variables).map(([k, v]) => ({ key: k, value: v, enabled: true }))}
                          onChange={(pairs) => {
                            const vars: Record<string, string> = {};
                            for (const p of pairs) { if (p.key.trim()) vars[p.key.trim()] = p.value; }
                            setEnvironments(prev => prev.map(e =>
                              e.id === activeEnv.id ? { ...e, variables: vars } : e
                            ));
                          }}
                          showEnableToggle={false}
                        />
                      </div>
                    )}
                  </div>
                </TabsPanel>
              </Tabs>
            </div>
          ) : (
            /* ── Collapsed icon strip ── */
            <div className="w-[40px] min-w-[40px] border-r border-border flex flex-col items-center gap-1 pt-2">
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors text-sm"
                title="展开侧栏"
              >▶</button>
              <button
                onClick={() => { setSidebarOpen(true); setSidebarTab("collections"); }}
                className={cn(
                  "p-1.5 rounded text-sm transition-colors",
                  sidebarTab === "collections"
                    ? "text-foreground bg-muted"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
                title="集合"
              >📁</button>
              <button
                onClick={() => { setSidebarOpen(true); setSidebarTab("envs"); }}
                className={cn(
                  "p-1.5 rounded text-sm transition-colors",
                  sidebarTab === "envs"
                    ? "text-foreground bg-muted"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
                title="环境"
              >🌐</button>
            </div>
          )}

          {/* ── Main Content ── */}
          <div className="flex-1 min-w-0 flex flex-col overflow-auto">
            {/* Request Tab bar */}
            <TabBar tabs={tabs} activeId={activeTabId}
              onSelect={setActiveTabId} onClose={closeTab} onAdd={addTab} />

            {/* ── Request Builder Card ── */}
            <div className="rounded-xl border border-border bg-card p-4 mb-4">
              {/* Method + URL + Send row */}
              <div className="flex gap-2 mb-3">
                <Select value={req.method} onValueChange={(v) => updateReq({ method: v as HttpMethod })}>
                  <SelectTrigger className={cn("w-[100px] font-bold font-mono text-sm", METHOD_COLORS[req.method])}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectPopup>
                    {HTTP_METHODS.map(m => (
                      <SelectItem key={m} value={m}>
                        <span className={cn("font-mono font-bold", METHOD_COLORS[m])}>{m}</span>
                        {req.method === m && <SelectItemIndicator />}
                      </SelectItem>
                    ))}
                  </SelectPopup>
                </Select>

                <Input value={req.url}
                  onChange={(e) => updateReq({ url: e.target.value })}
                  placeholder={activeEnv ? "https://{{host}}/api/endpoint" : "https://api.example.com/endpoint"}
                  className="flex-1 font-mono text-sm" />

                <Button onClick={() => activeTab && handleSend(activeTab)} disabled={loading}
                  className="min-w-[100px]">
                  {loading ? "⏳" : "▶"} 发送
                </Button>
                <Tooltip>
                  <TooltipTrigger render={<Button variant="outline" size="icon-sm" onClick={() => { navigator.clipboard.writeText(curlCmd); }} />}>
                    📋
                  </TooltipTrigger>
                  <TooltipPopup>复制 cURL</TooltipPopup>
                </Tooltip>
                <Button variant="outline" size="sm"
                  onClick={openAiModal}
                  className="gap-1 text-xs font-medium whitespace-nowrap"
                >
                  🤖 AI分析
                </Button>
              </div>

              {/* Request config tabs */}
              <Tabs value={reqConfigTab} onValueChange={setReqConfigTab}>
                <TabsList>
                  <TabsTab value="headers" className="text-xs">
                    Headers
                    {req.headers.filter(h => h.enabled && h.key.trim()).length > 0 && (
                      <span className="ml-1 text-[0.65rem] opacity-60">
                        ({req.headers.filter(h => h.enabled && h.key.trim()).length})
                      </span>
                    )}
                  </TabsTab>
                  <TabsTab value="query" className="text-xs">
                    Params
                    {req.queryParams.filter(q => q.enabled && q.key.trim()).length > 0 && (
                      <span className="ml-1 text-[0.65rem] opacity-60">
                        ({req.queryParams.filter(q => q.enabled && q.key.trim()).length})
                      </span>
                    )}
                  </TabsTab>
                  {hasBody && (
                    <TabsTab value="body" className="text-xs">
                      Body
                      {(req.body.trim() || req.formData.filter(f => f.enabled && f.key.trim()).length > 0) && (
                        <span className="ml-1 text-[0.65rem] opacity-60">●</span>
                      )}
                    </TabsTab>
                  )}
                  <TabsTab value="auth" className="text-xs">
                    Auth
                    {req.authType !== "none" && (
                      <span className="ml-1 text-[0.65rem] opacity-60">●</span>
                    )}
                  </TabsTab>
                </TabsList>

                <TabsPanel value="headers">
                  <KeyValueEditor
                    pairs={req.headers.length > 0 ? req.headers : [{ key: "", value: "", enabled: true }]}
                    onChange={(pairs) => updateReq({ headers: pairs })} showEnableToggle />
                </TabsPanel>
                <TabsPanel value="query">
                  <KeyValueEditor
                    pairs={req.queryParams.length > 0 ? req.queryParams : [{ key: "", value: "", enabled: true }]}
                    onChange={(pairs) => updateReq({ queryParams: pairs })} showEnableToggle />
                </TabsPanel>
                {hasBody && (
                  <TabsPanel value="body">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">模式</span>
                        <Select value={req.bodyMode} onValueChange={(v) => updateReq({ bodyMode: v as BodyMode })}>
                          <SelectTrigger className="h-7 text-xs w-40">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectPopup>
                            <SelectItem value="raw">raw</SelectItem>
                            <SelectItem value="form-data">form-data</SelectItem>
                            <SelectItem value="x-www-form-urlencoded">x-www-form-urlencoded</SelectItem>
                          </SelectPopup>
                        </Select>
                        {req.bodyMode === "raw" && (
                          <Select value={req.contentType} onValueChange={(v) => updateReq({ contentType: v })}>
                            <SelectTrigger className="h-7 text-xs w-48">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectPopup>
                              {["application/json", "text/plain", "text/html", "application/xml", "application/x-www-form-urlencoded"].map(ct =>
                                <SelectItem key={ct} value={ct}>{ct}</SelectItem>
                              )}
                            </SelectPopup>
                          </Select>
                        )}
                      </div>
                      {req.bodyMode === "raw" ? (
                        <div>
                          <textarea value={req.body}
                            onChange={(e) => updateReq({ body: e.target.value })}
                            placeholder='{"key": "value"}'
                            className="flex min-h-[150px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono resize-y outline-none focus-visible:border-ring"
                            rows={8}
                          />
                          {req.contentType === "application/json" && req.body.trim() && (
                            <Button variant="ghost" size="xs"
                              onClick={() => updateReq({ body: tryPrettifyJSON(req.body) })}
                              className="mt-1 text-xs">🧹 格式化 JSON</Button>
                          )}
                        </div>
                      ) : (
                        <KeyValueEditor
                          pairs={req.formData.length > 0 ? req.formData : [{ key: "", value: "", enabled: true }]}
                          onChange={(pairs) => updateReq({ formData: pairs })} showEnableToggle />
                      )}
                    </div>
                  </TabsPanel>
                )}
                <TabsPanel value="auth">
                  <div className="flex flex-col gap-3 max-w-sm">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground block mb-1.5">认证类型</label>
                      <Select value={req.authType} onValueChange={(v) => updateReq({ authType: v as AuthType })}>
                        <SelectTrigger className="w-40 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectPopup>
                          <SelectItem value="none">无认证</SelectItem>
                          <SelectItem value="bearer">Bearer Token</SelectItem>
                          <SelectItem value="basic">Basic Auth</SelectItem>
                        </SelectPopup>
                      </Select>
                    </div>
                    {req.authType === "bearer" && (
                      <div>
                        <label className="text-xs font-medium text-muted-foreground block mb-1.5">Token</label>
                        <Input value={req.authBearerToken}
                          onChange={(e) => updateReq({ authBearerToken: e.target.value })}
                          placeholder={activeEnv ? "{{token}}" : "eyJ..."}
                          className="font-mono text-sm" />
                      </div>
                    )}
                    {req.authType === "basic" && (
                      <>
                        <div>
                          <label className="text-xs font-medium text-muted-foreground block mb-1.5">用户名</label>
                          <Input value={req.authBasicUser}
                            onChange={(e) => updateReq({ authBasicUser: e.target.value })}
                            placeholder="admin" className="max-w-[300px]" />
                        </div>
                        <div>
                          <label className="text-xs font-medium text-muted-foreground block mb-1.5">密码</label>
                          <Input value={req.authBasicPass}
                            onChange={(e) => updateReq({ authBasicPass: e.target.value })}
                            type="password" placeholder="••••" className="max-w-[300px]" />
                        </div>
                      </>
                    )}
                  </div>
                </TabsPanel>
              </Tabs>
            </div>

            {/* ── Error ── */}
            {thisError && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm px-4 py-3 mb-3">
                {thisError}
              </div>
            )}

            {/* ── Response ── */}
            {response && (
              <div className="rounded-xl border border-border bg-card p-4">
                {/* Status bar */}
                <div className="flex items-center flex-wrap gap-2 mb-3">
                  <span className={cn(
                    "inline-flex items-center px-3 py-1 rounded-full text-sm font-bold font-mono",
                    statusColor,
                  )}>
                    {response.status || "—"} {response.status_text}
                  </span>
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-secondary text-muted-foreground font-mono">
                    ⏱ {formatTiming(response.timing_ms)}
                  </span>
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-secondary text-muted-foreground font-mono">
                    📦 {formatBytes(response.body)}
                  </span>
                  {responseContentType && (
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[0.7rem] bg-secondary text-muted-foreground">
                      {responseContentType.split(";")[0]}
                    </span>
                  )}
                  <div className="flex-1" />
                  <Tooltip>
                    <TooltipTrigger render={<Button variant="ghost" size="xs" onClick={() => { navigator.clipboard.writeText(response.body); }} />}>
                      📋 复制响应
                    </TooltipTrigger>
                    <TooltipPopup>复制响应体到剪贴板</TooltipPopup>
                  </Tooltip>
                  <Button variant="ghost" size="xs"
                    onClick={() => setTabs(prev => prev.map(t =>
                      t.id === activeTabId ? { ...t, response: null, error: "" } : t
                    ))}
                  >✕ 清除</Button>
                </div>

                {/* Response tabs */}
                <Tabs value={respTab} onValueChange={setRespTab}>
                  <TabsList>
                    <TabsTab value="body" className="text-xs">Body</TabsTab>
                    <TabsTab value="headers" className="text-xs">
                      Headers
                      <span className="ml-1 text-[0.65rem] opacity-60">({Object.keys(response.headers).length})</span>
                    </TabsTab>
                    <TabsTab value="curl" className="text-xs">cURL</TabsTab>
                  </TabsList>

                  <TabsPanel value="body">
                    {/* View mode toggles */}
                    <div className="flex gap-1 mb-2">
                      {(["pretty", "raw", "preview"] as const).map(mode => (
                        <Button key={mode} variant="ghost" size="xs"
                          onClick={() => setBodyViewMode(mode)}
                          className={cn(
                            "text-[0.7rem] px-2",
                            bodyViewMode === mode
                              ? "bg-secondary text-foreground font-medium"
                              : "text-muted-foreground"
                          )}
                        >
                          {mode === "pretty" ? "✨ Pretty" : mode === "raw" ? "📄 Raw" : "🖼 Preview"}
                        </Button>
                      ))}
                    </div>

                    {bodyViewMode === "preview" && responseContentType?.includes("html") ? (
                      <iframe srcDoc={response.body}
                        className="w-full h-[400px] rounded-md border border-border bg-white" />
                    ) : (
                      <pre className="max-h-[500px] overflow-auto font-mono text-[0.78rem] whitespace-pre-wrap break-all p-3 rounded-md bg-secondary border border-border">
                        {formattedBody || "(空响应)"}
                      </pre>
                    )}
                  </TabsPanel>

                  <TabsPanel value="headers">
                    <div className="max-h-[400px] overflow-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left p-2 w-[35%] text-xs font-medium text-muted-foreground uppercase tracking-wider">Key</th>
                            <th className="text-left p-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(response.headers).map(([k, v]) => (
                            <tr key={k} className="border-b border-border/50 hover:bg-muted/30">
                              <td className="p-2 font-mono text-xs text-foreground">{k}</td>
                              <td className="p-2 font-mono text-xs break-all">{v}</td>
                            </tr>
                          ))}
                          {Object.keys(response.headers).length === 0 && (
                            <tr><td colSpan={2} className="p-4 text-xs text-muted-foreground text-center">无响应头</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </TabsPanel>

                  <TabsPanel value="curl">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs text-muted-foreground">等效 cURL 命令</span>
                      <Button variant="ghost" size="xs" onClick={() => navigator.clipboard.writeText(curlCmd)}>
                        📋 复制
                      </Button>
                    </div>
                    <pre className="p-3 rounded-md bg-secondary border border-border font-mono text-xs whitespace-pre-wrap break-all max-h-[300px] overflow-auto">
                      {curlCmd}
                    </pre>
                  </TabsPanel>
                </Tabs>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── AI Analysis Modal ── */}
      <Dialog open={aiModalOpen} onOpenChange={setAiModalOpen}>
        <DialogContent className="!w-[80vw] !max-w-[80vw] max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              🤖 AI 调用链分析
              <span className={cn("text-xs font-mono font-bold", METHOD_COLORS[req.method])}>
                {req.method}
              </span>
              <span className="text-xs text-muted-foreground font-normal truncate max-w-[400px]">
                {req.url || "(无 URL)"}
              </span>
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto py-2 space-y-4">
            {/* Project directory selector — always visible */}
            {!aiLoading && !aiResult && !aiError && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/30 p-3">
                  <span className="text-xs text-muted-foreground whitespace-nowrap">📁 项目目录</span>
                  <Input value={aiProjectDir} onChange={(e) => { setAiProjectDir(e.target.value); setAiDirShow(false); }} placeholder="." className="flex-1 h-7 text-xs font-mono" />
                  <Button size="icon-sm" variant="ghost" onClick={() => browseProjectDir(aiProjectDir)} title="浏览目录" className="shrink-0">📂</Button>
                  <Button size="sm" onClick={startAiAnalyze} className="gap-1 text-xs">🚀 开始分析</Button>
                </div>
                {aiDirShow && (aiDirParents.length > 0 || aiDirList.length > 0) && (
                  <div className="rounded-lg border border-border bg-card p-2 max-h-[200px] overflow-y-auto space-y-0.5">
                    {aiDirParents.map((d) => (
                      <button key={d.path} onClick={() => browseProjectDir(d.path)}
                        className="block w-full text-left px-2 py-1 rounded text-xs font-mono hover:bg-muted text-muted-foreground"
                      >📁 ../{d.name}</button>
                    ))}
                    {aiDirList.map((d) => (
                      <button key={d.path} onClick={() => { setAiProjectDir(d.relative); setAiDirShow(false); }}
                        className="block w-full text-left px-2 py-1 rounded text-xs font-mono hover:bg-muted"
                      >📁 {d.name}</button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {aiLoading && (
              <div className="flex flex-col items-center justify-center py-12 gap-3">
                <div className="animate-spin text-3xl">⏳</div>
                <p className="text-sm text-muted-foreground">AI 正在分析调用链，请稍候…</p>
              </div>
            )}
            {!aiLoading && aiError && (
              <>
                <div className="space-y-2">
                  <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/30 p-3">
                    <span className="text-xs text-muted-foreground whitespace-nowrap">📁 项目目录</span>
                    <Input value={aiProjectDir} onChange={(e) => { setAiProjectDir(e.target.value); setAiDirShow(false); }} placeholder="." className="flex-1 h-7 text-xs font-mono" />
                    <Button size="icon-sm" variant="ghost" onClick={() => browseProjectDir(aiProjectDir)} title="浏览目录" className="shrink-0">📂</Button>
                    <Button size="sm" onClick={startAiAnalyze} className="gap-1 text-xs">🔄 重试</Button>
                  </div>
                  {aiDirShow && (aiDirParents.length > 0 || aiDirList.length > 0) && (
                    <div className="rounded-lg border border-border bg-card p-2 max-h-[200px] overflow-y-auto space-y-0.5">
                      {aiDirParents.map((d) => (
                        <button key={d.path} onClick={() => browseProjectDir(d.path)}
                          className="block w-full text-left px-2 py-1 rounded text-xs font-mono hover:bg-muted text-muted-foreground"
                        >📁 ../{d.name}</button>
                      ))}
                      {aiDirList.map((d) => (
                        <button key={d.path} onClick={() => { setAiProjectDir(d.relative); setAiDirShow(false); }}
                          className="block w-full text-left px-2 py-1 rounded text-xs font-mono hover:bg-muted"
                        >📁 {d.name}</button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm px-4 py-3">
                  {aiError}
                </div>
              </>
            )}
            {!aiLoading && aiResult && aiResult.ok && (
              <>
                {/* Re-analyze bar */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/30 p-2">
                    <span className="text-xs text-muted-foreground whitespace-nowrap">📁</span>
                    <Input value={aiProjectDir} onChange={(e) => { setAiProjectDir(e.target.value); setAiDirShow(false); }} placeholder="." className="flex-1 h-7 text-xs font-mono" />
                    <Button size="icon-sm" variant="ghost" onClick={() => browseProjectDir(aiProjectDir)} title="浏览目录" className="shrink-0">📂</Button>
                    <Button size="sm" variant="outline" onClick={startAiAnalyze} className="gap-1 text-xs">🔄 重新分析</Button>
                  </div>
                  {aiDirShow && (aiDirParents.length > 0 || aiDirList.length > 0) && (
                    <div className="rounded-lg border border-border bg-card p-2 max-h-[200px] overflow-y-auto space-y-0.5">
                      {aiDirParents.map((d) => (
                        <button key={d.path} onClick={() => browseProjectDir(d.path)}
                          className="block w-full text-left px-2 py-1 rounded text-xs font-mono hover:bg-muted text-muted-foreground"
                        >📁 ../{d.name}</button>
                      ))}
                      {aiDirList.map((d) => (
                        <button key={d.path} onClick={() => { setAiProjectDir(d.relative); setAiDirShow(false); }}
                          className="block w-full text-left px-2 py-1 rounded text-xs font-mono hover:bg-muted"
                        >📁 {d.name}</button>
                      ))}
                    </div>
                  )}
                </div>
                {aiResult.ai_summary && (
                  <div className="rounded-lg border border-border bg-secondary/30 p-3">
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">📝 AI 分析总结</h4>
                    <p className="text-sm whitespace-pre-wrap leading-relaxed">{aiResult.ai_summary}</p>
                  </div>
                )}
                {aiResult.ai_swimlane && (
                  <div className="rounded-lg border border-border bg-card p-3">
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">📊 泳道图</h4>
                    <div className="overflow-x-auto bg-white rounded-md p-3 border border-border min-h-[100px]">
                      {aiSvg ? (
                        <div dangerouslySetInnerHTML={{ __html: aiSvg }} className="flex justify-center" />
                      ) : aiSvgError ? (
                        <p className="text-destructive text-sm py-4">泳道图渲染失败: {aiSvgError}</p>
                      ) : (
                        <p className="text-muted-foreground text-sm py-4 text-center">正在渲染泳道图…</p>
                      )}
                    </div>
                    <Collapsible>
                      <CollapsibleTrigger className="text-xs text-muted-foreground hover:text-foreground mt-1.5 inline-block cursor-pointer">📄 查看 Mermaid 源码</CollapsibleTrigger>
                      <CollapsiblePanel>
                        <pre className="mt-1 p-2 rounded bg-secondary border border-border text-[0.7rem] font-mono whitespace-pre-wrap max-h-[200px] overflow-auto">{aiResult.ai_swimlane}</pre>
                      </CollapsiblePanel>
                    </Collapsible>
                  </div>
                )}
                {aiResult.call_chain.length > 0 && (
                  <Collapsible>
                    <CollapsibleTrigger className="text-xs font-semibold text-muted-foreground uppercase tracking-wider cursor-pointer hover:text-foreground block">🔗 后端调用链 ({aiResult.call_chain.length} 个节点)</CollapsibleTrigger>
                    <CollapsiblePanel>
                      <div className="mt-1.5 rounded-lg border border-border overflow-hidden">
                        <table className="w-full text-xs">
                          <thead><tr className="bg-secondary"><th className="text-left p-2 font-medium text-muted-foreground">函数</th><th className="text-left p-2 font-medium text-muted-foreground">类型</th><th className="text-left p-2 font-medium text-muted-foreground">位置</th></tr></thead>
                          <tbody>
                            {aiResult.call_chain.map((n, i) => (
                              <Fragment key={i}>
                                <tr
                                  className={cn("border-t border-border/50 hover:bg-muted/30", n.code && "cursor-pointer")}
                                  onClick={() => n.code && setExpandedCodeRow(expandedCodeRow === i ? null : i)}
                                  title={n.code ? "点击查看源码" : undefined}
                                >
                                  <td className="p-2 font-mono">{n.name}</td>
                                  <td className="p-2"><span className={cn("px-1.5 py-0.5 rounded text-[0.65rem]", n.kind === "route" ? "bg-blue-500/10 text-blue-400" : n.kind === "service" ? "bg-green-500/10 text-green-400" : n.kind === "db" ? "bg-red-500/10 text-red-400" : "bg-muted text-muted-foreground")}>{n.kind}</span></td>
                                  <td className="p-2 font-mono text-muted-foreground">{n.file_path}:{n.line_number}</td>
                                </tr>
                                {expandedCodeRow === i && n.code && (
                                  <tr className="border-t border-border/30 bg-secondary/20">
                                    <td colSpan={3} className="p-0">
                                      <pre className="p-3 text-[0.7rem] font-mono whitespace-pre overflow-x-auto max-h-[300px] overflow-y-auto">{n.code}</pre>
                                    </td>
                                  </tr>
                                )}
                              </Fragment>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CollapsiblePanel>
                  </Collapsible>
                )}
                {aiResult.tables.length > 0 && (
                  <Collapsible>
                    <CollapsibleTrigger className="text-xs font-semibold text-muted-foreground uppercase tracking-wider cursor-pointer hover:text-foreground block">🗄️ 涉及数据表 ({aiResult.tables.length})</CollapsibleTrigger>
                    <CollapsiblePanel>
                      <div className="mt-1.5 rounded-lg border border-border overflow-hidden">
                        <table className="w-full text-xs">
                          <thead><tr className="bg-secondary"><th className="text-left p-2 font-medium text-muted-foreground">表名</th><th className="text-left p-2 font-medium text-muted-foreground">操作</th><th className="text-left p-2 font-medium text-muted-foreground">位置</th></tr></thead>
                          <tbody>
                            {aiResult.tables.map((t, i) => (
                              <tr key={i} className="border-t border-border/50 hover:bg-muted/30">
                                <td className="p-2 font-mono">{t.table_name}</td>
                                <td className="p-2"><span className={cn("px-1.5 py-0.5 rounded text-[0.65rem]", t.operation === "SELECT" ? "bg-blue-500/10 text-blue-400" : t.operation === "INSERT" ? "bg-green-500/10 text-green-400" : t.operation === "UPDATE" ? "bg-yellow-500/10 text-yellow-400" : t.operation === "DELETE" ? "bg-red-500/10 text-red-400" : "bg-muted text-muted-foreground")}>{t.operation}</span></td>
                                <td className="p-2 font-mono text-muted-foreground">{t.file_path}:{t.line_number}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CollapsiblePanel>
                  </Collapsible>
                )}
                {aiResult.route_info && (
                  <div className="rounded-lg border border-border bg-secondary/30 p-3">
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">🎯 匹配路由</h4>
                    <div className="flex items-center gap-2 text-sm">
                      <span className={cn("px-2 py-0.5 rounded text-xs font-mono font-bold", METHOD_COLORS[aiResult.route_info.method])}>{aiResult.route_info.method}</span>
                      <span className="font-mono text-xs">{aiResult.route_info.path}</span>
                      <span className="text-muted-foreground text-xs">→</span>
                      <span className="font-mono text-xs">{aiResult.route_info.handler}()</span>
                      <span className="text-muted-foreground text-[0.65rem]">@ {aiResult.route_info.file_path}:{aiResult.route_info.line_number}</span>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(aiResult?.ai_swimlane || aiResult?.swimlane || ""); }} disabled={!aiResult?.ai_swimlane}>📋 复制 Mermaid</Button>
            <DialogClose render={<Button variant="outline" size="sm">关闭</Button>} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}
