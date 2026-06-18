import { create } from "zustand";
import { setToken, getToken } from "../api/client";

interface AuthState {
  isLoggedIn: boolean;
  user: { username: string; role: string } | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  isLoggedIn: !!getToken(),
  user: null,

  login: async (username, password) => {
    const { login: apiLogin } = await import("../api/client");
    const data = await apiLogin(username, password);
    setToken(data.access_token);
    set({ isLoggedIn: true, user: { username, role: "auditor" } });
  },

  logout: () => {
    setToken(null);
    set({ isLoggedIn: false, user: null });
  },
}));
