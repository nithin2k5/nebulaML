"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Server, Monitor, CheckCircle, XCircle, RefreshCw, Globe, Database, Cpu, Github, Box } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";

export default function SettingsTab() {
  const { token } = useAuth();
  const [backendStatus, setBackendStatus] = useState("checking");
  const [backendInfo, setBackendInfo] = useState(null);
  const [systemStats, setSystemStats] = useState({
    frontend: "active",
    version: "2.1.0",
    uptime: "Active"
  });

  useEffect(() => {
    checkBackendStatus();
    const interval = setInterval(checkBackendStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const checkBackendStatus = async () => {
    setBackendStatus("checking");
    try {
      const response = await fetch(API_ENDPOINTS.HEALTH);
      if (response.ok) {
        const data = await response.json();
        setBackendStatus("connected");
        setBackendInfo(data);
      } else {
        setBackendStatus("error");
      }
    } catch (error) {
      setBackendStatus("disconnected");
      setBackendInfo(null);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case "connected":
        return (
          <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 px-3 py-1">
            <CheckCircle className="mr-2" /> Operational
          </Badge>
        );
      case "disconnected":
        return (
          <Badge className="bg-red-500/20 text-red-400 border-red-500/30 px-3 py-1">
            <XCircle className="mr-2" /> Offline
          </Badge>
        );
      case "checking":
        return (
          <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 px-3 py-1">
            <RefreshCw className="mr-2 animate-spin" /> Checking
          </Badge>
        );
      default: return null;
    }
  };

  return (
    <div className="space-y-8 animate-fade-in text-gray-100">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">System Status</h2>
          <p className="text-muted-foreground mt-1">Platform health and configuration overview.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Backend Status */}
        <div className="rounded-2xl bg-card/40 backdrop-blur-md border border-white/5 p-6 shadow-xl flex flex-col justify-between hover:bg-white/5 transition-colors">
          <div>
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 border border-indigo-500/20">
                  <Server className="text-2xl" />
                </div>
                <div>
                  <h3 className="font-bold text-lg">Inference Engine</h3>
                  <p className="text-sm text-muted-foreground">Python FastAPI</p>
                </div>
              </div>
              {getStatusBadge(backendStatus)}
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center p-3 rounded-lg bg-black/20 border border-white/5">
                <span className="text-sm text-gray-400">Endpoint</span>
                <code className="text-xs bg-white/10 px-2 py-1 rounded text-indigo-300">{API_ENDPOINTS.HEALTH.replace('/health', '')}</code>
              </div>
              <div className="flex justify-between items-center p-3 rounded-lg bg-black/20 border border-white/5">
                <span className="text-sm text-gray-400">Docs</span>
                <a href={`${API_ENDPOINTS.HEALTH.replace('/health', '')}/docs`} target="_blank" className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
                  Swagger UI <Globe />
                </a>
              </div>
            </div>
          </div>

          <Button
            onClick={checkBackendStatus}
            variant="outline"
            className="w-full mt-6 border-white/10 hover:bg-white/5 bg-transparent"
            disabled={backendStatus === "checking"}
          >
            <RefreshCw className={`mr-2 ${backendStatus === "checking" ? "animate-spin" : ""}`} />
            Verify Connection
          </Button>
        </div>

        {/* Frontend Status */}
        <div className="rounded-2xl bg-card/40 backdrop-blur-md border border-white/5 p-6 shadow-xl flex flex-col justify-between hover:bg-white/5 transition-colors">
          <div>
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-400 border border-purple-500/20">
                  <Monitor className="text-2xl" />
                </div>
                <div>
                  <h3 className="font-bold text-lg">Dashboard UI</h3>
                  <p className="text-sm text-muted-foreground">Next.js 15.1</p>
                </div>
              </div>
              <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 px-3 py-1">
                <CheckCircle className="mr-2" /> Active
              </Badge>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center p-3 rounded-lg bg-black/20 border border-white/5">
                <span className="text-sm text-gray-400">Version</span>
                <span className="text-sm font-mono text-white">v{systemStats.version}</span>
              </div>
              <div className="flex justify-between items-center p-3 rounded-lg bg-black/20 border border-white/5">
                <span className="text-sm text-gray-400">Framework</span>
                <span className="text-sm text-white">React Server Components</span>
              </div>
            </div>
          </div>

          <div className="mt-6 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
            <p className="text-sm text-emerald-400 font-medium">All systems normal</p>
          </div>
        </div>

        {/* Services Status */}
        <div className="lg:col-span-2 rounded-2xl bg-card/40 backdrop-blur-md border border-white/5 p-6">
          <h3 className="font-bold text-lg mb-6">Service Health</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { name: "Inference API", icon: Cpu },
              { name: "Training", icon: Database },
              { name: "Registry", icon: Box },
              { name: "Annotations", icon: Globe },
              { name: "Storage", icon: Server },
            ].map((svc, i) => (
              <div key={i} className="flex flex-col items-center justify-center p-4 rounded-xl bg-white/5 border border-white/5 hover:border-indigo-500/30 transition-colors">
                <svc.icon className={`text-xl mb-2 ${backendStatus === "connected" ? "text-emerald-400" : "text-red-400"}`} />
                <span className="text-sm font-medium text-gray-300">{svc.name}</span>
                <span className={`text-xs mt-1 ${backendStatus === "connected" ? "text-emerald-500/70" : "text-red-500/70"}`}>
                  {backendStatus === "connected" ? "Operational" : "Degraded"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex justify-center pt-8">
        <p className="text-xs text-gray-600 flex items-center gap-2">
          <Github />
          Powered by YOLOv8 and Shadcn UI. Internal Build {systemStats.version}.
        </p>
      </div>
    </div>
  );
}
