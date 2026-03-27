"use client";

import { createContext, useContext, useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const AuthContext = createContext({});

export const useAuth = () => useContext(AuthContext);

import { API_BASE_URL } from "@/lib/config";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const promptRef = useRef(0);

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
        throw new Error(err.detail || "Failed to extend session");
      }

      const data = await response.json();
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
        setToken(data.access_token);
      }
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
          localStorage.removeItem("token");
        }
      } catch (error) {
        console.error("Auth check failed:", error);
        localStorage.removeItem("token");
        setToken(null);
      }
    } else {
      setToken(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (!token) return;
    if (loading) return;

    const thresholdSeconds = Number(process.env.NEXT_PUBLIC_SESSION_EXTEND_THRESHOLD_SECONDS || (10 * 60));
    const pollMs = 30000;
    const interval = setInterval(async () => {
      const exp = getJwtExpSeconds(token);
      if (!exp) return;
      const nowSec = Math.floor(Date.now() / 1000);
      const remaining = exp - nowSec;
      if (remaining <= thresholdSeconds && remaining > 0) {
        if (Date.now() - promptRef.current < pollMs) return;
        promptRef.current = Date.now();
        const ok = window.confirm("Your session is about to expire. Extend session?");
        if (ok) {
          await extendSession();
        } else {
          localStorage.removeItem("token");
          setToken(null);
          setUser(null);
          router.push("/login");
        }
      }
    }, pollMs);

    return () => clearInterval(interval);
  }, [token, loading, router]);

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
        throw new Error(error.detail || "Login failed");
      }

      const data = await response.json();
      
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
        setToken(data.access_token);

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
        throw new Error(error.detail || "Registration failed");
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
        throw new Error(error.detail || "Verification failed");
      }

      const data = await response.json();
      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);

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
        throw new Error(error.detail || "Failed to resend OTP");
      }

      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
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

