"use client";

import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft } from "lucide-react";

function GridBackground() {
  return (
    <div className="fixed inset-0 z-0 pointer-events-none opacity-20">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ef444415_1px,transparent_1px),linear-gradient(to_bottom,#ef444415_1px,transparent_1px)] bg-[size:4rem_4rem]" />
    </div>
  );
}

function BoundingBox({ label, children, className, score = "sys.err" }) {
  return (
    <div className={`relative border border-red-500/40 bg-black/50 backdrop-blur-sm ${className}`}>
      <div className="absolute -top-[1px] -left-[1px] bg-red-500 text-black text-[10px] font-mono font-bold px-2 py-0.5 flex items-center gap-2 z-10">
        <span>{label}</span>
        <span className="opacity-70">{score}</span>
      </div>
      <div className="absolute -top-1 -left-1 w-2 h-2 border-t border-l border-red-500" />
      <div className="absolute -top-1 -right-1 w-2 h-2 border-t border-r border-red-500" />
      <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b border-l border-red-500" />
      <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b border-r border-red-500" />
      {children}
    </div>
  );
}

export default function UnauthorizedPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center p-4 cursor-crosshair font-sans">
      <GridBackground />

      <div className="w-full max-w-md relative z-10">
        <BoundingBox label="ACCESS_DENIED" score="err.403" className="p-8 pb-10">
          <div className="mb-10 border-b border-white/10 pb-6 mt-2">
            <h1 className="text-2xl font-bold uppercase tracking-tight flex items-center gap-2 text-red-500">
              <AlertTriangle className="w-5 h-5" />
              UNAUTHORIZED
            </h1>
            <p className="text-gray-500 font-mono text-xs mt-2 uppercase">Insufficient privileges for requested module.</p>
          </div>

          <div className="space-y-6 relative z-10">
            <div className="p-3 border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-mono uppercase leading-relaxed">
              &gt; User lacks required permissions to view this resource.
              <br />
              &gt; Action has been logged.
              <br />
              &gt; Contact administrator if this is an error.
            </div>

            <div className="flex flex-col gap-3 pt-4">
              <button
                onClick={() => router.push("/dashboard")}
                className="w-full h-10 bg-red-500 hover:bg-red-400 text-black font-mono font-bold text-xs uppercase transition-colors"
              >
                [ RETURN_TO_DASHBOARD ]
              </button>
              <button
                onClick={() => router.back()}
                className="w-full h-10 border border-white/20 hover:border-white/60 text-white font-mono text-xs uppercase transition-colors flex items-center justify-center gap-2"
              >
                <ArrowLeft className="w-3 h-3" />
                [ GO_BACK ]
              </button>
            </div>
          </div>
        </BoundingBox>
      </div>
    </div>
  );
}
