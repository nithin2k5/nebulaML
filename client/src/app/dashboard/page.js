"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import DashboardStats from "@/components/DashboardStats";
import DatasetsTab from "@/components/DatasetsTab";
import TrainingTab from "@/components/TrainingTab";
import TestTab from "@/components/TestTab";
import ModelsTab from "@/components/ModelsTab";
import SettingsTab from "@/components/SettingsTab";
import ProfileTab from "@/components/ProfileTab";
import ChatbotTab from "@/components/ChatbotTab";
import HelpContactTab from "@/components/HelpContactTab";
import OnboardingTour from "@/components/OnboardingTour";
import { cn } from "@/lib/utils";
import {
  Activity, Database, Zap, Cpu, Box,
  Settings, LogOut, Menu, X, ChevronLeft, ChevronRight, UserCircle, MessageSquare, LifeBuoy
} from "lucide-react";

function GridBackground() {
  return (
    <div className="fixed inset-0 z-0 pointer-events-none opacity-20">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#a78bfa15_1px,transparent_1px),linear-gradient(to_bottom,#a78bfa15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
    </div>
  );
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState("datasets");
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [time, setTime] = useState("");
  const router = useRouter();

  useEffect(() => {
    const updateTime = () => setTime(new Date().toISOString().split('T')[1].slice(0, 12));
    updateTime();
    const interval = setInterval(updateTime, 100);
    return () => clearInterval(interval);
  }, []);

  const tabs = [
    { id: "dashboard", label: "OVERVIEW", icon: Activity },
    { id: "datasets", label: "PROJECTS", icon: Database },
    { id: "training", label: "TRAINING", icon: Cpu },
    { id: "chat", label: "ASSISTANT", icon: MessageSquare },
    { id: "test", label: "TEST", icon: Zap },
    { id: "models", label: "MODELS", icon: Box },
    { id: "settings", label: "SETTINGS", icon: Settings },
    { id: "profile", label: "PROFILE", icon: UserCircle },
    { id: "help", label: "HELP_CONTACT", icon: LifeBuoy },
  ];

  return (
    <ProtectedRoute>
      <OnboardingTour />
      <div className="h-screen overflow-hidden bg-black text-white flex font-sans cursor-crosshair">
        <GridBackground />

        {/* Mobile sidebar overlay */}
        {mobileSidebarOpen && (
          <div className="fixed inset-0 bg-black/80 z-40 lg:hidden" onClick={() => setMobileSidebarOpen(false)} />
        )}

        {/* Sidebar */}
        <aside className={cn(
          "fixed lg:relative z-50 flex flex-col border-r border-white/20 bg-black/80 backdrop-blur-md transition-all duration-300",
          sidebarOpen ? "w-64" : "w-16",
          mobileSidebarOpen ? "left-0" : "-left-full lg:left-0",
          "h-screen"
        )}>
          {/* Logo */}
          <div className="h-12 flex items-center justify-between px-4 border-b border-white/20 shrink-0">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-2 h-2 bg-violet-500 rounded-none shrink-0" />
              {sidebarOpen && <span className="font-mono text-sm font-bold tracking-widest uppercase text-violet-400">NBLA_ML</span>}
            </div>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="hidden lg:flex h-6 w-6 text-gray-500 hover:text-white shrink-0 items-center justify-center border border-white/20 transition-colors"
            >
              {sidebarOpen ? <ChevronLeft className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </button>
          </div>

          {/* Nav */}
          <nav className="flex-1 py-4 px-3 space-y-2 overflow-y-auto custom-scrollbar">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  id={`tour-${tab.id}`}
                  onClick={() => { setActiveTab(tab.id); setMobileSidebarOpen(false); }}
                  className={cn(
                    "w-full flex items-center gap-3 transition-colors duration-200 text-xs font-mono border border-transparent",
                    sidebarOpen ? "px-3 py-3" : "px-0 py-3 justify-center",
                    isActive
                      ? "bg-violet-500/10 text-violet-400 border-violet-500/30 shadow-[inset_2px_0_0_0_#8b5cf6]"
                      : "text-gray-500 hover:text-white hover:border-white/10"
                  )}
                  title={!sidebarOpen ? tab.label : undefined}
                >
                  <Icon className={cn(
                    "shrink-0 transition-colors",
                    sidebarOpen ? "w-4 h-4" : "w-5 h-5",
                    isActive ? "text-violet-400" : ""
                  )} />
                  {sidebarOpen && <span>[{tab.label}]</span>}
                </button>
              );
            })}
          </nav>

          {/* User */}
          <div className="border-t border-white/20 p-4 shrink-0 bg-black/40">
            {sidebarOpen ? (
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setActiveTab("profile")}
                  className="flex items-center gap-3 min-w-0 group"
                  title="View profile"
                >
                  <div className="w-8 h-8 bg-violet-500/20 border border-violet-500/50 flex items-center justify-center text-violet-400 text-xs font-mono font-bold shrink-0 transition-colors group-hover:bg-violet-500 group-hover:text-black">
                    {user?.username?.charAt(0)?.toUpperCase() || "U"}
                  </div>
                  <div className="min-w-0 text-left">
                    <p className="text-xs font-mono text-white truncate">{user?.username || "SYS_ADMIN"}</p>
                    <p className="text-[10px] font-mono text-gray-500 truncate uppercase">{user?.role || "SUPERUSER"}</p>
                  </div>
                </button>
                <button
                  onClick={logout}
                  className="text-gray-500 hover:text-red-400 h-8 w-8 shrink-0 flex items-center justify-center border border-transparent hover:border-red-400/30 transition-colors"
                  title="Logout"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={logout}
                className="w-full text-gray-500 hover:text-red-400 flex items-center justify-center py-2 border border-transparent hover:border-red-400/30 transition-colors"
                title="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-10">
          {/* Header */}
          <header className="h-12 flex items-center justify-between px-6 border-b border-white/20 bg-black/80 backdrop-blur-md shrink-0">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setMobileSidebarOpen(true)}
                className="lg:hidden h-8 w-8 text-gray-400 border border-white/20 flex items-center justify-center"
              >
                <Menu className="w-4 h-4" />
              </button>
              <h2 className="text-sm font-bold uppercase tracking-widest text-white">
                MODULE // {tabs.find(t => t.id === activeTab)?.label || "DASHBOARD"}
              </h2>
            </div>
            
            <div className="hidden md:flex items-center gap-6">
               <span className="font-mono text-xs text-gray-500">T_SYS: {time}</span>
               <div className="flex items-center gap-2">
                 <div className="w-1.5 h-1.5 bg-emerald-500 rounded-none animate-pulse" />
                 <span className="font-mono text-[10px] text-emerald-500">SYS_OK</span>
               </div>
            </div>
          </header>

          {/* Content */}
          <main className="flex-1 overflow-y-auto custom-scrollbar relative">
            <div className="h-full">
              <div className="max-w-7xl mx-auto space-y-8 p-6 md:p-8 relative z-10">
                {activeTab === "dashboard" && <DashboardStats onNavigate={setActiveTab} />}
                {activeTab === "datasets" && <DatasetsTab />}
                {activeTab === "training" && <TrainingTab />}
                {activeTab === "chat" && <ChatbotTab />}
                {activeTab === "test" && <TestTab />}
                {activeTab === "models" && <ModelsTab />}
                {activeTab === "settings" && <SettingsTab />}
                {activeTab === "profile" && <ProfileTab />}
                {activeTab === "help" && <HelpContactTab onNavigate={setActiveTab} />}
              </div>
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
