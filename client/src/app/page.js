"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Square } from "lucide-react";

export default function SplashScreen() {
  const router = useRouter();
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const hasSeenSplash = sessionStorage.getItem("hasSeenSplash");

    if (hasSeenSplash) {
      router.replace("/home");
      return;
    }

    sessionStorage.setItem("hasSeenSplash", "true");

    const timer = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(timer);
          return 100;
        }
        return prev + 15; 
      });
    }, 50);

    const redirectTimer = setTimeout(() => {
      router.push("/home");
    }, 800);

    return () => {
      clearInterval(timer);
      clearTimeout(redirectTimer);
    };
  }, [router]);

  return (
    <div className="fixed inset-0 bg-black flex flex-col items-center justify-center z-50 overflow-hidden cursor-crosshair">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#a78bfa15_1px,transparent_1px),linear-gradient(to_bottom,#a78bfa15_1px,transparent_1px)] bg-[size:4rem_4rem] pointer-events-none opacity-20" />

      <div className="relative z-10 w-full max-w-sm px-6">
        <div className="border border-violet-500/40 bg-black/80 backdrop-blur-sm p-8 relative">
          <div className="absolute -top-[1px] -left-[1px] bg-violet-500 text-black text-xs font-mono font-bold px-2 py-0.5 flex items-center gap-2">
            <span>SYS_INIT</span>
            <span className="opacity-70">1.00</span>
          </div>
          
          <div className="absolute -top-1 -left-1 w-2 h-2 border-t border-l border-violet-400" />
          <div className="absolute -top-1 -right-1 w-2 h-2 border-t border-r border-violet-400" />
          <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b border-l border-violet-400" />
          <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b border-r border-violet-400" />

          <div className="flex flex-col mb-8">
            <h1 className="text-2xl font-bold uppercase tracking-tight text-white flex items-center gap-2">
              <Square className="w-4 h-4 fill-violet-500 text-violet-500" />
              NBLA_ML
            </h1>
            <p className="text-gray-500 text-xs font-mono mt-2">Loading core modules...</p>
          </div>

          <div className="space-y-2">
            <div className="w-full h-1 bg-white/10 relative">
              <div
                className="absolute top-0 left-0 h-full bg-violet-500 transition-all duration-75 ease-linear"
                style={{ width: `${Math.min(progress, 100)}%` }}
              />
            </div>
            <div className="flex justify-between items-center text-[10px] font-mono text-violet-400">
              <span>{Math.min(Math.floor(progress), 100)}%</span>
              <span>[====&gt;.........]</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
