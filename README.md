<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=fff" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=000" alt="React">
  <img src="https://img.shields.io/badge/Rust-Tauri_v2-FFD700?logo=rust&logoColor=fff" alt="Tauri">
  <img src="https://img.shields.io/badge/LangGraph-0.0.60-7B68EE" alt="LangGraph">
  <br>
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=fff" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=fff" alt="Redis">
  <img src="https://img.shields.io/badge/Qdrant-vector_db-00B4D8" alt="Qdrant">
  <img src="https://img.shields.io/badge/license-Proprietary-important" alt="License">
</p>

<h1 align="center">mix-agent</h1>
<h3 align="center">企业级多智能体代码安全审计协同系统</h3>
<p align="center"><em>Enterprise Multi-Agent Code Security Audit Collaboration System</em></p>

---

## 📖 项目简介 | Overview

**mix-agent** 是一个企业级多智能体协同驱动的代码安全审计系统。它通过 **LangGraph 编排多个 Agent**，对代码变更进行全链路安全分析，覆盖静态代码分析、SQL 安全审计、密钥扫描、合规检查等核心能力，并提供 **Human-in-the-Loop** 审批工作流。

系统以 **Tauri 桌面应用** 为入口，**FastAPI** 为后端，通过 **Tree-sitter AST** 提取业务语义（不将原始源码送入 LLM），结合 **SQLGlot 语法树** 精准检测高危 SQL 操作，有效解决传统 SAST 工具误报高、人工 Review 成本高、LLM 直接分析源码的 Token 成本爆炸等问题。

> 📌 系统设计为**三个阶段交付**：Phase 1 — 确定性扫描；Phase 2 — Agent 化协同；Phase 3 — 高级能力（RAG、动态分析等）。

---

## ✨ 核心特性 | Key Features

| 特性 | 说明 |
|------|------|
| **🧠 多 Agent 协同** | LangGraph 状态机编排：需求解析 → 代码审查 → SQL 审计 → 自动修复 → 汇总，含人工审批门控 |
| **🔍 静态代码分析** | Tree-sitter AST 解析、调用链追踪、路由扫描（FastAPI + Vue Router）、ORM 表提取、泳道图生成 |
| **🛡️ SQL 安全审计** | SQLGlot 语法树检测高危 DDL（DROP/TRUNCATE/ALTER）、无条件 DML、动态 SQL 注入 |
| **🔑 密钥扫描** | 正则 + 熵检测硬编码密钥/令牌/密码 |
| **📋 合规检查** | OWASP 规则引擎，可扩展 YAML 规则集 |
| **🔗 Git 深度集成** | 分支 Diff、提交日志、状态查询、文件补丁 — 完整的 VCS 工具链 |
| **📦 Docker 沙箱** | 隔离执行不可信代码，确保分析安全 |
| **💬 A2A 协议** | Agent-to-Agent 消息通信，标准化 Pydantic 模式 |
| **🤖 LLM 集成** | 支持 DeepSeek + MiniMax（OpenAI 兼容协议），含成本追踪 |
| **📊 向量 RAG** | Qdrant 驱动的代码摘要检索与知识沉淀 |
| **🖥️ 桌面应用** | Tauri v2 + React 19 前端，原生 git diff、文件读写/回滚、文件监听 |
| **📈 CI/CD 集成** | 内置 GitHub Actions 与 GitLab CI 模板，无缝嵌入现有流水线 |

---

## 🏗️ 系统架构 | Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Tauri Desktop App                           │
│  ┌─────────────────────┐    Tauri IPC    ┌──────────────────┐ │
│  │  React 19 + Vite    │◄──────────────►│  Rust Backend    │ │
│  │  (WebView)          │                 │  (src-tauri/)    │ │
│  │                     │                 │  • git diff      │ │
│  │  Pages:             │                 │  • File read     │ │
│  │  /login             │                 │  • File watch    │ │
│  │  /tasks/:id         │                 │  • Patch/Rollback│ │
│  │  /approvals         │                 └──────────────────┘ │
│  │  /settings/*        │─────────── HTTP ──────────────────── │
│  └─────────────────────┘                                      │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI Backend                             │
│                                                               │
│  ┌──────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │  API     │   │  Agents          │   │  Tools           │  │
│  │  /tasks  │   │  graph.py        │   │  parser/         │  │
│  │  /approve│   │  agent_nodes/    │   │  sandbox/        │  │
│  │  /auth   │   │  prompts.py      │   │  security/       │  │
│  └──────────┘   └──────────────────┘   │  vcs/            │  │
│                                          └──────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  LangGraph StateMachine                                │    │
│  │  parse_req → orchestrator → code_review/sql_audit/    │    │
│  │  auto_fix → summary → END (conditional review gate)  │    │
│  └───────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
                           │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │ PostgreSQL │  │   Redis    │  │   Qdrant   │
     │ (主存储)   │  │ (缓存/CP)  │  │ (向量库)   │
     └────────────┘  └────────────┘  └────────────┘
```

---

## 🛠️ 技术栈 | Tech Stack

| 层 | 技术 |
|--------|--------|
| **后端** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy (async), LangGraph |
| **前端** | React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, Zustand, Monaco Editor |
| **桌面壳** | Rust + Tauri v2 (git diff, file ops, file watcher via IPC) |
| **代码分析** | Tree-sitter (AST), SQLGlot (SQL 语法树) |
| **数据库** | PostgreSQL 16 (asyncpg), Redis 7, Qdrant (向量数据库) |
| **沙箱** | Docker 容器 (隔离执行) |
| **LLM** | DeepSeek, MiniMax (OpenAI 兼容) |
| **CI/CD** | GitHub Actions, GitLab CI |

---

## 🚀 快速开始 | Quick Start

### 前置条件 | Prerequisites

- Python ≥ 3.11
- Poetry
- Node.js ≥ 18
- Rust (如需运行 Tauri 桌面端)
- Docker & Docker Compose (可选，用于基础设施)

### 1. 启动基础设施 | Start Infrastructure

```bash
docker compose up -d
# 启动 PostgreSQL 16, Redis 7, Qdrant
```

### 2. 安装后端 | Install Backend

```bash
# 安装依赖
poetry install

# 激活虚拟环境
poetry shell

# 初始化数据库（Alembic 迁移）
alembic upgrade head

# 启动服务
mix-agent serve
# 或: uvicorn mix_agent.api.main:app --reload
```

### 3. 启动前端 | Start Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. 运行桌面应用 | Run Desktop App

```bash
cd frontend
npm run tauri dev
```

---

## 📟 CLI 使用 | CLI Usage

```bash
# 执行代码安全扫描
mix-agent scan --target <path> [--output <format>]

# 启动 API 服务
mix-agent serve [--host 0.0.0.0] [--port 8000]

# 查看帮助
mix-agent --help
```

---

## 📂 项目结构 | Project Structure

```
mix-agent/
├── src/
│   └── mix_agent/
│       ├── agents/            # LangGraph Agent 定义
│       │   ├── graph.py       # 状态机构图
│       │   ├── agent_nodes/   # 各 Agent 节点
│       │   └── prompts.py     # 提示词模板
│       ├── api/               # FastAPI 路由
│       ├── services/          # 业务服务层
│       │   ├── llm.py         # LLM 调用封装
│       │   ├── rag.py         # Qdrant RAG 服务
│       │   └── cost_manager.py# Token 成本追踪
│       ├── tools/             # 工具层
│       │   ├── parser/        # Tree-sitter AST 解析
│       │   ├── security/      # SQL 审计 & 密钥扫描
│       │   ├── vcs/           # Git 集成
│       │   └── sandbox/       # Docker 沙箱
│       └── compliance_rules/  # OWASP 合规规则
├── frontend/
│   ├── src/                   # React 前端源码
│   └── src-tauri/             # Tauri Rust 后端
├── docs/
│   ├── requirements.md        # 需求文档
│   ├── technical-design.md    # 技术设计文档
│   └── tasks.md               # 开发任务分解
├── docker-compose.yml         # 基础设施编排
├── pyproject.toml             # Python 项目配置
└── alembic/                   # 数据库迁移
```

---

## 🔬 核心工作流 | Core Workflow

```
用户意图 (自然语言)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ parse_requirement   — 语义解析 → 结构化分析任务          │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ orchestrator         — 智能路由到下游 Agent              │
└─────────────────────────────────────────────────────────┘
    │
    ├──► code_review      — Tree-sitter AST 静态分析      │
    ├──► sql_risk_explain — SQLGlot 语法树安全审计        │
    └──► auto_fix         — 自动生成修复方案              │
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Human-in-the-Loop 审批门控                              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ summary              — 汇总报告生成                     │
└─────────────────────────────────────────────────────────┘
```

---

## 🧪 测试 | Testing

```bash
# 运行后端测试
poetry run pytest

# 运行前端 lint
cd frontend && npm run lint
```

---

## 📄 文档 | Documentation

- [需求文档](docs/requirements.md) — 项目背景、痛点、建设目标、功能规格
- [技术设计文档](docs/technical-design.md) — 总体架构、模块设计、接口规范
- [开发任务分解](docs/tasks.md) — 分期交付计划与任务清单

---

## 🤝 贡献 | Contributing

内部项目，请遵循团队 Git 工作流规范：
1. 从 `main` 创建功能分支
2. 提交变更并编写清晰的提交信息
3. 创建 Merge Request，系统将自动触发安全审计流水线
4. 通过 Code Review 后合入

---

## 📜 许可证 | License

**Proprietary** — 版权所有 © 2026 QuintaraBio. 保留所有权利。
