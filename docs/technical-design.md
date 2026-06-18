# mix-agent 技术设计文档

| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 | 2026-06-18 | 初稿，基于需求文档 V1.0 |

---

## 1. 系统概述

mix-agent 是一个企业级多智能体协同代码安全审计系统，以 Tauri 桌面应用为入口，FastAPI 为后端，通过 LangGraph 编排多 Agent 对代码变更进行全链路安全分析。

**核心能力**：模糊需求解析 → Git Diff 增量分析 → Tree-sitter AST 提取（不送源码给 LLM）→ 规则引擎前置判定风险 → LLM 解释与审查 → Human-in-the-Loop 审批 → 报告导出。

**分期交付**：Phase 1（1 个月）确定性扫描 → Phase 2（2 个月）Agent 化 → Phase 3（3 个月）高级能力。

---

## 2. 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     Tauri Desktop App                        │
│  ┌─────────────────────┐    invoke()    ┌──────────────────┐ │
│  │  React 18 + Vite    │◄─────────────►│  Rust Backend    │ │
│  │  (WebView)          │  Tauri IPC    │  (src-tauri/)    │ │
│  │                     │               │  • git diff      │ │
│  │  Pages:             │               │  • File read     │ │
│  │  /login             │               │  • Dialog open   │ │
│  │  /tasks             │               │  • File watch    │ │
│  │  /tasks/:id         │               └──────────────────┘ │
│  │  /approvals         │                                     │
│  │  /settings/*        │──────── HTTP/HTTPS ────────────────│
│  └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                 FastAPI Backend (backend/)                   │
│                                                              │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  api/    │  │  agents/         │  │  tools/           │  │
│  │  v1_tasks│  │  graph.py        │  │  parser/          │  │
│  │  v1_appro│  │  nodes.py        │  │  sandbox/         │  │
│  │  deps.py │  │  prompts.py      │  │  security/        │  │
│  └──────────┘  └──────────────────┘  │  vcs/             │  │
│                                       └───────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LangGraph StateGraph (Phase 2)                       │   │
│  │  parse_req → code_review → sql_audit → summary       │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ PostgreSQL │  │   Redis    │  │   Qdrant   │
     │ (主库)     │  │ (缓存/CP)  │  │ (Phase 2)  │
     └────────────┘  └────────────┘  └────────────┘
```

---

## 3. 数据模型（PostgreSQL）

### 3.1 核心表

```sql
-- 用户与认证
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'developer',  -- developer / auditor / admin
    team_id UUID REFERENCES teams(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 任务
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    team_id UUID REFERENCES teams(id),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
        -- pending / running / awaiting_approval / completed / failed / cancelled
    description TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    target_branch VARCHAR(256) NOT NULL,
    base_branch VARCHAR(256) NOT NULL DEFAULT 'main',
    path_filter VARCHAR(512),
    task_type VARCHAR(16) DEFAULT 'standard',  -- quick_scan / standard / deep
    cost_budget NUMERIC(8,4) DEFAULT 0.05,
    -- accumulated_cost 由 agent_token_logs 表 SUM 聚合得到（避免并发写入冲突）
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- 变更文件（Git Diff 产出）
CREATE TABLE diff_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    change_type VARCHAR(16) NOT NULL,  -- added / modified / deleted / renamed
    additions INT DEFAULT 0,
    deletions INT DEFAULT 0
);

-- 审计发现（各分析节点的产出）
CREATE TABLE audit_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent VARCHAR(64) NOT NULL,      -- sql_audit / code_review / config_audit / ...
    finding_type VARCHAR(64) NOT NULL,  -- sql_injection / hardcoded_secret / ...
    risk_level VARCHAR(16) NOT NULL,    -- safe / warning / danger
    file_path TEXT,
    line_number INT,
    code_snippet TEXT,
    description TEXT,
    recommendation TEXT,
    auto_fix_patch TEXT,                -- Phase 3
    is_deleted BOOLEAN DEFAULT FALSE,   -- 软删除（合规审计不留痕迹删除）
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 审批记录
CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES audit_findings(id) ON DELETE CASCADE,
    auditor_id UUID REFERENCES users(id),
    decision VARCHAR(16) NOT NULL,  -- approve / reject / modify
    feedback TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 审计报告
CREATE TABLE audit_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE UNIQUE,
    format VARCHAR(8) NOT NULL DEFAULT 'json',  -- json / md / pdf
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 操作审计日志
CREATE TABLE audit_operation_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    team_id UUID,
    action_type VARCHAR(64) NOT NULL,
    target_type VARCHAR(64),
    target_id UUID,
    detail JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- LLM 调用流水（成本追踪，避免 accumulated_cost 并发写入冲突）
CREATE TABLE agent_token_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id),
    agent VARCHAR(64) NOT NULL,        -- 调用方 Agent 名称
    model VARCHAR(64) NOT NULL,        -- 使用的模型
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    cost NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- LangGraph Checkpoint 持久化到 PostgreSQL（长周期 HiL 中断安全）
CREATE TABLE langgraph_checkpoints (
    thread_id UUID NOT NULL,
    checkpoint_ns VARCHAR(256) NOT NULL DEFAULT '',
    checkpoint_id UUID NOT NULL,
    parent_checkpoint_id UUID,
    type VARCHAR(32),                  -- 'pending' / 'interrupt' / 'resume'
    checkpoint JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX idx_tasks_user ON tasks (user_id, created_at DESC);
CREATE INDEX idx_tasks_team ON tasks (team_id, created_at DESC);
CREATE INDEX idx_tasks_status ON tasks (status) WHERE status IN ('running', 'awaiting_approval');
CREATE INDEX idx_findings_task ON audit_findings (task_id) WHERE NOT is_deleted;
CREATE INDEX idx_token_logs_task ON agent_token_logs (task_id);
CREATE INDEX idx_audit_user_time ON audit_operation_log (user_id, created_at DESC);
```

### 3.2 枚举值

| 字段 | 值 |
|------|----|
| `users.role` | `developer`, `auditor`, `admin` |
| `tasks.status` | `pending`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled` |
| `tasks.task_type` | `quick_scan` ($0.01), `standard` ($0.05), `deep` ($0.15) |
| `diff_files.change_type` | `added`, `modified`, `deleted`, `renamed` |
| `audit_findings.risk_level` | `safe`, `warning`, `danger` |
| `approvals.decision` | `approve`, `reject`, `modify` |

---

## 4. API 契约

### 4.1 认证

```
POST /api/v1/auth/login
Request:  { "username": "dev01", "password": "***" }
Response: { "access_token": "eyJ...", "refresh_token": "eyJ...", "expires_in": 86400 }

POST /api/v1/auth/refresh
Request:  { "refresh_token": "eyJ..." }
Response: { "access_token": "eyJ...", "expires_in": 86400 }
```

所有业务接口需携带 `Authorization: Bearer <access_token>`。

### 4.2 任务

```
POST /api/v1/tasks/
Request:  { "description": "...", "target_branch": "feature/x", "base_branch": "main" }
Response: { "task_id": "uuid", "status": "pending" }                        → 201

GET /api/v1/tasks/{task_id}
Response: { "task_id": "uuid", "status": "awaiting_approval", ... }         → 200

GET /api/v1/tasks/{task_id}/findings
Response: { "findings": [ { "agent": "sql_audit", "risk_level": "danger", ... } ] }

GET /api/v1/tasks/{task_id}/report?format=json|md|pdf
Response: binary (PDF) or JSON object                                        → 200

POST /api/v1/tasks/{task_id}/cancel
Response: { "task_id": "uuid", "status": "cancelled" }                       → 200
```

### 4.3 审批（需 `auditor` 或 `admin` 角色）

```
GET /api/v1/approvals/pending
Response: { "items": [ { "finding_id": "uuid", "description": "...", "risk": "danger" } ] }

GET /api/v1/approvals/{finding_id}
Response: { "finding_id": "uuid", "code_snippet": "...", "recommendation": "..." }

POST /api/v1/approvals/respond
Request:  { "finding_id": "uuid", "decision": "approve", "feedback": "已确认安全" }
Response: { "status": "ok" }                                                 → 200
```

### 4.4 系统管理（需 `admin` 角色）

```
# 模型配置
GET    /api/v1/admin/models          → 列出所有已配置模型
POST   /api/v1/admin/models          → 添加自定义模型
DELETE /api/v1/admin/models/{id}     → 删除模型

# 提示词管理
GET    /api/v1/admin/prompts         → 列出所有提示词
PUT    /api/v1/admin/prompts/{agent} → 更新提示词

# 成本看板
GET    /api/v1/admin/cost/overview   → 本月成本概览
GET    /api/v1/admin/cost/breakdown  → 按 Agent 拆解

# 审计日志
GET    /api/v1/admin/audit-log       → 查询操作记录 (支持 ?user_id= & ?from= & ?to=)
```

---

## 5. Agent 编排（LangGraph）

### 5.1 状态机定义

```
┌──────────────────────────────────────────────────────────────┐
│  LangGraph StateGraph (Phase 2 引入，仅编排 Agent 节点)       │
│                                                              │
│  State = AgentState {                                        │
│    task_id, description, target_branch, base_branch,         │
│    changed_files, git_diff_summary,                          │
│    parse_result, review_result, sql_result,                  │
│    api_path_result, config_result, dep_result,              │
│    pending_approval, summary, accumulated_cost               │
│  }                                                           │
│                                                              │
│  ┌─────────────────┐                                        │
│  │ parse_requirement│  → LLM (MiniMax)                      │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ orchestrator    │  → 混合路由（确定性规则前置 + LLM 补充）│
│  │                 │     1. 规则引擎强制激活:                │
│  │                 │        • diff 含 .sql / import sqlalchemy│
│  │                 │        → 强制激活 sql_audit              │
│  │                 │        • diff 含 pyproject.toml /        │
│  │                 │          package.json → 强制激活 dep_risk │
│  │                 │        • diff 含 config.yaml / .env      │
│  │                 │          → 强制激活 config_audit          │
│  │                 │     2. LLM 语义补充（仅解析模糊需求）:   │
│  │                 │        • "检查用户模块" → 补充激活       │
│  │                 │           code_review                    │
│  │                 │        • "有没有安全问题" → 默认全部激活 │

[more lines below; pass offset=325 to continue]
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ code_review     │  → LLM (DeepSeek) AST 语义审查          │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ sql_risk_explain│  → LLM (DeepSeek) SQL 风险解读          │
│  │  ↓ 发现高危     │                                        │
│  │  [interrupt]    │  ← Human-in-the-Loop 中断点             │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ summary         │  → LLM (DeepSeek) 报告生成              │
│  └─────────────────┘                                        │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 工具层（不走 LangGraph，纯函数 asyncio.gather）

```python
# Phase 1: 工具层为普通 Python 函数，并行执行
# Semaphore 控制高负载工具的并发度
_sandbox_sem = asyncio.Semaphore(2)   # Docker 沙箱最多 2 并发
_ast_sem = asyncio.Semaphore(4)       # AST 解析最多 4 并发

async def run_tools(state: TaskState) -> ToolResults:
    async def run_sandbox():
        async with _sandbox_sem:
            return await trivy_sandbox.scan(state.repo_path)

    async def run_ast():
        async with _ast_sem:
            return await ast_analyzer.parse_files(state.changed_files)

    results = await asyncio.gather(
        git_diff(state.repo_path, state.target_branch, state.base_branch),
        run_ast(),
        sqlguard.audit_batch(state.sql_statements),
        secret_scanner.scan(state.changed_files),
        run_sandbox(),
    )
    return merge(results)

# LLM 调用统一封装指数退避 + Jitter
async def llm_call_with_retry(model: str, prompt: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await llm.chat(model, prompt)
        except RateLimitError:
            wait = (2 ** attempt) + random.uniform(0, 1)  # 1s → 2s → 4s + jitter
            await asyncio.sleep(wait)
    raise LLMServiceError("Max retries exceeded")

# Phase 2: Agent 节点注册到 LangGraph
graph = StateGraph(AgentState)
graph.add_node("parse_requirement", parse_requirement_node)  # LLM
graph.add_node("orchestrator", orchestrator_node)            # LLM
graph.add_node("code_review", code_review_node)              # LLM
graph.add_node("sql_risk_explain", sql_risk_explain_node)    # LLM
graph.add_node("summary", summary_node)                      # LLM

graph.set_entry_point("parse_requirement")
graph.add_edge("parse_requirement", "orchestrator")
graph.add_conditional_edges("orchestrator", route, {...})
graph.add_edge("code_review", "sql_risk_explain")
graph.add_edge("sql_risk_explain", "summary")
graph.add_edge("summary", END)
```

### 5.3 HiL 中断点

```python
@graph.add_node("sql_risk_explain")
def sql_risk_explain_node(state: AgentState):
    result = explain_sql_risks(state)
    if result.has_danger:
        # LangGraph 内置中断。
    # Checkpoint 持久化到 PostgreSQL（支持长周期中断，安全重启不丢状态）
        approval = interrupt({
            "type": "human_approval",
            "finding_id": result.danger_finding.id,
            "prompt": result.danger_finding.description
        })
        # 外部 API POST /api/v1/approvals/respond → Command(resume=approval)
    return {"sql_result": result}
```

### 5.4 Phase 1 → Phase 2 过渡方案

当系统从 Phase 1 升级到 Phase 2 时，工具层纯函数无缝升级为 LangGraph 内置 Tool：

```python
# Phase 1: 纯函数
results = await asyncio.gather(
    git_diff(...), ast_analyzer.parse_files(...), sqlguard.audit_batch(...), ...
)

# Phase 2: LangGraph Tool（函数签名不变，增加装饰器）
from langgraph.prebuilt import ToolNode

@tool
def sqlguard_audit(sqls: list[str]) -> AuditResult:
    """SQLGlot 语法树审计，返回规则命中结果"""
    return sqlguard.audit_batch(sqls)  # ← 核心逻辑完全复用

# 注册为 LangGraph Tool Node
tool_node = ToolNode([git_diff_tool, ast_analyzer_tool, sqlguard_audit, ...])
graph.add_node("tools", tool_node)
```

关键原则：
- 核心逻辑无改动，仅包装为 LangGraph Tool
- Phase 1 的 `asyncio.gather` 并行执行方式在 Phase 2 中通过 LangGraph 的并行节点机制等价替换
- 工具函数保持确定性（无副作用），确保两个阶段的结果一致

---

## 6. Agent 详细设计

### 6.1 Agent 清单

| Agent | Phase | LLM | 输入 | 输出 | 工具 |
|-------|-------|-----|------|------|------|
| 前端交互 Agent | 2 | MiniMax | 用户自然语言 | 结构化任务描述 | 仅 LLM chat |
| 需求解析 Agent | 2 | MiniMax | 任务描述 + diff 上下文 | 任务分类 + 范围 | LLM chat |
| 编排 Agent | 2 | DeepSeek | 需求解析结果 | 分析路径激活列表 | LangGraph |
| 代码 Review Agent | 2 | DeepSeek | AST 符号表 + diff 信息 | Review 意见 + ORM 风险标记 | Tree-sitter |
| SQL 审计 Agent | 2 | DeepSeek | SQL 规则命中结果 | 风险解读（可能触发 HiL） | SQLGlot |
| 接口路径 Agent | 3 | DeepSeek | 路由清单 + 调用链 | 路径分析报告 | Route Scanner |
| 配置审计 Agent | 2 | MiniMax | 配置缺陷列表 | 配置审计报告 | 正则引擎 |
| 依赖风险 Agent | 2 | MiniMax | CVE 清单 | CVE 解读 | Trivy/pip-audit |
| 修复建议 Agent | 3 | DeepSeek | 所有发现项 | 修复 diff（不 commit） | Git patch |
| 汇总 Agent | 2 | DeepSeek | 全部分析结果 | 综合审计报告 | — |
| 数据 Agent | 2 | MiniMax | 检索查询 | 上下文注入 | Qdrant/Redis |

### 6.2 编排 Agent 决策规则（混合路由）

```
输入: parse_result (结构化任务描述) + changed_files (diff 产出)
输出: { activated_paths: [...], skip_paths: [...], cost_estimate: $X.XX }

【阶段一：确定性规则强制激活（不可被 LLM 跳过）】

| 触发条件 (文件模式匹配)                   | 强制激活路径     |
|------------------------------------------|-----------------|
| diff 含 *.sql / import sqlalchemy /      | SQL 审计         |
|        ORM 链式调用 AST 命中              |                  |
| diff 含 pyproject.toml / package.json /   | 依赖风险分析     |
|        pom.xml / go.mod                   |                  |
| diff 含 config.yaml / .env / settings.py  | 安全配置审计     |
| diff 含 @app.route / APIRouter /          | 接口路径分析     |
|        createRouter / beforeEach           |                  |

【阶段二：LLM 语义补充（解析模糊需求，增量激活）】

规则:
1. 描述含 "代码"/"逻辑"/"review"   → 激活代码 Review
2. 描述含 "接口"/"API"/"鉴权"      → 激活接口路径（阶段一可能已激活）
3. 若 cost_estimate > 成本预算 × 0.8 → 跳过代码 Review 和接口路径
4. 若 RAG 命中 7 天内相同文件       → 跳过 LLM，复用历史结果

关键原则：LLM 不作为路由的唯一闸口，确定性规则永远优先。
```

---

## 7. 安全设计

### 7.1 认证链路

```
Tauri App                  FastAPI                    PostgreSQL
    │                         │                          │
    │  POST /auth/login       │                          │
    │ ──────────────────────► │ bcrypt.verify(password)  │
    │                         │ ────────────────────────►│
    │                         │ ◄─────────────────────── │
    │ ◄── JWT (role, exp) ── │                          │
    │                         │                          │
    │  Authorization: Bearer  │                          │
    │ ──────────────────────► │ jwt.decode + role check  │
```

- JWT: HS256, access_token 24h, refresh_token 7d
- 角色: `developer` / `auditor` / `admin`
- 审批接口额外校验 `role ∈ {auditor, admin}`

### 7.2 数据安全

- 源码不传给 LLM：仅传输 Tree-sitter 提取的符号表和行号
- **AST 符号表样例**（绝对不含源码，仅结构和位置）：

```json
{
  "file": "src/user_dao.py",
  "language": "python",
  "symbols": [
    {
      "type": "class",
      "name": "UserDAO",
      "line": 15,
      "methods": [
        { "name": "get_by_id", "line": 20, "params": ["user_id: int"], "return": "User | None" },
        { "name": "delete_expired", "line": 42, "params": [], "return": "int",
          "calls": ["session.query(User).delete", "session.commit"],
          "orm_chain": "query → delete (NO filter detected ⚠️)" }
      ]
    }
  ],
  "imports": ["sqlalchemy.orm.Session", "datetime"],
  "annotations": {
    "line_42": "ORM 链式调用未挂载 filter()/where()，存在全表删除风险"
  }
}
```

> 安全合规说明：LLM 收到的仅为此 JSON，不含任何原始代码行内容。符号位置信息（`line: 42`）用于前端 DiffViewer 定位展示。

- HTTPS 强制（生产环境），本地 dev 可 HTTP localhost
- 敏感信息入库前脱敏（`secret_scanner` 扫描报告内容）
- `audit_operation_log` 记录所有操作，不可删除

### 7.3 Tauri 安全

- FS scope 运行时动态授权：用户通过 `dialog.open` 选择目录后，Rust 后端将该路径加入白名单
- Shell scope 仅允许 `git` 命令
- 应用退出时清除动态 scope

---

## 8. 部署架构

### 8.1 开发环境

```
┌─────────────────┐
│  Tauri App       │  npm run dev (Vite HMR + Tauri window)
│  localhost:1420  │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│  FastAPI         │  uvicorn mix_agent.main:app --reload --port 8000
│  localhost:8000  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  docker-compose up -d                    │
│  ├── PostgreSQL  :5432                  │
│  ├── Redis       :6379                  │
│  └── Qdrant      :6333  (Phase 2)      │
└─────────────────────────────────────────┘
```

### 8.2 生产环境

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Tauri App       │     │  Tauri App       │     │  GitLab CI       │
│  (Developer A)   │     │  (Developer B)   │     │  (mix-agent job) │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │ HTTPS
                                 ▼
                    ┌─────────────────────────┐
                    │  Nginx (TLS termination) │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  FastAPI (gunicorn)      │
                    │  workers: 4              │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
              ┌──────────┐ ┌────────┐ ┌──────────┐
              │PostgreSQL│ │ Redis  │ │ Qdrant   │
              │(RDS)     │ │(Cache) │ │(Phase 2) │
              └──────────┘ └────────┘ └──────────┘
```

---

## 9. 技术栈明细

| 组件 | 技术 | 版本 | Phase |
|------|------|------|-------|
| 后端语言 | Python | ≥ 3.11 | 1 |
| Web 框架 | FastAPI | ≥ 0.111 | 1 |
| 业务数据库 | PostgreSQL | ≥ 15 | 1 |
| 缓存/Checkpoint | Redis | ≥ 7 | 1 |
| ORM | SQLAlchemy 2.0 (async) | ≥ 2.0 | 1 |
| 数据库迁移 | Alembic | ≥ 1.12 | 1 |
| 多智能体编排 | LangGraph | ≥ 0.2 | 2 |
| AST 解析 | Tree-sitter | ≥ 0.22 | 1 |
| SQL 语法分析 | SQLGlot | ≥ 25 | 1 |
| 依赖扫描 | Trivy / pip-audit | latest | 1 |
| 沙箱隔离 | Docker SDK | ≥ 7 | 1 |
| 向量数据库 | Qdrant | ≥ 1.9 | 2 |
| LLM 网关 | MiniMax API + DeepSeek API | — | 2 |
| 桌面框架 | Tauri | 2.x | 1 |
| 前端框架 | React + Vite | 18 / 5 | 1 |
| UI 组件库 | Ant Design | 5.x | 1 |
| 状态管理 | React Query + Zustand | latest | 1 |
| 代码编辑器 | Monaco Editor | latest | 1 |
| 测试 | Pytest + Vitest + Playwright | latest | 1 |
| PDF 生成 | WeasyPrint | ≥ 60 | 1 |

---

## 10. 关键流程时序

### 10.1 Phase 1 审计流程

```
Developer                Tauri                 FastAPI              Tools              PostgreSQL
    │                      │                      │                    │                    │
    │  选择仓库 + 分支     │                      │                    │                    │
    │ ───────────────────► │                      │                    │                    │
    │                      │  dialog.open()       │                    │                    │
    │                      │  git branch -a       │                    │                    │
    │                      │                      │                    │                    │
    │  提交                │                      │                    │                    │
    │ ───────────────────► │  POST /tasks/        │                    │                    │
    │                      │ ────────────────────►│                    │                    │
    │                      │                      │  INSERT tasks      │                    │
    │                      │                      │ ─────────────────────────────────────►│
    │                      │  201 {task_id}       │                    │                    │
    │                      │ ◄────────────────────│                    │                    │
    │                      │                      │                    │                    │
    │                      │                      │  ┌─ asyncio.gather ──────────────────┐│
    │                      │                      │  │ git_diff()                       ││
    │                      │                      │  │ ast_analyzer.parse_files()       ││
    │                      │                      │  │ sqlguard.audit_batch()           ││
    │                      │                      │  │ secret_scanner.scan()            ││
    │                      │                      │  │ trivy.scan()                     ││
    │                      │                      │  └──────────────────────────────────┘│
    │                      │                      │                    │                    │
    │                      │                      │  INSERT findings   │                    │
    │                      │                      │ ─────────────────────────────────────►│
    │                      │                      │  UPDATE tasks.completed              │
    │                      │                      │ ─────────────────────────────────────►│
    │                      │                      │                    │                    │
    │  GET /tasks/{id}     │                      │  status=completed  │                    │
    │ ◄────────────────────│ ◄────────────────────│                    │                    │
```

### 10.2 Phase 2 审批流程（含长周期中断安全）

审批人员可能在数小时甚至数天后才操作。LangGraph 的 `interrupt()` 触发后，State 持久化到 **PostgreSQL**（`langgraph_checkpoints` 表），确保 FastAPI 重启或 Redis 过期都不会丢失中断状态。

```
Developer               Auditor               FastAPI            LangGraph           PostgreSQL
    │                      │                      │                    │                    │
    │  提交审计任务        │                      │                    │                    │
    │ ────────────────────►│                      │  POST /tasks/      │                    │
    │                      │                      │ ──────────────────►│                    │
    │                      │                      │                    │  run graph         │
    │                      │                      │                    │  ...               │
    │                      │                      │                    │  sql_risk @danger   │
    │                      │                      │                    │  interrupt()        │
    │                      │                      │ ◄──────────────────│                    │
    │                      │                      │  status=awaiting   │                    │
    │                      │                      │ ───────────────────►                    │
    │                      │                      │                    │                    │
    │                      │  GET /approvals/pend │                    │                    │
    │                      │ ◄────────────────────│                    │                    │
    │                      │                      │                    │                    │
    │                      │  POST /approvals/rsp │                    │                    │
    │                      │  { decision:approve }│                    │                    │
    │                      │ ────────────────────►│ Command(resume=..) │                    │
    │                      │                      │ ──────────────────►│                    │
    │                      │                      │                    │  continue → summary│
    │                      │                      │ ◄──────────────────│                    │
    │                      │                      │  INSERT approvals  │                    │
    │                      │                      │ ───────────────────►                    │
    │                      │                      │  status=completed   │                    │
    │                      │                      │ ───────────────────►                    │
```

---

## 11. 错误处理

| 场景 | HTTP Code | 响应 |
|------|-----------|------|
| 参数校验失败 | 422 | `{ "detail": [ { "loc": ["body","description"], "msg": "..." } ] }` |
| JWT 过期 | 401 | `{ "detail": "Token expired" }` |
| 权限不足 | 403 | `{ "detail": "Requires auditor role" }` |
| 任务不存在 | 404 | `{ "detail": "Task not found" }` |
| LLM 调用失败（重试后） | 500 | `{ "detail": "LLM service unavailable", "task_status": "degraded" }` |
| 成本超限 | 429 | `{ "detail": "Monthly budget exceeded", "retry_after": "next_month" }` |
| LangGraph 崩溃 | 500 | `{ "detail": "Task failed", "task_status": "failed", "can_retry": true }` |
