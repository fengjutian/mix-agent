import { create } from "zustand";

const STORAGE_KEY = "mix_agent_lock_password";

/**
 * Local lock-screen password hash.
 *
 * IMPORTANT: This is NOT a cryptographic hash — it uses Java-style
 * `String.hashCode()` + base-36. It is deliberately simple because:
 *  - This is a dev-tool lock screen, not an auth system.
 *  - The hash is stored in localStorage (plain text), visible to anyone
 *    with browser DevTools.
 *  - Its purpose is to prevent casual/mistaken access by a colleague
 *    walking past your desk, NOT to resist a targeted attack.
 *
 * If real authentication is ever needed, use the server-side JWT flow
 * or a proper PBKDF2/bcrypt implementation.
 */
function hashPassword(pw: string): string {
  let hash = 0;
  for (let i = 0; i < pw.length; i++) {
    const ch = pw.charCodeAt(i);
    hash = ((hash << 5) - hash + ch) | 0;
  }
  return "mxa_" + hash.toString(36);
}

function getStoredHash(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

function setStoredHash(h: string) {
  localStorage.setItem(STORAGE_KEY, h);
}

function clearStoredHash() {
  localStorage.removeItem(STORAGE_KEY);
}

interface AuthState {
  isUnlocked: boolean;
  hasPassword: boolean;
  /** Set the lock-screen password. Only works when no password is set.
   *  Returns { ok: false, error: "..." } on failure. */
  setPassword: (password: string) => { ok: boolean; error?: string };
  /** Change the lock-screen password (requires current password). */
  changePassword: (current: string, next: string) => { ok: boolean; error?: string };
  /** Remove the password (requires current password). */
  removePassword: (current: string) => { ok: boolean; error?: string };
  /** Unlock the screen with the password. */
  unlock: (password: string) => boolean;
  /** Lock the screen (only if a password has been set). */
  lock: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => {
  const stored = getStoredHash();

  return {
    isUnlocked: true, // always start unlocked
    hasPassword: stored !== null,

    setPassword: (password: string) => {
      if (!password) return { ok: false, error: "密码不能为空" };
      if (get().hasPassword) return { ok: false, error: "密码已存在，请使用「修改密码」" };
      setStoredHash(hashPassword(password));
      set({ hasPassword: true });
      return { ok: true };
    },

    changePassword: (current: string, next: string) => {
      if (!next) return { ok: false, error: "新密码不能为空" };
      const stored = getStoredHash();
      if (!stored) return { ok: false, error: "尚未设置密码" };
      if (hashPassword(current) !== stored) return { ok: false, error: "当前密码错误" };
      setStoredHash(hashPassword(next));
      return { ok: true };
    },

    removePassword: (current: string) => {
      const stored = getStoredHash();
      if (!stored) return { ok: false, error: "尚未设置密码" };
      if (hashPassword(current) !== stored) return { ok: false, error: "密码错误" };
      clearStoredHash();
      set({ hasPassword: false, isUnlocked: true });
      return { ok: true };
    },

    unlock: (password: string) => {
      const stored = getStoredHash();
      if (!stored) return true; // no password set — always succeed
      if (hashPassword(password) === stored) {
        set({ isUnlocked: true });
        return true;
      }
      return false;
    },

    lock: () => {
      if (!get().hasPassword) return;
      set({ isUnlocked: false });
    },
  };
});
