"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authApi, type User } from "@/lib/api";

const ACCESS_TOKEN_KEY = "agentlens_access_token";
const REFRESH_TOKEN_KEY = "agentlens_refresh_token";

type AuthContextValue = {
  user: User | null;
  accessToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  updateProfile: (data: { full_name?: string }) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function storeTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function getStoredTokens() {
  if (typeof window === "undefined") return { access: null, refresh: null };
  return {
    access: localStorage.getItem(ACCESS_TOKEN_KEY),
    refresh: localStorage.getItem(REFRESH_TOKEN_KEY),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadProfile = useCallback(async (token: string, refresh: string | null) => {
    try {
      const profile = await authApi.getProfile(token);
      setUser(profile);
      setAccessToken(token);
      return true;
    } catch {
      if (refresh) {
        try {
          const tokens = await authApi.refresh(refresh);
          storeTokens(tokens.access_token, tokens.refresh_token);
          const profile = await authApi.getProfile(tokens.access_token);
          setUser(profile);
          setAccessToken(tokens.access_token);
          return true;
        } catch {
          clearTokens();
          setUser(null);
          setAccessToken(null);
        }
      }
      return false;
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      const { access, refresh } = getStoredTokens();
      if (access) {
        await loadProfile(access, refresh);
      }
      setIsLoading(false);
    };
    void init();
  }, [loadProfile]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login({ email, password });
    storeTokens(tokens.access_token, tokens.refresh_token);
    const profile = await authApi.getProfile(tokens.access_token);
    setAccessToken(tokens.access_token);
    setUser(profile);
  }, []);

  const signup = useCallback(async (email: string, password: string, fullName?: string) => {
    await authApi.signup({ email, password, full_name: fullName });
    await login(email, password);
  }, [login]);

  const logout = useCallback(async () => {
    const { access, refresh } = getStoredTokens();
    if (access && refresh) {
      try {
        await authApi.logout(refresh, access);
      } catch {
        // ignore logout API errors
      }
    }
    clearTokens();
    setUser(null);
    setAccessToken(null);
  }, []);

  const refreshProfile = useCallback(async () => {
    const { access, refresh } = getStoredTokens();
    if (access) {
      await loadProfile(access, refresh);
    }
  }, [loadProfile]);

  const updateProfile = useCallback(
    async (data: { full_name?: string }) => {
      if (!accessToken) throw new Error("Not authenticated");
      const updated = await authApi.updateProfile(data, accessToken);
      setUser(updated);
    },
    [accessToken],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      isLoading,
      isAuthenticated: Boolean(user && accessToken),
      login,
      signup,
      logout,
      refreshProfile,
      updateProfile,
    }),
    [user, accessToken, isLoading, login, signup, logout, refreshProfile, updateProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
