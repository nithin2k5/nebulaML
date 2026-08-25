"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { API_BASE_URL } from "@/lib/config";
import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { TerminalSquare, Database, Cpu, Activity, Square, GitCommit, Crosshair } from "lucide-react";

function CrosshairCursor() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e) => {
      setMousePos({ x: e.clientX, y: e.clientY });
      setIsVisible(true);
    };
    const handleMouseLeave = () => setIsVisible(false);

    window.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseleave", handleMouseLeave);
    
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, []);

  if (!isVisible) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden mix-blend-difference">
      {/* Horizontal line */}
      <div 
        className="absolute h-[1px] bg-white/30 w-full" 
        style={{ top: mousePos.y }}
      />
      {/* Vertical line */}
      <div 
        className="absolute w-[1px] bg-white/30 h-full" 
        style={{ left: mousePos.x }}
      />
      {/* Center dot */}
      <div 
        className="absolute w-1 h-1 bg-violet-400 -translate-x-1/2 -translate-y-1/2"
        style={{ left: mousePos.x, top: mousePos.y }}
      />
    </div>
  );
}

function GridBackground() {
  return (
    <div className="fixed inset-0 z-0 pointer-events-none opacity-20">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#a78bfa15_1px,transparent_1px),linear-gradient(to_bottom,#a78bfa15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
    </div>
  );
}

function BoundingBox({ label, children, className, score = "0.99" }) {
  return (
    <div className={`relative border border-violet-500/40 bg-black/50 backdrop-blur-sm ${className}`}>
      <div className="absolute -top-[1px] -left-[1px] bg-violet-500 text-black text-[10px] sm:text-xs font-mono font-bold px-2 py-0.5 flex items-center gap-2">
        <span>{label}</span>
        <span className="opacity-70">{score}</span>
      </div>
      {/* Corner markers */}
      <div className="absolute -top-1 -left-1 w-2 h-2 border-t border-l border-violet-400" />
      <div className="absolute -top-1 -right-1 w-2 h-2 border-t border-r border-violet-400" />
      <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b border-l border-violet-400" />
      <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b border-r border-violet-400" />
      {children}
    </div>
  );
}

function ParameterItem({ label, value }) {
  return (
    <div className="flex justify-between items-end border-b border-white/10 pb-1 mb-3">
      <span className="font-mono text-xs text-gray-500 uppercase">{label}</span>
      <span className="font-mono text-sm text-white">{value}</span>
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const { user } = useAuth();
  const [time, setTime] = useState("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime(now.toISOString().split('T')[1].slice(0, 12));
    };
    updateTime();
    const interval = setInterval(updateTime, 100);
    return () => clearInterval(interval);
  }, []);

  const handleAction = (path) => {
    router.push(path);
  };

  return (
    <div className="min-h-screen bg-black text-white font-sans selection:bg-violet-500/30 selection:text-violet-200 cursor-crosshair">
      <CrosshairCursor />
      <GridBackground />

      {/* Header/Nav - Engineered style */}
      <header className="fixed top-0 w-full z-40 border-b border-white/10 bg-black/80 backdrop-blur-md">
        <div className="flex items-center justify-between px-6 h-12">
          <div className="flex items-center gap-4">
            <div className="w-2 h-2 bg-violet-500 rounded-none animate-pulse" />
            <span className="font-mono text-sm font-bold tracking-widest uppercase">NBLA_ML // SYS_ONLINE</span>
          </div>
          
          <div className="hidden md:flex items-center gap-8">
            <span className="font-mono text-xs text-gray-500">T_SYS: {time}</span>
            <span className="font-mono text-xs text-gray-500">LATENCY: 12ms</span>
          </div>

          <div className="flex items-center gap-4">
            {user ? (
              <button
                onClick={() => handleAction("/dashboard")}
                className="font-mono text-xs font-bold px-4 py-1.5 border border-white/20 hover:border-violet-400 hover:text-violet-400 transition-colors uppercase"
              >
                [ Access_Workspace ]
              </button>
            ) : (
              <>
                <button
                  onClick={() => handleAction("/login")}
                  className="font-mono text-xs text-gray-400 hover:text-white uppercase transition-colors"
                >
                  Authenticate
                </button>
                <button
                  onClick={() => handleAction("/register")}
                  className="font-mono text-xs font-bold bg-white text-black px-4 py-1.5 hover:bg-violet-400 transition-colors uppercase"
                >
                  Initialize
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="relative z-10 pt-24 px-6 md:px-12 max-w-7xl mx-auto space-y-24 pb-32">
        
        {/* Hero Section */}
        <section className="min-h-[85vh] flex flex-col justify-center relative">
          <div className="absolute top-1/2 right-0 -translate-y-1/2 w-[500px] h-[500px] border border-white/5 rounded-full blur-[120px] bg-violet-500/10 pointer-events-none" />
          
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center relative z-10">
            <div className="lg:col-span-7 space-y-8">
              <div className="inline-flex items-center gap-3 px-3 py-1.5 border border-violet-500/30 bg-violet-500/10 mb-2 shadow-[0_0_15px_rgba(167,139,250,0.1)]">
                <div className="w-2 h-2 bg-violet-400 animate-pulse shadow-[0_0_10px_rgba(167,139,250,0.8)]" />
                <span className="font-mono text-[10px] text-violet-300 uppercase tracking-widest font-bold">NBLA_ML // v2.4.0_STABLE</span>
              </div>
              
              <h1 className="text-5xl md:text-7xl lg:text-[5.5rem] font-black uppercase tracking-tighter leading-[0.85]">
                <span className="block text-white">ENGINEER</span>
                <span className="block text-transparent border-text">VISION MODELS</span>
                <span className="block text-white">AT SCALE.</span>
              </h1>
              
              <p className="font-mono text-sm md:text-base text-gray-400 max-w-xl leading-relaxed border-l-2 border-violet-500/50 pl-5 py-1">
                A bare-metal control surface for object detection pipelines. 
                Zero abstractions. Direct GPU access. Native edge compilation.
              </p>

              <div className="flex flex-col sm:flex-row gap-4 pt-6">
                <button
                  onClick={() => handleAction(user ? "/dashboard" : "/register")}
                  className="group relative px-8 py-4 bg-violet-500 hover:bg-violet-400 text-black font-mono font-bold text-sm uppercase transition-colors flex items-center justify-center gap-4"
                >
                  <span>[ INIT_WORKSPACE ]</span>
                  <Activity className="w-4 h-4 opacity-50 group-hover:opacity-100" />
                </button>
                <button
                  onClick={() => window.open(`${API_BASE_URL}/docs`, '_blank')}
                  className="px-8 py-4 border border-white/20 hover:border-violet-500/50 hover:bg-violet-500/10 text-white font-mono font-bold text-sm uppercase transition-all flex items-center justify-center gap-2"
                >
                  <span>// READ_DOCS</span>
                </button>
              </div>
            </div>

            <div className="lg:col-span-5 hidden lg:block relative">
              <BoundingBox label="SYS.TELEMETRY" score="1.00" className="p-1">
                <div className="bg-black border border-white/10 p-6 space-y-6">
                  {/* Visualizer mock */}
                  <div className="relative aspect-video bg-[#050505] border border-white/5 overflow-hidden flex items-center justify-center">
                    <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:1rem_1rem]" />
                    <div className="absolute inset-x-0 h-[1px] bg-violet-500/50 scan-line" />
                    
                    {/* Bounding box mock inside */}
                    <div className="absolute top-[20%] left-[20%] w-[40%] h-[35%] border border-emerald-500 bg-emerald-500/10 group hover:bg-emerald-500/20 transition-colors">
                      <div className="absolute -top-[18px] -left-[1px] bg-emerald-500 text-black text-[9px] font-mono px-1.5 font-bold tracking-widest">VEHICLE 0.98</div>
                      <div className="absolute inset-0 border border-emerald-500/30 m-1" />
                    </div>
                    <div className="absolute bottom-[15%] right-[25%] w-[25%] h-[50%] border border-amber-500 bg-amber-500/10 group hover:bg-amber-500/20 transition-colors">
                      <div className="absolute -top-[18px] -left-[1px] bg-amber-500 text-black text-[9px] font-mono px-1.5 font-bold tracking-widest">PEDESTRIAN 0.91</div>
                      <div className="absolute inset-0 border border-amber-500/30 m-1" />
                    </div>
                  </div>
                  
                  <div className="space-y-3 pt-2">
                    <ParameterItem label="GPU_ALLOC" value="A100-SXM4" />
                    <ParameterItem label="TENSOR_RT" value="ACTIVE" />
                    <ParameterItem label="INFERENCE" value="2.4ms / FRAME" />
                  </div>
                </div>
              </BoundingBox>
            </div>

          </div>
        </section>

        {/* Pipeline Section */}
        <section className="space-y-12 border-t border-white/10 pt-24">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-3xl font-bold uppercase tracking-tight">Pipeline.Sequence</h2>
              <p className="font-mono text-sm text-gray-500 mt-2">SYS_WORKFLOW_DEFINITIONS</p>
            </div>
            <div className="hidden sm:flex items-center gap-2 font-mono text-xs text-gray-600">
              <GitCommit className="w-4 h-4" />
              <span>STRICT_LINEAR_EXECUTION</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 border border-white/10 bg-black">
            {[
              { id: "01", title: "Ingest", desc: "Upload datasets. Organize, version, and manage labels with raw file integrity.", icon: Database },
              { id: "02", title: "Annotate", desc: "Define bounding boxes. Keyboard-driven precision for rapid dataset curation.", icon: Crosshair },
              { id: "03", title: "Train", desc: "Allocate GPU instances. Define epochs, batch size, and architecture.", icon: Cpu },
              { id: "04", title: "Deploy", desc: "Expose via API or run WASM-accelerated inference directly in the browser.", icon: TerminalSquare }
            ].map((step, idx) => (
              <div key={step.id} className={`p-6 ${idx !== 3 ? 'border-b md:border-b-0 md:border-r border-white/10' : ''} group hover:bg-white/[0.02] transition-colors`}>
                <div className="flex justify-between items-start mb-12">
                  <span className="font-mono text-xs text-violet-500 font-bold">SEQ_{step.id}</span>
                  <step.icon className="w-5 h-5 text-gray-600 group-hover:text-violet-400 transition-colors" />
                </div>
                <h3 className="text-xl font-bold uppercase mb-3">{step.title}</h3>
                <p className="font-mono text-xs text-gray-400 leading-relaxed">
                  {step.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* System Capabilities Section */}
        <section className="space-y-12 border-t border-white/10 pt-24">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-3xl font-bold uppercase tracking-tight">System.Capabilities</h2>
              <p className="font-mono text-sm text-gray-500 mt-2">PLATFORM_FEATURE_MATRIX</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { id: "FEAT_01", title: "Smart Annotation", desc: "AI-assisted bounding box generation. Click once to auto-segment and label objects instantly." },
              { id: "FEAT_02", title: "Version Control", desc: "Immutable dataset snapshots. Roll back to any previous state of your annotations effortlessly." },
              { id: "FEAT_03", title: "Active Learning", desc: "Deploy your model to the edge and automatically pipe low-confidence predictions back for review." },
              { id: "FEAT_04", title: "Synthetic Data", desc: "Generate edge-case training data using integrated diffusion models to fix class imbalances." },
              { id: "FEAT_05", title: "Hyperparameter Tuning", desc: "Automated genetic algorithms to find the optimal learning rate, batch size, and momentum." },
              { id: "FEAT_06", title: "Hardware Agnostic", desc: "Train on cloud A100s, deploy to Raspberry Pi. Export to CoreML, TensorRT, TFLite, and ONNX." }
            ].map((feat) => (
              <BoundingBox key={feat.id} label={feat.id} score="SYS.ACTIVE" className="p-6 hover:bg-white/[0.02] transition-colors">
                <h3 className="text-lg font-bold uppercase mt-4 mb-2 text-white">{feat.title}</h3>
                <p className="font-mono text-xs text-gray-400 leading-relaxed">
                  {feat.desc}
                </p>
              </BoundingBox>
            ))}
          </div>
        </section>

        {/* Engine Specs Section */}
        <section className="space-y-12 border-t border-white/10 pt-24">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-3xl font-bold uppercase tracking-tight">Engine.Specs</h2>
              <p className="font-mono text-sm text-gray-500 mt-2">HARDWARE_&_SOFTWARE_TARGETS</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <BoundingBox label="INFERENCE_MODES" score="SYS.OK">
              <div className="p-8 space-y-6">
                <div className="flex justify-between border-b border-white/10 pb-4">
                  <span className="font-mono text-xs uppercase text-gray-400">Target</span>
                  <span className="font-mono text-xs uppercase text-violet-400">Latency Profile</span>
                </div>
                {[
                  { target: "ONNX_RUNTIME (BROWSER)", latency: "~15-30ms / FRAME" },
                  { target: "FASTAPI_BACKEND (CLOUD_GPU)", latency: "~8-12ms / FRAME" },
                  { target: "COREML (iOS NEURAL_ENGINE)", latency: "~4-6ms / FRAME" },
                  { target: "TENSORRT (JETSON_NANO)", latency: "~10-15ms / FRAME" }
                ].map((spec, i) => (
                  <div key={i} className="flex justify-between items-center group">
                    <span className="font-mono text-sm text-white group-hover:text-violet-300 transition-colors">{spec.target}</span>
                    <span className="font-mono text-xs text-gray-500">{spec.latency}</span>
                  </div>
                ))}
              </div>
            </BoundingBox>

            <BoundingBox label="ARCHITECTURE_SUPPORT" score="SYS.OK">
              <div className="p-8 space-y-6">
                <div className="flex justify-between border-b border-white/10 pb-4">
                  <span className="font-mono text-xs uppercase text-gray-400">Model_Family</span>
                  <span className="font-mono text-xs uppercase text-violet-400">Status</span>
                </div>
                {[
                  { model: "YOLOv8 (N, S, M, L, X)", status: "SUPPORTED" },
                  { model: "YOLOv10 (N, S, M, B, L, X)", status: "SUPPORTED" },
                  { model: "YOLOv11 (N, S, M, L, X)", status: "BETA_TESTING" },
                  { model: "RT-DETR (ResNet50)", status: "EXPERIMENTAL" }
                ].map((spec, i) => (
                  <div key={i} className="flex justify-between items-center group">
                    <span className="font-mono text-sm text-white group-hover:text-violet-300 transition-colors">{spec.model}</span>
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-none ${spec.status === 'SUPPORTED' ? 'bg-emerald-500' : spec.status === 'BETA_TESTING' ? 'bg-amber-500 animate-pulse' : 'bg-gray-500'}`} />
                      <span className="font-mono text-[10px] text-gray-400">{spec.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </BoundingBox>
          </div>
        </section>

        {/* Terminal / Technical Interface */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-12 border-t border-white/10 pt-24 items-center">
          <div>
            <h2 className="text-3xl font-bold uppercase tracking-tight mb-4">Command.Interface</h2>
            <p className="font-mono text-sm text-gray-400 mb-8 max-w-md">
              Control the entire platform through terminal commands. No GUI required for advanced orchestrations.
            </p>
            
            <div className="space-y-4 font-mono text-xs">
              <div className="flex items-center gap-4">
                <div className="w-8 h-[1px] bg-violet-500" />
                <span className="text-white">pip install nebulaml</span>
              </div>
              <div className="flex items-center gap-4">
                <div className="w-8 h-[1px] bg-violet-500/30" />
                <span className="text-gray-500">nebula init --workspace proj_alpha</span>
              </div>
              <div className="flex items-center gap-4">
                <div className="w-8 h-[1px] bg-violet-500/30" />
                <span className="text-gray-500">nebula train --model yolov8n --data dataset.yaml</span>
              </div>
            </div>
          </div>

          <BoundingBox label="TERMINAL_OUTPUT" score="sys.ok" className="p-0 bg-black">
            <div className="p-6 font-mono text-xs sm:text-sm space-y-3 h-64 overflow-hidden relative">
              <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black pointer-events-none z-10" />
              <div className="text-gray-500">Initializing distributed training cluster...</div>
              <div className="text-gray-500">Found 4x NVIDIA A100-SXM4-40GB</div>
              <div className="text-white">Loading YOLOv8n architecture...</div>
              <div className="text-gray-500">Epoch 1/100</div>
              <div className="text-violet-400 flex items-center">
                <span className="mr-4">train/loss:</span>
                <span className="w-32 h-1 bg-white/10 mr-4">
                  <span className="block h-full bg-violet-500 w-1/5" />
                </span>
                <span>2.431</span>
              </div>
              <div className="text-gray-500">Epoch 2/100</div>
              <div className="text-violet-400 flex items-center">
                <span className="mr-4">train/loss:</span>
                <span className="w-32 h-1 bg-white/10 mr-4">
                  <span className="block h-full bg-violet-500 w-2/5" />
                </span>
                <span>1.821</span>
              </div>
              <div className="animate-pulse w-2 h-4 bg-white mt-4" />
            </div>
          </BoundingBox>
        </section>

      </main>

      {/* Footer */}
      <footer className="border-t border-white/10 bg-black py-12 px-6 md:px-12 relative z-10">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-start md:items-center gap-8">
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="w-2 h-2 bg-violet-500 rounded-none" />
              <span className="font-mono text-sm font-bold tracking-widest uppercase">NBLA_ML // KERNEL</span>
            </div>
            <p className="font-mono text-xs text-gray-500 max-w-sm leading-relaxed">
              Precision tooling for computer vision engineers. 
              Designed for performance, clarity, and total hardware control.
            </p>
          </div>
          
          <div className="flex gap-12 font-mono text-xs">
            <div className="space-y-3">
              <span className="text-white font-bold block uppercase tracking-widest mb-4">Resources</span>
              <a href="#" className="block text-gray-500 hover:text-violet-400 transition-colors uppercase">Documentation</a>
              <a href="#" className="block text-gray-500 hover:text-violet-400 transition-colors uppercase">API_Reference</a>
              <a href="#" className="block text-gray-500 hover:text-violet-400 transition-colors uppercase">GitHub_Repo</a>
            </div>
            <div className="space-y-3">
              <span className="text-white font-bold block uppercase tracking-widest mb-4">System</span>
              <a href="#" className="block text-gray-500 hover:text-violet-400 transition-colors uppercase">Status_Page</a>
              <a href="#" className="block text-gray-500 hover:text-violet-400 transition-colors uppercase">Changelog</a>
              <a href="#" className="block text-gray-500 hover:text-violet-400 transition-colors uppercase">Telemetry</a>
            </div>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-12 pt-8 border-t border-white/10 flex flex-col sm:flex-row justify-between items-center gap-4 font-mono text-[10px] text-gray-600 uppercase">
          <span>&copy; {new Date().getFullYear()} NBLA_ML SYSTEMS. ALL_RIGHTS_RESERVED.</span>
          <span>SYS_VERSION: 2.4.0_STABLE // UPTIME: 99.99%</span>
        </div>
      </footer>

      <style jsx global>{`
        .border-text {
          -webkit-text-stroke: 1px rgba(255, 255, 255, 0.8);
          color: transparent;
        }
        body {
          background-color: #000;
        }
        @keyframes scan {
          0%, 100% { transform: translateY(-5000%); opacity: 0; }
          5% { opacity: 1; }
          95% { opacity: 1; }
          50% { transform: translateY(5000%); }
        }
        .scan-line {
          animation: scan 3s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
