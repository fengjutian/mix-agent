import { create } from "zustand";

const STORAGE_KEY = "mix_agent_lock_password";

function hashPassword(pw: string): string {
  // Simple hash for local lock screen — not crypto-grade but enough for a dev tool
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
  /** Set the lock-screen password. Only works when no password is set. */
  setPassword: (password: string) => boolean;
  /** Change the lock-screen password (requires current password). */
  changePassword: (current: string, next: string) => boolean;
  /** Remove the password (requires current password). */
  removePassword: (current: string) => boolean;
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
      if (!password || get().hasPassword) return false;
      setStoredHash(hashPassword(password));
      set({ hasPassword: true });
      return true;
    },

    changePassword: (current: string, next: string) => {
      if (!next) return false;
      const stored = getStoredHash();
      if (!stored || hashPassword(current) !== stored) return false;
      setStoredHash(hashPassword(next));
      return true;
    },

    removePassword: (current: string) => {
      const stored = getStoredHash();
      if (!stored || hashPassword(current) !== stored) return false;
      clearStoredHash();
      set({ hasPassword: false, isUnlocked: true });
      return true;
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
