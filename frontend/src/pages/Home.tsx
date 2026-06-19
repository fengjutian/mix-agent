export default function HomePage() {
  return (
    <div style={{ maxWidth: 640, margin: "0 auto", padding: "60px 20px" }}>
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <h1 style={{ fontSize: "2rem", fontWeight: 700, margin: "0 0 8px" }}>
          mix-agent
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "1rem", margin: 0 }}>
          智能代码审计平台
        </p>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginTop: 0 }}>🔍 代码审查</h3>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6 }}>
          浏览 commit 历史、查看 diff、逐行 blame，辅助人工代码审查。
        </p>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginTop: 0 }}>🤖 AI 审计</h3>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6 }}>
          自然语言描述需求，AI 自动分析代码变更，输出安全/质量发现。
        </p>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginTop: 0 }}>🔗 接口追踪</h3>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6 }}>
          分析 API 调用链、数据表关系，生成泳道图。
        </p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>🔧 管理</h3>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6 }}>
          配置模型、Prompt、MCP 服务器、API Key，调整全局设置。
        </p>
      </div>

      <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.8rem", marginTop: 32 }}>
        从左侧活动栏选择功能开始 →
      </p>
    </div>
  );
}
