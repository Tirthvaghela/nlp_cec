import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, setUnauthorizedHandler, tokenStore } from "@/lib/api";
import type { Role, TokenResponse, User } from "@/lib/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (data: { name: string; email: string; password: string; role: Role; invite_code?: string }) => Promise<User>;
  logout: () => void;
  setUser: (u: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => Boolean(tokenStore.get()));
  const queryClient = useQueryClient();

  const logout = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    if (!tokenStore.get()) return;
    let cancelled = false;
    api
      .get<User>("/api/auth/me")
      .then((u) => !cancelled && setUser(u))
      .catch(() => !cancelled && tokenStore.set(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const accept = useCallback(
    (res: TokenResponse) => {
      queryClient.clear();
      tokenStore.set(res.access_token);
      setUser(res.user);
      return res.user;
    },
    [queryClient],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login: async (email, password) => accept(await api.post<TokenResponse>("/api/auth/login", { email, password })),
      register: async (data) => accept(await api.post<TokenResponse>("/api/auth/register", data)),
      logout,
      setUser,
    }),
    [user, loading, accept, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export function homeFor(role: Role) {
  return role === "teacher" ? "/teacher" : "/student";
}
