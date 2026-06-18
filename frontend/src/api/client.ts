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
      if (!refreshRes.ok) throw new Error("refresh failed");
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
      throw new Error("401: Session expired, please login again");
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
