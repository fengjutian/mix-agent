import { useAuthStore } from "../stores/auth";

export default function StatusBar() {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  const user = useAuthStore((s) => s.user);

  return (
    <footer className="status-bar">
      {/* ── Left items ── */}
      <div className="status-bar__left">
        <span className="status-bar__item" title={isLoggedIn ? "后端已连接" : "未登录"}>
          <span
            className={`status-dot status-dot--${isLoggedIn ? "success" : "warning"}`}
            style={{ width: 7, height: 7, marginRight: 6 }}
          />
          {isLoggedIn ? "已连接" : "未登录"}
        </span>

        {user && (
          <span className="status-bar__item" title="当前用户">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4 }}>
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            {user.username}
          </span>
        )}
      </div>

      {/* ── Right items ── */}
      <div className="status-bar__right">
        <span className="status-bar__item" title="mix-agent 版本">
          mix-agent v0.1.0
        </span>
      </div>
    </footer>
  );
}
