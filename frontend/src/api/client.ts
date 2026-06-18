const BASE = "http://localhost:8000/api/v1";

let token: string | null = localStorage.getItem("access_token");

export function setToken(t: string | null) {
  token = t;
  if (t) localStorage.setItem("access_token", t);
  else localStorage.removeItem("access_token");
}

export function getToken() {
  return token;
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts?.headers as Record<string, string> || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
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
