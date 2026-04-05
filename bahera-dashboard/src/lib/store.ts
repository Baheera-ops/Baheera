// src/lib/store.ts — Global auth state with Zustand

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api, User } from "./api";

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName: string, agencyName: string) => Promise<void>;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,

      login: async (email, password) => {
        const res = await api.login({ email, password });
        api.setToken(res.access_token);
        set({ token: res.access_token, user: res.user, isAuthenticated: true });
      },

      signup: async (email, password, fullName, agencyName) => {
        const res = await api.signup({ email, password, full_name: fullName, agency_name: agencyName });
        api.setToken(res.access_token);
        set({ token: res.access_token, user: res.user, isAuthenticated: true });
      },

      logout: () => {
        api.setToken(null);
        set({ token: null, user: null, isAuthenticated: false });
      },

      hydrate: () => {
        const { token } = get();
        if (token) api.setToken(token);
      },
    }),
    { name: "bahera-auth" }
  )
);
