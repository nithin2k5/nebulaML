"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";

export default function SplashScreen() {
  const router = useRouter();
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // Check if we've seen the splash screen in this session
    const hasSeenSplash = sessionStorage.getItem("hasSeenSplash");

    if (hasSeenSplash) {
      router.replace("/home");
      return;
    }

    sessionStorage.setItem("hasSeenSplash", "true");

    // Fast loading progress
    const timer = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(timer);
          return 100;
        }
        return prev + 15; // Faster progress
      });
    }, 50);

    // Redirect after just 800ms
    const redirectTimer = setTimeout(() => {
      router.push("/home");
    }, 800);

    return () => {
      clearInterval(timer);
      clearTimeout(redirectTimer);
    };
  }, [router]);

  return (
    <div className="fixed inset-0 bg-black flex flex-col items-center justify-center z-50 overflow-hidden">
      {/* Background Ambience */}
      <div className="absolute inset-0 z-0">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[100px] animate-pulse-glow" />
      </div>

      <div className="relative z-10 flex flex-col items-center">
        {/* Logo Animation */}
        <div className="relative mb-8">
          <div className="absolute inset-0 bg-indigo-500 blur-2xl opacity-20 animate-pulse" />
          <div className="w-24 h-24 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-3xl flex items-center justify-center shadow-2xl shadow-indigo-500/30 animate-float">
            <Zap className="text-5xl text-white drop-shadow-md" />
          </div>
        </div>

        {/* Text */}
        <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">
          Nebula<span className="text-indigo-500">ML</span>
        </h1>
        <p className="text-gray-500 text-sm mb-8 animate-pulse">Initializing Environment...</p>

        {/* Loading Bar */}
        <div className="w-64 h-1.5 bg-zinc-900 rounded-full overflow-hidden border border-white/5 relative">
          <div
            className="absolute top-0 left-0 h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-300 ease-out shadow-[0_0_10px_rgba(99,102,241,0.5)]"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>

        {/* Progress Percentage */}
        <div className="mt-2 font-mono text-xs text-indigo-400">
          {Math.min(Math.floor(progress), 100)}%
        </div>
      </div>
    </div>
  );
}
