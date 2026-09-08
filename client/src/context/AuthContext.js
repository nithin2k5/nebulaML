"use client";

import { createContext, useContext, useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const AuthContext = createContext({});

export const useAuth = () => useContext(AuthContext);

import { API_BASE_URL } from "@/lib/config";
import { useConfirm } from "@/components/ui/confirm-dialog";

export function AuthProvider({ children }) {
  const confirm = useConfirm();
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const promptRef = useRef(0);

  const extractError = (detail) => {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join(", ");
    return null;
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const getJwtExpSeconds = (jwt) => {
    try {
      const parts = jwt.split(".");
      if (parts.length !== 3) return null;
      const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const decoded = JSON.parse(atob(payload.padEnd(payload.length + (4 - (payload.length % 4)) % 4, "=")));
      if (!decoded || typeof decoded.exp !== "number") return null;
      return decoded.exp;
    } catch {
      return null;
    }
  };

  // Access and refresh tokens are stored together so a single place decides
  // what is persisted. The access token is now short-lived (an hour), and the
  // refresh token is rotated on every use — replaying an old one server-side
  // revokes the whole family.
  const storeTokens = (accessToken, refreshToken) => {
    if (accessToken) {
      localStorage.setItem("token", accessToken);
      setToken(accessToken);
    }
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
  };

  const clearTokens = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    setToken(null);
  };

  // Exchange the refresh token for a new pair. Returns the new access token,
  // or null when the session is genuinely over and the user must sign in.
  const refreshSession = async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return null;
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) {
        // 401 means rotated, revoked or expired — none of it recoverable here.
        if (response.status === 401) clearTokens();
        return null;
      }
      const data = await response.json();
      storeTokens(data.access_token, data.refresh_token);
      setUser(data.user || null);
      return data.access_token || null;
    } catch {
      return null;
    }
  };

  const refreshUserPermissions = async (newToken) => {
    try {
      const permResponse = await fetch(`${API_BASE_URL}/api/auth/permissions`, {
        headers: { "Authorization": `Bearer ${newToken}` }
      });
      if (permResponse.ok) {
        const permData = await permResponse.json();
        setUser((prev) => ({ ...(prev || {}), permissions: permData.permissions }));
      }
    } catch {}
  };

  const extendSession = async () => {
    if (!token) return { success: false, error: "No token" };
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/extend-session`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(extractError(err.detail) || "Failed to extend session");
      }

      const data = await response.json();
      storeTokens(data.access_token, data.refresh_token);
      setUser(data.user || null);
      if (data.access_token) await refreshUserPermissions(data.access_token);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const checkAuth = async () => {
    const defaultToken = localStorage.getItem("token");
    if (defaultToken) {
      setToken(defaultToken);
      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: {
            "Authorization": `Bearer ${defaultToken}`
          }
        });

        if (response.ok) {
          const userData = await response.json();
          setUser(userData);

          // Fetch permissions
          const permResponse = await fetch(`${API_BASE_URL}/api/auth/permissions`, {
            headers: {
              "Authorization": `Bearer ${defaultToken}`
            }
          });

          if (permResponse.ok) {
            const permData = await permResponse.json();
            setUser(prev => ({ ...prev, permissions: permData.permissions }));
          }
        } else {
          // The access token is stale. It is short-lived now, so this is the
          // normal path on any page load more than an hour after sign-in —
          // try the refresh token before bouncing the user to /login.
          const renewed = await refreshSession();
          if (!renewed) clearTokens();
        }
      } catch (error) {
        console.error("Auth check failed:", error);
        clearTokens();
      }
    } else {
      setToken(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (!token) return;
    if (loading) return;

    const thresholdSeconds = Number(process.env.NEXT_PUBLIC_SESSION_EXTEND_THRESHOLD_SECONDS || (5 * 60));
    const pollMs = 30000;
    const interval = setInterval(async () => {
      const exp = getJwtExpSeconds(token);
      if (!exp) return;
      const nowSec = Math.floor(Date.now() / 1000);
      const remaining = exp - nowSec;
      if (remaining > thresholdSeconds || remaining <= 0) return;
      if (Date.now() - promptRef.current < pollMs) return;
      promptRef.current = Date.now();

      // Access tokens now expire hourly rather than weekly, so prompting on
      // every expiry would nag. Renew silently while the refresh token is
      // still good; only fall back to the prompt when it is not.
      const renewed = await refreshSession();
      if (renewed) return;

      const ok = await confirm({
        title: "Session expiring",
        description: "Your session expires shortly. Extend it to stay signed in.",
        confirmLabel: "Extend session",
        cancelLabel: "Sign out",
        variant: "default",
      });
      if (ok) {
        await extendSession();
      } else {
        clearTokens();
        setUser(null);
        router.push("/login");
      }
    }, pollMs);

    return () => clearInterval(interval);
  }, [token, loading, router, confirm]);

  const login = async (email) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ email })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(extractError(error.detail) || "Login failed");
      }

      const data = await response.json();
      
      if (data.access_token) {
        storeTokens(data.access_token, data.refresh_token);

        // Fetch permissions
        const permResponse = await fetch(`${API_BASE_URL}/api/auth/permissions`, {
          headers: {
            "Authorization": `Bearer ${data.access_token}`
          }
        });

        if (permResponse.ok) {
          const permData = await permResponse.json();
          setUser({ ...data.user, permissions: permData.permissions });
        } else {
          setUser(data.user);
        }

        return { success: true, isFastPass: true };
      }

      return { success: true, requiresOtp: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const register = async (username, email, role = "user") => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ username, email, role })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(extractError(error.detail) || "Registration failed");
      }

      return { success: true, requiresOtp: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const verifyOtp = async (email, otp) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ email, otp })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(extractError(error.detail) || "Verification failed");
      }

      const data = await response.json();
      storeTokens(data.access_token, data.refresh_token);

      const permResponse = await fetch(`${API_BASE_URL}/api/auth/permissions`, {
        headers: {
          "Authorization": `Bearer ${data.access_token}`
        }
      });

      if (permResponse.ok) {
        const permData = await permResponse.json();
        setUser({ ...data.user, permissions: permData.permissions });
      } else {
        setUser(data.user);
      }

      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const resendOtp = async (email) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/resend-otp`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ email })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(extractError(error.detail) || "Failed to resend OTP");
      }

      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const logout = async () => {
    // Revoke the refresh token server-side; without this it stays usable for
    // its full lifetime even after the client forgets it.
    const refreshToken = localStorage.getItem("refresh_token");
    const accessToken = localStorage.getItem("token");
    if (accessToken) {
      try {
        await fetch(`${API_BASE_URL}/api/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
        });
      } catch {
        // Sign the user out locally regardless of whether the call lands.
      }
    }
    clearTokens();
    setUser(null);
    router.push("/login");
  };

  const hasPermission = (permission) => {
    if (!user || !user.permissions) return false;
    return user.permissions.includes(permission);
  };

  const isAdmin = () => {
    return user?.role === "admin";
  };

  const value = {
    user,
    token,
    loading,
    login,
    register,
    verifyOtp,
    resendOtp,
    extendSession,
    refreshSession,
    logout,
    hasPermission,
    isAdmin,
    checkAuth
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

