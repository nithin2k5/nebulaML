"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { useState, useEffect } from "react";
import { Home } from "lucide-react";
import Link from "next/link";
import { Toaster } from 'sonner';
import { cn } from "@/lib/utils";
import { navGroups } from "@/lib/pipeline";

function GridBackground() {
  return (
    <div className="fixed inset-0 z-0 pointer-events-none opacity-20">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#a78bfa15_1px,transparent_1px),linear-gradient(to_bottom,#a78bfa15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
    </div>
  );
}

export default function ProjectLayout({ children }) {
    const { user, loading, hasPermission } = useAuth();
    const router = useRouter();
    const params = useParams();
    const searchParams = useSearchParams();
    const currentTab = searchParams.get('tab');

    useEffect(() => {
        if (!loading) {
            if (!user) {
                router.push("/login");
            } else if (!hasPermission("view_dataset")) {
                router.push("/unauthorized");
            }
        }
    }, [user, loading, router, hasPermission]);

    if (loading) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center font-mono text-violet-500 uppercase text-xs">
                [ SYS_INIT... ]
            </div>
        );
    }

    if (!user || !hasPermission("view_dataset")) return null;

    return (
        <div className="min-h-screen bg-black text-white flex cursor-crosshair font-sans">
            <GridBackground />

            {/* Sidebar */}
            <aside className="w-16 md:w-64 border-r border-white/20 bg-black/80 backdrop-blur-md flex flex-col fixed inset-y-0 z-50">
                <div className="h-12 flex items-center justify-center md:justify-start px-4 border-b border-white/20 shrink-0">
                    <div className="flex items-center gap-3 font-bold text-sm text-violet-400">
                        <div className="w-2 h-2 bg-violet-500 shrink-0" />
                        <span className="hidden md:inline font-mono tracking-widest uppercase">NBLA_ML</span>
                    </div>
                </div>

                <nav className="flex-1 py-4 px-2 md:px-3 space-y-2 overflow-y-auto">
                    <SidebarItem icon={Home} label="DASHBOARD" href="/dashboard" />

                    {params.id && navGroups().map(({ phase, steps }, i) => (
                        <div key={phase.id} className="space-y-1">
                            <div className="pt-4 pb-2 px-2 hidden md:block text-[10px] font-mono text-gray-500 uppercase tracking-widest">
                                {phase.ambient ? phase.label : `${i + 1} // ${phase.label}`}
                            </div>
                            {steps.map((step) => (
                                <SidebarItem
                                    key={step.id}
                                    icon={step.icon}
                                    label={step.label}
                                    href={`/project/${params.id}?tab=${step.id}`}
                                    active={
                                        currentTab === step.id ||
                                        (step.id === "overview" && !currentTab)
                                    }
                                />
                            ))}
                        </div>
                    ))}
                </nav>

                <div className="p-4 border-t border-white/20 bg-black/40">
                    <div className="flex items-center gap-3 group cursor-pointer">
                        <div className="w-8 h-8 bg-violet-500/20 border border-violet-500/50 flex items-center justify-center text-violet-400 text-xs font-mono font-bold shrink-0 transition-colors group-hover:bg-violet-500 group-hover:text-black">
                            {user.username?.[0]?.toUpperCase()}
                        </div>
                        <div className="hidden md:block overflow-hidden">
                            <p className="text-xs font-mono text-white truncate uppercase">{user.username}</p>
                            <p className="text-[10px] font-mono text-gray-500 truncate uppercase">LICENSE: FREE</p>
                        </div>
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 pl-16 md:pl-64 relative z-10">
                {children}
            </main>
            <Toaster />
        </div>
    );
}

function SidebarItem({ icon: Icon, label, href, active }) {
    return (
        <Link
            href={href}
            className={cn(
                // py-2 rather than py-3: the nav now carries all twelve steps
                // plus phase headings, and has to fit without scrolling.
                "flex items-center gap-3 px-3 py-2 transition-colors duration-200 text-xs font-mono border border-transparent",
                active
                    ? "bg-violet-500/10 text-violet-400 border-violet-500/30 shadow-[inset_2px_0_0_0_#8b5cf6]"
                    : "text-gray-500 hover:text-white hover:border-white/10"
            )}
        >
            <Icon className={cn("shrink-0", active ? "w-4 h-4 text-violet-400" : "w-4 h-4")} />
            <span className="hidden md:inline">[{label}]</span>
        </Link>
    )
}
