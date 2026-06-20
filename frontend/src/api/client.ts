const BASE = "http://localhost:8000/api/v1";

async function request<T>(
  path: string,
  opts?: RequestInit & { timeoutSeconds?: number }
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts?.headers as Record<string, string> || {}),
  };

  const timeoutSeconds = opts?.timeoutSeconds ?? 30;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutSeconds * 1000);
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...opts,
      headers,
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`${res.status}: ${err}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error(
        timeoutSeconds >= 60
          ? `请求超时（${timeoutSeconds}s），AI 调用可能仍在执行中，请稍后重试`
          : `请求超时（${timeoutSeconds}s），请检查后端服务是否运行`
      );
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ── Tasks ──
export function createTask(body: {
  description: string;
  target_branch: string;
  base_branch: string;
  repo_path: string;
}) {
  return request<{ task_id: string; status: string }>("/tasks/", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelTask(taskId: string) {
  return request<{ task_id: string; status: string }>(`/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}

// ── Agent (Phase 2 AI) ──
export function runAgent(body: {
  description: string;
  target_branch: string;
  base_branch: string;
  repo_path: string;
  force?: boolean;
}) {
  return request<{ task_id: string; status: string; message: string }>("/agent/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getAgentResult(taskId: string) {
  return request<{
    task_id: string;
    status: string;
    result: {
      parse_result: any;
      orchestrator_result: any;
      code_review_result: any;
      sql_audit_result: any;
      summary_result: any;
      accumulated_tokens: number;
    };
    changed_files: any[];
    changed_files_count: number;
    git_error: string | null;
  }>(`/agent/${taskId}/result`);
}

export function getTask(taskId: string) {
  return request<{
    task_id: string;
    status: string;
    description: string;
    target_branch: string;
    base_branch: string;
  }>(`/tasks/${taskId}`);
}

export function getFindings(taskId: string) {
  return request<{ findings: any[]; total: number }>(`/tasks/${taskId}/findings`);
}

export function getReport(taskId: string) {
  return request<any>(`/tasks/${taskId}/report`);
}

// ── Admin ──
export function getCostOverview() {
  return request<any>("/admin/cost/overview");
}

export function getCostBreakdown() {
  return request<{ tasks: any[] }>("/admin/cost/breakdown");
}

export function getModels() {
  return request<{
    models: Array<{
      provider: string;
      model: string;
      base_url: string;
      input_price_per_m: number;
      output_price_per_m: number;
    }>;
    nodes: Array<{
      node: string;
      provider: string;
      model: string;
      overridden: boolean;
    }>;
  }>("/admin/models");
}

export function assignModel(node: string, provider: string) {
  return request<{ ok: boolean; error?: string }>("/admin/models/assign", {
    method: "PUT",
    body: JSON.stringify({ node, provider }),
  });
}

// ── Prompts ──

export function getPrompts() {
  return request<{
    prompts: Array<{
      agent: string;
      system: string;
      user_template: string;
      overridden: boolean;
      is_custom: boolean;
    }>;
  }>("/admin/prompts");
}

export function createPrompt(agent: string, system: string, user_template?: string) {
  return request<{ ok: boolean; agent: string; error?: string }>("/admin/prompts", {
    method: "POST",
    body: JSON.stringify({ agent, system, user_template: user_template ?? "{input}" }),
  });
}

export function updatePrompt(agent: string, system?: string, user_template?: string) {
  return request<{ ok: boolean; agent: string; error?: string }>(`/admin/prompts/${agent}`, {
    method: "PUT",
    body: JSON.stringify({ system: system ?? null, user_template: user_template ?? null }),
  });
}

export function deletePrompt(agent: string) {
  return request<{ ok: boolean; agent: string; message?: string; error?: string }>(
    `/admin/prompts/${agent}`,
    { method: "DELETE" }
  );
}

export function aiGeneratePrompt(description: string) {
  return request<{
    ok: boolean;
    system?: string;
    user_template?: string;
    suggested_agent?: string;
    error?: string;
  }>("/admin/prompts/ai-generate", {
    method: "POST",
    body: JSON.stringify({ description }),
  });
}

// ── MCP Servers ──

export function getMCPServers() {
  return request<{
    servers: Array<{
      name: string;
      transport: string;
      enabled: boolean;
      command: string;
      args: string[];
      env: Record<string, string>;
      url: string;
      headers: Record<string, string>;
    }>;
  }>("/admin/mcp/servers");
}

export function addMCPServer(cfg: {
  name: string;
  transport: string;
  enabled?: boolean;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}) {
  return request<{ ok: boolean; server?: any; error?: string }>("/admin/mcp/servers", {
    method: "POST",
    body: JSON.stringify(cfg),
  });
}

export function updateMCPServer(name: string, updates: Record<string, any>) {
  return request<{ ok: boolean; server?: any; error?: string }>(`/admin/mcp/servers/${name}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export function deleteMCPServer(name: string) {
  return request<{ ok: boolean; name?: string; error?: string }>(`/admin/mcp/servers/${name}`, {
    method: "DELETE",
  });
}

export function testMCPServer(name: string) {
  return request<{
    ok: boolean;
    server_name: string;
    server_version: string;
    tools: Array<{ name: string; description: string; input_schema: any }>;
    error: string;
  }>(`/admin/mcp/servers/${name}/test`, { method: "POST" });
}

// ── API Keys ──
export function getKeys() {
  return request<{
    keys: Array<{
      provider: string;
      api_key_masked: string;
      has_key: boolean;
      base_url: string;
      model: string;
    }>;
  }>("/admin/keys");
}

export function setKey(provider: string, api_key: string, base_url?: string, model?: string) {
  return request<{ ok: boolean; provider: string; error?: string }>("/admin/keys", {
    method: "PUT",
    body: JSON.stringify({ provider, api_key, base_url, model }),
  });
}

export function deleteKey(provider: string) {
  return request<{ ok: boolean; provider: string; error?: string }>("/admin/keys", {
    method: "DELETE",
    body: JSON.stringify({ provider }),
  });
}

// ── Analyzer / 接口调用链分析 ──

export function listRoutes() {
  return request<{
    ok: boolean;
    routes: Array<{
      method: string;
      path: string;
      full_path: string;
      handler: string;
      file_path: string;
      line_number: number;
      has_auth: boolean;
      tags: string[];
      summary: string;
    }>;
    total: number;
  }>("/analyzer/routes");
}

export function traceInterface(method: string, path: string, sourceRoot: string = ".") {
  return request<{
    ok: boolean;
    entry_point: string;
    route_info: {
      method: string;
      path: string;
      handler: string;
      file_path: string;
      line_number: number;
      has_auth: boolean;
      auth_deps: string[];
      tags: string[];
    } | null;
    call_chain: Array<{
      name: string;
      kind: string;
      file_path: string;
      line_number: number;
    }>;
    tables: Array<{
      table_name: string;
      class_name: string | null;
      operation: string;
      location: string;
      file_path: string;
      line_number: number;
    }>;
    swimlane: string;
    diagram_nodes: Array<{
      id: string;
      name: string;
      kind: string;
      file_path: string;
      line_number: number;
    }>;
    diagram_edges: Array<{ from: string; to: string }>;
    summary: string;
    all_routes: Array<{
      method: string;
      path: string;
      full_path: string;
      handler: string;
      file_path: string;
      line_number: number;
    }>;
    error: string;
  }>("/analyzer/trace", {
    method: "POST",
    body: JSON.stringify({ method, path, source_root: sourceRoot }),
  });
}

// ── Project Directory Browser ──

export function listProjectDirs(dirPath: string = ".") {
  return request<{
    ok: boolean;
    current: string;
    dirs: Array<{ name: string; path: string; relative: string }>;
    parents: Array<{ name: string; path: string; relative: string }>;
    error?: string;
  }>(`/analyzer/dirs?path=${encodeURIComponent(dirPath)}`);
}

// ── Review ──

export function listCommits(params: {
  branch?: string;
  max_count?: number;
  skip?: number;
  file_path?: string;
  since?: string;
  until?: string;
  author?: string;
  repo_path?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.branch) qs.set("branch", params.branch);
  if (params.max_count) qs.set("max_count", String(params.max_count));
  if (params.skip) qs.set("skip", String(params.skip));
  if (params.file_path) qs.set("file_path", params.file_path);
  if (params.since) qs.set("since", params.since);
  if (params.until) qs.set("until", params.until);
  if (params.author) qs.set("author", params.author);
  if (params.repo_path) qs.set("repo_path", params.repo_path);
  return request<{
    ok: boolean;
    branch: string;
    commits: Array<{
      sha: string;
      short_sha: string;
      author: string;
      author_email: string;
      date: string;
      message: string;
      refs: string[];
    }>;
    total: number;
  }>(`/review/commits?${qs.toString()}`);
}

export function getCommitDetail(sha: string, repo_path: string = ".") {
  return request<{
    ok: boolean;
    commit: {
      sha: string;
      short_sha: string;
      author: string;
      author_email: string;
      date: string;
      message: string;
      refs: string[];
      changed_files: Array<{
        file_path: string;
        change_type: string;
        old_path: string | null;
        additions: number;
        deletions: number;
      }>;
      total_additions: number;
      total_deletions: number;
    };
    raw_diff: string;
  }>(`/review/commits/${sha}?repo_path=${encodeURIComponent(repo_path)}`);
}

export function listBranches(include_remote?: boolean, repo_path?: string) {
  const qs = new URLSearchParams();
  if (include_remote) qs.set("include_remote", "true");
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{
    ok: boolean;
    current: string;
    branches: Array<{
      name: string;
      is_current: boolean;
      is_remote: boolean;
      last_commit_sha: string;
      last_commit_short: string;
      last_commit_date: string;
      last_commit_message: string;
    }>;
    total: number;
  }>(`/review/branches?${qs.toString()}`);
}

export function checkoutBranch(branch: string, create?: boolean, repo_path?: string) {
  const qs = new URLSearchParams();
  qs.set("branch", branch);
  if (create) qs.set("create", "true");
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{ ok: boolean; current: string; checked_out: string }>(
    `/review/branches/checkout?${qs.toString()}`,
    { method: "POST" }
  );
}

export function readFile(file_path: string, revision?: string, repo_path?: string) {
  const qs = new URLSearchParams();
  qs.set("file_path", file_path);
  if (revision) qs.set("revision", revision);
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{
    ok: boolean;
    file_path: string;
    revision: string;
    content: string;
  }>(`/review/file?${qs.toString()}`);
}

export function blameFile(
  file_path: string,
  revision?: string,
  line_start?: number,
  line_end?: number,
  repo_path?: string
) {
  const qs = new URLSearchParams();
  qs.set("file_path", file_path);
  if (revision) qs.set("revision", revision);
  if (line_start) qs.set("line_start", String(line_start));
  if (line_end) qs.set("line_end", String(line_end));
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{
    ok: boolean;
    file_path: string;
    revision: string;
    lines: Array<{
      line_number: number;
      content: string;
      commit_sha: string;
      short_sha: string;
      author: string;
      date: string;
      summary: string;
    }>;
    total: number;
  }>(`/review/blame?${qs.toString()}`);
}

export function getDiffs(target?: string, base?: string, repo_path?: string) {
  const qs = new URLSearchParams();
  if (target) qs.set("target", target);
  if (base) qs.set("base", base);
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{
    ok: boolean;
    target: string;
    base: string;
    changed_files: Array<{
      file_path: string;
      change_type: string;
      old_path: string | null;
      additions: number;
      deletions: number;
    }>;
    total_additions: number;
    total_deletions: number;
    raw_diff: string;
  }>(`/review/diffs?${qs.toString()}`);
}

export function getRepoStatus(repo_path?: string) {
  const qs = repo_path ? `?repo_path=${encodeURIComponent(repo_path)}` : "";
  return request<{
    ok: boolean;
    branch: string;
    status_items: Array<{
      file_path: string;
      status: string;
      staged: boolean;
    }>;
    is_clean: boolean;
  }>(`/review/status${qs}`);
}

// ── Directory Browser ──

export function listDirs(path?: string) {
  const qs = path ? `?path=${encodeURIComponent(path)}` : "";
  return request<{
    ok: boolean;
    path: string;
    parent: string | null;
    entries: Array<{
      name: string;
      path: string;
      is_git_repo: boolean;
    }>;
    roots: string[];
  }>(`/review/dirs${qs}`);
}

// ── PR / MR ──

export function listPRs(repo_url: string, state = "open") {
  const qs = `?repo_url=${encodeURIComponent(repo_url)}&state=${state}`;
  return request<{
    ok: boolean;
    platform: string;
    repo: string;
    prs: Array<{
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
    }>;
    total: number;
  }>(`/pr/list${qs}`);
}

export function getPRDetail(number: number, repo_url: string) {
  const qs = `?repo_url=${encodeURIComponent(repo_url)}`;
  return request<{
    ok: boolean;
    pr: {
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
      changed_files: Array<{
        file_path: string;
        change_type: string;
        additions: number;
        deletions: number;
      }>;
      raw_diff: string;
      total_additions: number;
      total_deletions: number;
    };
  }>(`/pr/${number}${qs}`);
}

export function getGitToken(platform: string) {
  return request<{ platform: string; has_token: boolean; token_masked: string }>(
    `/pr/token?platform=${platform}`
  );
}

export function setGitToken(platform: string, token: string) {
  return request<{ ok: boolean; platform: string; error?: string }>("/pr/token", {
    method: "PUT",
    body: JSON.stringify({ platform, token }),
  });
}

// ── File Tree ──

export function getFileTree(dir_path?: string, revision?: string, repo_path?: string) {
  const qs = new URLSearchParams();
  if (dir_path) qs.set("dir_path", dir_path);
  if (revision) qs.set("revision", revision);
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{
    ok: boolean;
    repo_path: string;
    revision: string;
    dir_path: string;
    entries: Array<{ name: string; path: string; is_dir: boolean }>;
  }>(`/review/tree?${qs.toString()}`);
}

// ── Code Search ──

export function searchCode(q: string, repo_path?: string, revision?: string, case_sensitive?: boolean) {
  const qs = new URLSearchParams();
  qs.set("q", q);
  if (repo_path) qs.set("repo_path", repo_path);
  if (revision) qs.set("revision", revision);
  if (case_sensitive) qs.set("case_sensitive", "true");
  return request<{
    ok: boolean;
    query: string;
    revision: string;
    results: Array<{ file: string; line: number | string; content: string }>;
    total: number;
  }>(`/review/search?${qs.toString()}`);
}

// ── Open in VS Code ──

export function openInVSCode(file_path: string, repo_path?: string) {
  const qs = new URLSearchParams();
  qs.set("file_path", file_path);
  if (repo_path) qs.set("repo_path", repo_path);
  return request<{ ok: boolean; file_path: string; abs_path: string }>(
    `/review/open-in-vscode?${qs.toString()}`,
    { method: "POST" }
  );
}

// ── AI Multi-Commit Review ──

export function aiReviewCommits(body: {
  commit_shas: string[];
  repo_path?: string;
}) {
  return request<{ task_id: string; status: string }>("/review/ai-review-commits", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function aiReviewResult(taskId: string) {
  return request<{
    ok: boolean;
    status: string;
    report?: string;
    commit_infos?: Array<{
      sha: string;
      short_sha: string;
      author: string;
      date: string;
      message: string;
    }>;
    changed_files?: Array<{
      file_path: string;
      change_type: string;
      additions: number;
      deletions: number;
    }>;
    total_additions?: number;
    total_deletions?: number;
    model?: string;
    provider?: string;
    tokens?: { prompt: number; completion: number; total: number };
    error?: string;
  }>(`/review/ai-review-result/${taskId}`);
}

/**
 * AI 审查多个提交 — SSE 流式版。
 * 返回原生 fetch Response，调用方通过 res.body.getReader() 逐块读取。
 * 注意：不走 request() 封装，避免自动超时 abort。
 */
export function aiReviewStream(body: {
  commit_shas: string[];
  repo_path?: string;
}): Promise<Response> {
  return fetch(`${BASE}/review/ai-review-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Review Checklists ──

export function getChecklists() {
  return request<{
    ok: boolean;
    checklists: Record<string, { name: string; items: Array<{ id: string; label: string; hint: string }> }>;
  }>("/review/checklists");
}

export function saveChecklist(name: string, items: Array<{ id: string; label: string; hint: string }>) {
  return request<{ ok: boolean; name: string; items: number; error?: string }>("/review/checklists", {
    method: "PUT",
    body: JSON.stringify({ name, items }),
  });
}

// ── HTTP Proxy (API Client / Postman-like) ──

export interface ProxyRequestBody {
  method: string;
  url: string;
  headers: Record<string, string>;
  query_params: Record<string, string>;
  body: string | null;
  content_type: string | null;
  timeout_seconds: number;
  verify_ssl?: boolean;
}

export interface ProxyResponseBody {
  ok: boolean;
  status: number;
  status_text: string;
  headers: Record<string, string>;
  body: string;
  timing_ms: number;
  error: string;
}

export function sendProxyRequest(req: ProxyRequestBody) {
  return request<ProxyResponseBody>("/proxy", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ── AI 增强调用链分析 ──

export interface AiTraceRequestBody {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string;
  source_root?: string;
}

export interface AiTraceResult {
  ok: boolean;
  ai_swimlane: string;
  ai_summary: string;
  call_chain: Array<{
    name: string;
    kind: string;
    file_path: string;
    line_number: number;
    code?: string;
  }>;
  tables: Array<{
    table_name: string;
    class_name: string | null;
    operation: string;
    location: string;
    file_path: string;
    line_number: number;
  }>;
  swimlane: string;
  diagram_nodes: Array<{
    id: string;
    name: string;
    kind: string;
    file_path: string;
    line_number: number;
  }>;
  diagram_edges: Array<{ from: string; to: string }>;
  route_info: {
    method: string;
    path: string;
    handler: string;
    file_path: string;
    line_number: number;
  } | null;
  error: string;
}

export function aiAnalyzeRequest(body: AiTraceRequestBody) {
  return request<AiTraceResult>("/analyzer/ai-trace", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutSeconds: 120,
  });
}

// ── Global Settings ──

export function getGlobalSettings() {
  return request<{
    data: {
      token_burst_limit: number;
      token_refill_rate: number;
      sandbox_timeout: number;
      sandbox_cpu_limit: number;
      sandbox_memory_limit: string;
      sqlguard_enabled: boolean;
      sqlguard_block_ddl: boolean;
      sqlguard_block_unconditional_dml: boolean;
      agent_max_concurrency: number;
    };
    updated_at: string | null;
  }>("/admin/settings");
}

export function updateGlobalSettings(updates: Record<string, any>) {
  return request<{ ok?: boolean; error?: string; data?: any; updated_at?: string }>(
    "/admin/settings",
    {
      method: "PUT",
      body: JSON.stringify(updates),
    }
  );
}
