import { useAuthStore } from "../stores/auth";

export default function StatusBar() {
  const isUnlocked = useAuthStore((s) => s.isUnlocked);
  const hasPassword = useAuthStore((s) => s.hasPassword);

  const statusLabel = hasPassword
    ? (isUnlocked ? "已解锁" : "已锁定")
    : "无锁屏密码";

  return (
    <footer className="status-bar">
      {/* ── Left items ── */}
      <div className="status-bar__left">
        <span className="status-bar__item" title={statusLabel}>
          <span
            className={`status-dot status-dot--${isUnlocked || !hasPassword ? "success" : "warning"}`}
            style={{ width: 7, height: 7, marginRight: 6 }}
          />
          {statusLabel}
        </span>
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
