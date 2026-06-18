# mix-agent 开发任务文档

| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 | 2026-06-18 | 基于需求文档 V1.0 + 技术设计文档 V1.0 |

---

## 总体时间线

```
Phase 1 ───────────────────────────────── Phase 2 ───────────────────────────── Phase 3 ─────
Week 1  2  3  4              5  6  7  8  9  10  11  12  13  14  15  16   17  18  19  20  21  22  23  24  25  26  27  28
████████████████              ████████████████████████████████████████████ ██████████████████████████████████████████████████
```

| Phase | 工期 | 里程碑 |
|-------|------|--------|
| Phase 1 | 4 周 | 确定性扫描可上线，命令行可用 |
| Phase 2 | 12 周（1-2 人并行） | Agent 化完成，审批流可用，Tauri 桌面端可交付 |
| Phase 3 | 12 周 | 高级能力全部就绪，企业功能完整 |

> 注：Phase 2 推荐 2 人并行 —— 1 人负责 Agent 节点 + LangGraph，1 人负责 Tauri 桌面端。两个方向仅共享审批流 API（T2.4），可高度并行。单人开发按 12 周。

---

## Phase 1：确定性扫描

### 里程碑：`v0.1.0` — 命令行 + API 可用，不上 LLM

---

### T1.1 项目基础设施

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T1.1.1 Poetry 项目初始化，pyproject.toml 正确配置依赖 | — | 0.5d | — | `pyproject.toml` 可用 |
| T1.1.2 FastAPI 骨架：main.py + config.py + schemas.py | — | 1d | — | `/health` 返回 200 |
| T1.1.3 PostgreSQL + Redis Docker Compose | — | 0.5d | — | `docker-compose up` 启动 |
| T1.1.4 Alembic 初始化 + Phase 1 表迁移 | — | 1d | T1.1.3 | `alembic upgrade head` 建表 |
| T1.1.5 Pytest + conftest.py + 基础测试夹具 | — | 1d | T1.1.2 | 测试框架可运行 |

**验收标准**：
- `uvicorn mix_agent.main:app` 启动成功
- `pytest` 通过（含 fixture 加载）
- `alembic upgrade head` 创建 users / teams / tasks / diff_files / audit_findings / audit_operation_log 表

---

### T1.2 工具层实现

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T1.2.1 `tools/vcs/git_tool.py` — Git Diff 实现 | — | 2d | — | `git diff base...target` → changed_files |
| T1.2.2 `tools/parser/ast_analyzer.py` — AST 解析器（Phase 1 用 Python `ast` 标准库） | — | 2d | — | `.parse_files()` → 符号表 JSON |
| T1.2.3 `tools/security/sql_guard.py` — SQLGlot 审计门禁 | — | 2d | — | `.audit_batch()` → AuditResult[] |
| T1.2.4 `tools/security/secret_scanner.py` — 密钥/配置扫描 | — | 2d | — | `.scan()` → 配置缺陷列表 |
| T1.2.5 `tools/sandbox/container.py` — Docker 沙箱封装 | — | 2d | — | `sandbox.run(trivy)` → CVE 列表 |
| T1.2.6 工具层集成测试 | — | 1d | T1.2.1-5 | 每个工具单独测试通过 |

> **T1.2.2 优化**：Phase 1 使用 Python 标准库 `ast` 解析 Python 代码，免去 Tree-sitter 的 C 绑定和跨平台编译。Tree-sitter 多语言支持移入 Phase 2。

**验收标准**：
- 对自有代码仓运行 `git diff main...HEAD`，正确返回变更文件列表
- 对 `src/mix_agent/` 运行 Tree-sitter，输出合法 JSON 符号表
- SQLGuard 对 `DROP TABLE users` 返回 `risk_level=danger, is_blocked=true`
- Secret Scanner 对本项目 `.env` 检测出明文存储的 API Key 模板

---

### T1.3 核心 API

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T1.3.1 `POST /api/v1/tasks` — 创建任务 + 启动 analyze | — | 2d | T1.1.2, T1.2.1 | 提交任务 → Git Diff → 结果入库 |
| T1.3.2 `GET /api/v1/tasks/{id}` — 查询任务状态 | — | 0.5d | T1.3.1 | 返回 status + 进度 |
| T1.3.3 `GET /api/v1/tasks/{id}/findings` — 查询发现项 | — | 0.5d | T1.3.1 | 返回 audit_findings 列表 |
| T1.3.4 `GET /api/v1/tasks/{id}/report` — 报告导出 (JSON/MD) | — | 1d | T1.3.1 | JSON 报告 + Markdown 报告 |
| T1.3.5 `POST /api/v1/tasks/{id}/cancel` — 取消任务 | — | 0.5d | T1.3.1 | status → cancelled |
| T1.3.6 API 集成测试 | — | 1d | T1.3.1-5 | E2E: POST task → GET status → GET findings |

**验收标准**：
- `curl -X POST /api/v1/tasks/ -d '{"target_branch":"HEAD","base_branch":"main"}'` → 201
- 任务完成后 `GET /tasks/{id}/findings` 包含正确的发现项
- JSON 报告包含完整审计结果

---

### T1.4 Phase 1 里程碑验收

| 检查项 | 标准 |
|------|------|
| 命令行可用 | `mix-agent scan --repo . --target HEAD --base main` 输出报告 |
| API 可用 | 所有 T1.3 接口通过集成测试 |
| 确定性 | 同一代码仓跑两次，输出一致（无 LLM 引入的随机性） |
| 性能 | 10 万行代码仓 Phase 1 完成时间 < 30s |

---

## Phase 2：Agent 化

### 里程碑：`v0.2.0` — Tauri 桌面端 + LLM Agent + 审批流可用

---

### T2.1 LLM 基础设施

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.1.1 `services/llm.py` — LLM 调用封装（MiniMax + DeepSeek） | — | 2d | — | `llm.chat(model, prompt)` 统一接口 |
| T2.1.2 指数退避重试 + 成本累加器 | — | 1d | T2.1.1 | Rate Limit 429 自动重试 |
| T2.1.3 `agent_token_logs` 写入 | — | 0.5d | T2.1.1 | 每次 LLM 调用记录 token + cost |
| T2.1.4 RAG 检索封装 `services/rag.py` | — | 2d | T1.1.3 | `text-embedding` → Qdrant.search → 上下文注入 |

**验收标准**：
- `llm.chat("deepseek", "解释这段代码")` 返回合法响应
- 连续触发 429 3 次后自动退避重试成功
- `agent_token_logs` 写入记录正确

---

### T2.2 Agent 节点实现

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.2.1 建立 Prompt 管理规约 + `prompts/` 基础模板 | — | 1d | T2.1.1 | PromptManager 骨架 + 3 个 base .txt |
| T2.2.2 `agents/nodes/parse_requirement.py` — 需求解析 Agent | — | 2d | T2.1.1 | LLM 解析模糊需求 |
| T2.2.3 `agents/nodes/orchestrator.py` — 编排 Agent（混合路由） | — | 2d | T2.1.1 | 规则强制激活 + LLM 补充 |
| T2.2.4 `agents/nodes/code_review.py` — 代码 Review Agent | — | 3d | T2.1.1 | AST 符号表 → LLM 语义审查 |
| T2.2.5 `agents/nodes/sql_risk_explain.py` — SQL 风险解释 Agent | — | 2d | T2.1.1 | 规则命中 → LLM 解读 + HiL 中断 |
| T2.2.6 `agents/nodes/summary.py` — 汇总报告 Agent | — | 2d | T2.1.1 | 所有结果 → 综合报告 |
| T2.2.7 Agent 节点单元测试 | — | 2d | T2.2.2-6 | 每个节点独立测试 |

**验收标准**：
- 需求解析：输入 "检查用户模块的 SQL" → 返回结构化 `{target: "user_module", focus: ["sql"]}`
- 编排 Agent：检测到 `.sql` 文件变更 → 强制激活 SQL 审计路径
- SQL 解释：`DROP TABLE users` → HiL 中断，前端显示审批提示

---

### T2.3 LangGraph 状态机

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.3.1 `agents/graph.py` — 状态机构建（Mock Node 先行） | — | 2d | T2.1.1 | LangGraph StateGraph 骨架 + 路由流转可用 |
| T2.3.2 Redis Checkpointer → PostgreSQL Checkpointer | — | 1d | T2.3.1 | `langgraph_checkpoints` 表持久化 |
| T2.3.3 HiL 中断 + `Command(resume=...)` | — | 2d | T2.3.1 | 审批 API 恢复状态机 |
| T2.3.4 RAG 上下文注入（检索 → Prompt 拼接） | — | 1d | T2.1.4, T2.3.1 | Agent 节点获取历史上下文 |
| T2.3.5 状态机集成测试 | — | 2d | T2.3.1-4 | 完整流程 E2E |

**验收标准**：
- 状态机跑通完整流程：parse → orchestrate → code_review → sql_explain → summary
- 模拟服务器重启 → 从 `langgraph_checkpoints` 恢复状态 → 继续执行
- HiL 中断后 `POST /approvals/respond` → 状态机恢复

---

### T2.4 审批流 API

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.4.1 `POST /api/v1/auth/login` — JWT 签发 | — | 1d | — | 登录返回 access_token |
| T2.4.2 `GET /api/v1/auth/refresh` — Token 刷新 | — | 0.5d | T2.4.1 | refresh_token → 新 access_token |
| T2.4.3 JWT 中间件 + 角色校验 `deps.py` | — | 1d | T2.4.1 | `Depends(get_current_user)` / `require_admin` |
| T2.4.4 `GET /api/v1/approvals/pending` — 待审批列表 | — | 1d | T2.3.3, T2.4.3 | 返回等待审批的 audit_findings |
| T2.4.5 `POST /api/v1/approvals/respond` — 提交审批决策 | — | 1d | T2.3.3, T2.4.3 | `Command(resume=...)` 恢复状态机 |
| T2.4.6 审批流集成测试 | — | 1d | T2.4.1-5 | 登录 → 提交任务 → 审批 → 查看结果 |

**验收标准**：
- 无 Token 访问审批接口 → 401
- `developer` 角色访问审批接口 → 403
- `auditor` 审批通过 → 状态机恢复 → 任务完成

---

### T2.5 Tauri 桌面端

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.5.1 Tauri 项目初始化 `src-tauri/` + React 脚手架 | — | 1d | — | `npm run dev` 启动 |
| T2.5.2 Rust 命令：`read_local_repo`, `list_branches`, `git_diff`, `read_file_content` | — | 2d | T2.5.1 | 4 个 Tauri 命令可用 |

> **T2.5.2 优化**：使用 Rust `std::process::Command::new("git")` 调用本地 Git CLI 并解析 stdout，避免 `git2-rs` 的繁琐生命周期和错误处理。前提：用户本地已安装 Git。
| T2.5.3 React 页面：登录页 + 首页（任务提交） | — | 2d | T2.5.1 | `/login`, `/` 可用 |
| T2.5.4 React 页面：任务列表 + 任务详情 | — | 2d | T2.5.3 | `/tasks`, `/tasks/:id` |
| T2.5.5 React 页面：审批页 + 设置页（成本看板） | — | 2d | T2.5.3 | `/approvals`, `/settings/cost` |
| T2.5.6 Zustand + React Query 集成 | — | 1d | T2.5.3-5 | 状态管理 + 轮询 |
| T2.5.7 Tauri 安全配置（FS scope 动态授权） | — | 1d | T2.5.2 | `tauri.conf.json` + Rust 动态 scope |
| T2.5.8 Tauri 打包 + E2E 测试 | — | 2d | T2.5.2-7 | `.msi` / `.dmg` 可安装 |

**验收标准**：
- 桌面应用打开 → 登录 → 选择本地仓库 → 选分支 → 提交 → 看到轮询进度 → 查看报告
- 审批页显示待审批项 → 审批后状态更新
- 成本看板显示正确的成本数据

---

### T2.6 成本管理

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.6.1 成本累加器（`agent_token_logs` SUM 聚合） | — | 0.5d | T2.1.3 | 实时累计成本 |
| T2.6.2 CostBudget 检查（`cost_budget * 0.8` 降级） | — | 1d | T2.6.1 | 编排 Agent 检查预算 |
| T2.6.3 `GET /api/v1/admin/cost` — 成本看板 API | — | 1d | T2.6.1 | 按 Agent/任务/模型 拆解 |

---

### T2.7 Qdrant + RAG

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T2.7.1 Qdrant Docker Compose 集成 | — | 0.5d | — | Qdrant 可用 |
| T2.7.2 `services/vector_db.py` — 向量存储封装 | — | 1d | T2.7.1 | `upsert` / `search` |
| T2.7.3 审计报告入库（`knowledge` collection） | — | 1d | T2.7.2 | 每次审计后自动向量化 |
| T2.7.4 RAG 检索集成到 Agent 节点 | — | 1d | T2.7.3, T2.1.4 | 4 个检索场景可用 |

---

### T2.8 Phase 2 里程碑验收

| 检查项 | 标准 |
|------|------|
| 桌面端可用 | Tauri 应用可安装、登录、提交、查报告 |
| Agent 可用 | LLM 驱动的分析结果比 Phase 1 更准确 |
| 审批流可用 | 高危操作挂起 → 审批 → 放行完整闭环 |
| 成本可控 | 月成本可追踪、可降级、可封顶 |

---

## Phase 3：高级能力

### 里程碑：`v1.0.0` — 全功能 GA

---

### T3.1 API 调用链分析

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T3.1.1 `tools/parser/route_scanner.py` — FastAPI 路由扫描 | — | 3d | — | 扫描 `@app.get/post` + `APIRouter` |
| T3.1.2 Vue Router 扫描（`createRouter` + `beforeEach`） | — | 2d | — | 扫描 `src/router/` |
| T3.1.3 函数调用链追踪（AST 深度遍历） | — | 3d | T3.1.1 | 路由 → Service → DAO → DB |
| T3.1.4 `agents/nodes/api_path.py` — 接口路径 Agent | — | 2d | T3.1.1-3, T2.1.1 | LLM 分析未鉴权路由 |
| T3.1.5 集成测试 | — | 1d | T3.1.1-4 | 自有代码仓分析通过 |

---

### T3.2 AutoFix

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T3.2.1 `agents/nodes/auto_fix.py` — 修复建议 Agent | — | 3d | T2.1.1 | LLM 生成修复 diff |
| T3.2.2 修复验证回路（Docker 沙箱运行 `pytest` / `npm run build`） | — | 2d | T3.2.1 | 验证失败 → 拒绝 |
| T3.2.3 前端 DiffViewer + 「应用修复」按钮 | — | 2d | T3.2.1 | Monaco Diff Editor 展示 |
| T3.2.3.5 局部文件备份与回滚机制（Rust 侧 `.bak` + `git stash`） | — | 1d | T3.2.3 | 修改前自动备份，防止破坏未提交代码 |
| T3.2.4 Tauri Rust 端文件修改 + 应用补丁 | — | 1d | T3.2.3.5 | `apply_patch()` 命令 |
| T3.2.5 F22 AI 代码可读化（4 层滤网 — Layer 1+2 优先） | — | 3d | T3.2.3 | 意图摘要 + Diff 锚点（Layer 3/4 按需补充） |

---

### T3.3 合规审计

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T3.3.1 `compliance_rules/` — YAML 规则引擎 | — | 2d | — | OWASP + GDPR + PCI-DSS + 等保 |
| T3.3.2 `tools/security/compliance_checker.py` — 合规扫描 | — | 2d | T3.3.1 | 规则命中 → 违规列表 |
| T3.3.3 `agents/nodes/compliance.py` — 合规检查 Agent | — | 2d | T3.3.2, T2.1.1 | LLM 解释违规 |

---

### T3.4 Watch Mode + CI/CD

| 任务 | 负责人 | 预估 | 前置 | 产出 |
|------|--------|------|------|------|
| T3.4.1 Tauri Rust `notify` crate 集成 | — | 2d | — | 文件系统变更监听 |
| T3.4.2 Watch Mode 自动触发审计 | — | 1d | T3.4.1 | 保存文件 → 自动 diff → 审计 |
| T3.4.3 GitLab CI 模板 | — | 1d | — | `.gitlab-ci.yml` |
| T3.4.4 GitHub Actions 模板 | — | 1d | T3.4.3 | `action.yml` |

---

### T3.5 Phase 3 里程碑验收

| 检查项 | 标准 |
|------|------|
| API 调用链 | 自有代码仓的 `/api/v1/tasks` 调用链展示完整 |
| AutoFix | 生成修复 diff → Docker 验证通过 → 用户确认应用 |
| 合规审计 | OWASP Top 10 规则对自己项目扫描通过 |
| Watch Mode | 修改文件 → 自动触发审计 → 桌面通知 |
| CI/CD | GitLab CI 跑 mix-agent 容器 → exit code 正确 |

---

## 任务汇总

| Phase | 任务数 | 总预估天数 | 关键依赖 |
|-------|--------|-----------|---------|
| Phase 1 | 16 | 18d (≈ 4 周) | 工具层 → API |
| Phase 2 | 30 | 45d (≈ 12 周 solo / 8 周 2人) | LLM 基础 → Agent 节点 + Tauri 并行 |
| Phase 3 | 17 | 31d (≈ 8 周) | Phase 2 完整 |
| **合计** | **63** | **94d** | |

> 2-3 人并行可压缩至 16-20 周（4-5 个月）。

---

## Phase 2 推荐依赖拓扑

```
[T2.1 LLM 基础] ────► [T2.3 LangGraph 状态机(Mock Node)] ──► [注入具体 T2.2 Agent 节点]
           │
           ├────► [T2.2 Prompt 模板 + Agent 节点开发] ────────┘
           │
           └────► [T2.4 审批流 API] ────────────────────────► [T2.5 Tauri 桌面端对接]
                                                                      │
                                                       [Tauri 与 Agent 全并行开发]
```
| **合计** | **62** | **96d (≈ 20 周)** | |

> 注：以上为单人预估。2-3 人并行开发可压缩至 12-16 周（3-4 个月）。

---

## 风险清单

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM API 不稳定 | Phase 2/3 阻塞 | 指数退避重试 + 模型降级 + Phase 1 可独立运行 |
| Python `ast` 库无法处理复杂作用域 | F4 代码 Review 受限 | Phase 2 切换 Tree-sitter，Phase 1 先用 `ast` 兜底 |
| Qdrant 向量精度不够 | RAG 检索命中率低 | 评估 bge-large-zh vs text-embedding-3-small 后选用 |
| Tauri 打包签名问题 | 分发受阻 | Phase 2 先提供 `tauri dev` 模式；生产签名延期 |
| 大模型成本超预算 | 服务中断 | CostBudget 封顶 + 环境分级 + 管理员告警 |
| PostgreSQL Checkpointer 与 SQLAlchemy 连接池冲突 | 状态机中断恢复失败 | T2.3.2 提前调研 LangGraph PG adapter 的 asyncpg 配置 |
| Tauri FS scope 动态授权版本差异 | 安全配置功能延期 | 明确使用 Tauri 2.x API，预留 1 天调研缓冲 |
