"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import DashboardStats from "@/components/DashboardStats";
import DatasetsTab from "@/components/DatasetsTab";
import InferenceTab from "@/components/InferenceTab";
import TrainingTab from "@/components/TrainingTab";
import ModelsTab from "@/components/ModelsTab";
import SettingsTab from "@/components/SettingsTab";
import OnboardingTour from "@/components/OnboardingTour";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Activity, Database, Zap, Cpu, Box,
  Settings, LogOut, Menu, X, ChevronLeft, ChevronRight
} from "lucide-react";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState("datasets");
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const router = useRouter();

  const tabs = [
    { id: "dashboard", label: "Overview", icon: Activity },
    { id: "datasets", label: "Projects", icon: Database },
    { id: "inference", label: "Playground", icon: Zap },
    { id: "training", label: "Training", icon: Cpu },
    { id: "models", label: "Models", icon: Box },
    { id: "settings", label: "Settings", icon: Settings },
  ];

  return (
    <ProtectedRoute>
      <OnboardingTour />
      <div className="h-screen overflow-hidden bg-background text-foreground flex">
        {/* Mobile sidebar overlay */}
        {mobileSidebarOpen && (
          <div className="fixed inset-0 bg-black/60 z-40 lg:hidden" onClick={() => setMobileSidebarOpen(false)} />
        )}

        {/* Sidebar */}
        <aside className={cn(
          "fixed lg:relative z-50 flex flex-col border-r border-white/5 bg-zinc-950 transition-all duration-300",
          sidebarOpen ? "w-56" : "w-16",
          mobileSidebarOpen ? "left-0" : "-left-full lg:left-0",
          "h-screen"
        )}>
          {/* Logo */}
          <div className="h-16 flex items-center justify-between px-4 border-b border-white/5 shrink-0">
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shrink-0 shadow-lg shadow-indigo-500/20">
                <Zap className="text-white text-sm" />
              </div>
              {sidebarOpen && <span className="font-bold text-sm whitespace-nowrap">Nebula</span>}
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="hidden lg:flex h-7 w-7 text-gray-500 hover:text-white shrink-0"
            >
              {sidebarOpen ? <ChevronLeft className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            </Button>
          </div>

          {/* Nav */}
          <nav className="flex-1 py-4 px-2.5 space-y-1 overflow-y-auto custom-scrollbar">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  id={`tour-${tab.id}`}
                  onClick={() => { setActiveTab(tab.id); setMobileSidebarOpen(false); }}
                  className={cn(
                    "w-full flex items-center gap-3 rounded-xl transition-all duration-200 text-sm font-medium",
                    sidebarOpen ? "px-3 py-2.5" : "px-0 py-2.5 justify-center",
                    isActive
                      ? "bg-indigo-500/10 text-white"
                      : "text-gray-500 hover:text-gray-200 hover:bg-white/5"
                  )}
                  title={!sidebarOpen ? tab.label : undefined}
                >
                  <Icon className={cn(
                    "shrink-0 transition-colors",
                    sidebarOpen ? "text-lg" : "text-xl",
                    isActive ? "text-indigo-400" : ""
                  )} />
                  {sidebarOpen && <span>{tab.label}</span>}
                </button>
              );
            })}
          </nav>

          {/* User */}
          <div className="border-t border-white/5 p-3 shrink-0">
            {sidebarOpen ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white text-xs font-bold shrink-0">
                    {user?.username?.charAt(0)?.toUpperCase() || "U"}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{user?.username || "User"}</p>
                    <p className="text-[10px] text-muted-foreground truncate">{user?.role || "user"}</p>
                  </div>
                </div>
                <Button
                  onClick={logout}
                  variant="ghost"
                  size="icon"
                  className="text-gray-500 hover:text-red-400 h-7 w-7 shrink-0"
                  title="Logout"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </Button>
              </div>
            ) : (
              <Button
                onClick={logout}
                variant="ghost"
                size="icon"
                className="w-full text-gray-500 hover:text-red-400"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </Button>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Header */}
          <header className="h-16 flex items-center justify-between px-6 border-b border-white/5 bg-background/80 backdrop-blur-xl z-20 shrink-0">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setMobileSidebarOpen(true)}
                className="lg:hidden h-8 w-8"
              >
                <Menu />
              </Button>
              <h2 className="text-lg font-bold">
                {tabs.find(t => t.id === activeTab)?.label || "Dashboard"}
              </h2>
            </div>
          </header>

          {/* Content */}
          <main className="flex-1 overflow-y-auto px-4 pb-4 md:px-6 custom-scrollbar">
            <div className="h-full rounded-2xl border border-white/5 bg-card/20 backdrop-blur-sm p-6 md:p-8">
              <div className="max-w-7xl mx-auto animate-fade-in space-y-8">
                {activeTab === "dashboard" && <DashboardStats onNavigate={setActiveTab} />}
                {activeTab === "datasets" && <DatasetsTab />}
                {activeTab === "inference" && <InferenceTab />}
                {activeTab === "training" && <TrainingTab />}
                {activeTab === "models" && <ModelsTab />}
                {activeTab === "settings" && <SettingsTab />}
              </div>
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
