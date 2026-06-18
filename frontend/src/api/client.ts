const BASE = "http://localhost:8000/api/v1";

let token: string | null = localStorage.getItem("access_token");
let _refreshToken: string | null = localStorage.getItem("refresh_token");

export function setToken(t: string | null) {
  token = t;
  if (t) localStorage.setItem("access_token", t);
  else localStorage.removeItem("access_token");
}

export function setRefreshToken(rt: string | null) {
  _refreshToken = rt;
  if (rt) localStorage.setItem("refresh_token", rt);
  else localStorage.removeItem("refresh_token");
}

export function getToken() {
  return token;
}

export function getRefreshToken() {
  return _refreshToken;
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts?.headers as Record<string, string> || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });

  // Auto-refresh on 401 (skip refresh endpoint itself to avoid loop)
  if (res.status === 401 && _refreshToken && path !== "/auth/refresh") {
    try {
      const refreshRes = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: _refreshToken }),
      });
      if (!refreshRes.ok) throw new Error("刷新令牌失败");
      const data = await refreshRes.json();
      setToken(data.access_token);
      setRefreshToken(data.refresh_token);
      headers["Authorization"] = `Bearer ${data.access_token}`;
      const retry = await fetch(`${BASE}${path}`, { ...opts, headers });
      if (!retry.ok) {
        const err = await retry.text();
        throw new Error(`${retry.status}: ${err}`);
      }
      return retry.json();
    } catch {
      // Refresh failed — clear tokens and reject
      setToken(null);
      setRefreshToken(null);
      throw new Error("401：会话已过期，请重新登录");
    }
  }

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json();
}

// ── Auth ──
export function login(username: string, password: string) {
  return request<{ access_token: string; refresh_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function refreshToken(refresh_token: string) {
  return request<{ access_token: string; refresh_token: string }>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token }),
  });
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

// ── Approvals ──
export function getPendingApprovals() {
  return request<{ items: any[]; total: number }>("/approvals/pending");
}

export function getPendingApproval(taskId: string) {
  return request<{
    task_id: string;
    node_name: string;
    prompt: string;
    context: { danger_count: number; items: any[] };
  }>(`/approvals/pending/${taskId}`);
}

export function respondApproval(taskId: string, decision: string, feedback: string) {
  return request<any>("/approvals/respond", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId, decision, feedback }),
  });
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
    }>;
  }>("/admin/prompts");
}

export function updatePrompt(agent: string, system?: string, user_template?: string) {
  return request<{ ok: boolean; agent: string; error?: string }>(`/admin/prompts/${agent}`, {
    method: "PUT",
    body: JSON.stringify({ system: system ?? null, user_template: user_template ?? null }),
  });
}

export function resetPrompt(agent: string) {
  return request<{ ok: boolean; agent: string; message?: string; error?: string }>(
    `/admin/prompts/${agent}`,
    { method: "DELETE" }
  );
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
