"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { API_BASE_URL } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Zap,
  ArrowRight,
  Database,
  Cpu,
  Image,
  Activity,
  CheckCircle,
  Box,
  Code,
  Star,
  Shield,
  TrendingUp,
  Github,
  Twitter,
  Mail,
  Layers
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect, useRef } from "react";

// Animated counter hook
function useCounter(end, duration = 2000) {
  const [count, setCount] = useState(0);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (!started) return;
    let startTime = null;
    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      setCount(Math.floor(progress * end));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [started, end, duration]);

  return { count, startCounter: () => setStarted(true) };
}

export default function HomePage() {
  const router = useRouter();
  const { user } = useAuth();
  const canvasRef = useRef(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Intersection observer to trigger counters
  const [statsVisible, setStatsVisible] = useState(false);

  const counter1 = useCounter(50000, 2000);
  const counter2 = useCounter(99, 1500);
  const counter3 = useCounter(24, 1200);
  const counter4 = useCounter(10, 1000);

  useEffect(() => {
    if (statsVisible) {
      counter1.startCounter();
      counter2.startCounter();
      counter3.startCounter();
      counter4.startCounter();
    }
  }, [statsVisible]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setStatsVisible(true); },
      { threshold: 0.3 }
    );
    const el = document.getElementById("stats-section");
    if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Handle mouse movement for spotlight effects
  const handleMouseMove = (e) => {
    // Update CSS variables for any elements using them
    document.documentElement.style.setProperty('--mouse-x', `${e.clientX}px`);
    document.documentElement.style.setProperty('--mouse-y', `${e.clientY}px`);
  };

  // Particle System
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationFrameId;
    let particles = [];

    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    class Particle {
      constructor() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 2;
        this.speedX = (Math.random() - 0.5) * 0.3;
        this.speedY = (Math.random() - 0.5) * 0.3;
        this.color = `rgba(${100 + Math.random() * 100}, ${100 + Math.random() * 100}, 255, ${Math.random() * 0.4})`;
      }

      update() {
        this.x += this.speedX;
        this.y += this.speedY;

        if (this.x > canvas.width) this.x = 0;
        else if (this.x < 0) this.x = canvas.width;
        if (this.y > canvas.height) this.y = 0;
        else if (this.y < 0) this.y = canvas.height;
      }

      draw() {
        ctx.fillStyle = this.color;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const init = () => {
      particles = [];
      for (let i = 0; i < 80; i++) {
        particles.push(new Particle());
      }
    };

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach(particle => {
        particle.update();
        particle.draw();
      });

      // Connect particles
      for (let i = 0; i < particles.length; i++) {
        for (let j = i; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance < 120) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(100, 100, 255, ${0.08 - distance / 1500})`;
            ctx.lineWidth = 0.5;
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    init();
    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const features = [
    {
      icon: Database,
      title: "Dataset Management",
      description: "Organize, version, and collaborate on your computer vision datasets with enterprise-grade lineage tracking.",
      color: "text-blue-400"
    },
    {
      icon: Image,
      title: "Smart Annotation",
      description: "Accelerate labeling with keyboard shortcuts, zoom & pan, undo/redo, and intelligent class management.",
      color: "text-purple-400"
    },
    {
      icon: Cpu,
      title: "One-Click Training",
      description: "Train YOLOv8–v11 models on your GPU cluster. Full hyperparameter control, zero configuration hell.",
      color: "text-emerald-400"
    },
    {
      icon: Activity,
      title: "Instant Inference",
      description: "Deploy models and run real-time object detection with visual bounding box overlays and latency metrics.",
      color: "text-amber-400"
    }
  ];

  const stats = [
    { value: counter1.count.toLocaleString() + "+", label: "Detections Run", icon: Zap },
    { value: counter2.count + ".2%", label: "Platform Uptime", icon: Shield },
    { value: counter3.count + "+", label: "Model Versions", icon: Box },
    { value: counter4.count + "x", label: "Faster Than Manual", icon: TrendingUp },
  ];

  return (
    <div className="min-h-screen bg-black text-white selection:bg-indigo-500/30 selection:text-indigo-200 font-sans overflow-hidden relative" onMouseMove={handleMouseMove}>

      {/* Particle Background */}
      <canvas ref={canvasRef} className="fixed inset-0 z-0 pointer-events-none opacity-60" />

      {/* Background Ambience */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[20%] w-[500px] h-[500px] rounded-full bg-indigo-600/10 blur-[120px] animate-pulse-glow" />
        <div className="absolute bottom-[-10%] right-[10%] w-[600px] h-[600px] rounded-full bg-violet-600/5 blur-[120px] animate-mesh" />
        <div className="absolute top-[40%] left-[-10%] w-[400px] h-[400px] rounded-full bg-blue-600/5 blur-[100px] animation-delay-2000 animate-mesh" />
      </div>

      {/* Grid Overlay */}
      <div className="fixed inset-0 z-0 bg-grid-white/[0.02] bg-[length:50px_50px] pointer-events-none" />

      {/* Header */}
      <header className="fixed top-0 w-full z-50 border-b border-white/5 bg-black/60 backdrop-blur-2xl">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 cursor-pointer group" onClick={() => router.push("/")}>
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:shadow-indigo-500/40 transition-all duration-300 group-hover:scale-105">
              <Zap className="text-white text-lg" />
            </div>
            <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent">
              Nebula
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm text-gray-400">
            <a href="#features" className="hover:text-white transition-colors">Features</a>
            <a href="#workflow" className="hover:text-white transition-colors">Workflow</a>
            <a href="#stats-section" className="hover:text-white transition-colors">Stats</a>
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <Button
                onClick={() => router.push("/dashboard")}
                className="bg-white text-black hover:bg-white/90 rounded-full px-6 font-semibold shadow-[0_0_20px_rgba(255,255,255,0.15)] transition-all hover:shadow-[0_0_30px_rgba(255,255,255,0.3)] h-9 text-sm"
              >
                Dashboard
                <ArrowRight className="ml-2" />
              </Button>
            ) : (
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => router.push("/login")}
                  className="text-gray-400 hover:text-white h-9 text-sm"
                >
                  Sign In
                </Button>
                <Button
                  onClick={() => router.push("/register")}
                  className="bg-white text-black hover:bg-white/90 rounded-full px-5 font-semibold h-9 text-sm"
                >
                  Get Started
                </Button>
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="relative z-10 pt-16">
        {/* Hero Section */}
        <section className="container mx-auto px-6 py-24 lg:py-36">
          <div className="flex flex-col items-center text-center max-w-4xl mx-auto space-y-8">
            <Badge variant="outline" className="rounded-full px-4 py-1.5 border-white/10 bg-white/5 text-sm backdrop-blur-md hover:bg-white/10 transition-colors animate-fade-in group cursor-default">
              <span className="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-pulse" />
              <span className="group-hover:text-emerald-300 transition-colors">v2.0 — YOLO11 Now Supported</span>
            </Badge>

            <h1 className="text-5xl md:text-7xl font-black tracking-tight leading-[1.1] animate-slide-up">
              Build Computer Vision{" "}
              <br className="hidden sm:block" />
              <span className="block mt-2">
                <span className="glitch-wrapper">
                  <span className="glitch text-gradient" data-text="Without Limits">Without Limits</span>
                </span>
              </span>
            </h1>

            <p className="text-lg md:text-xl text-gray-400 max-w-2xl leading-relaxed animate-slide-up stagger-2" style={{ opacity: 0 }}>
              Upload → Annotate → Train → Deploy. The complete ML pipeline for object detection,
              built for speed and simplicity.
            </p>

            <div className="flex flex-col sm:flex-row items-center gap-4 pt-4 animate-slide-up stagger-3" style={{ opacity: 0 }}>
              <Button
                size="lg"
                onClick={() => router.push(user ? '/dashboard' : '/register')}
                className="h-14 px-8 rounded-full text-base bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_20px_rgba(99,102,241,0.5)] transition-all hover:scale-105"
              >
                Start Building Free
                <ArrowRight className="ml-2" />
              </Button>

              <Button
                variant="outline"
                size="lg"
                onClick={() => window.open(`${API_BASE_URL}/docs`, '_blank')}
                className="h-14 px-8 rounded-full text-base border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20 text-white backdrop-blur-sm"
              >
                <Code className="mr-2" />
                View API Docs
              </Button>
            </div>

            {/* Hero Preview 3D Card */}
            <div className="mt-20 relative w-full aspect-video max-w-5xl group perspective-1000 animate-slide-up stagger-4" style={{ opacity: 0 }}>
              <div className="w-full h-full rounded-2xl border border-white/10 overflow-hidden shadow-2xl shadow-indigo-500/10 transform transition-transform duration-700 hover:rotate-x-12 preserve-3d bg-zinc-950">
                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent z-10" />
                <div className="absolute inset-0 bg-gradient-to-br from-indigo-600/10 via-purple-600/5 to-transparent group-hover:from-indigo-600/15 transition-all duration-700" />

                {/* Dashboard Mockup Content */}
                <div className="flex items-center justify-center w-full h-full p-8">
                  <div className="w-full h-full rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden flex shadow-inner">
                    {/* Sidebar skeleton */}
                    <div className="w-48 border-r border-white/5 p-4 space-y-4 hidden md:block">
                      <div className="flex items-center gap-2 mb-6">
                        <div className="w-6 h-6 rounded-lg bg-indigo-500/30" />
                        <div className="h-3 w-16 bg-white/10 rounded" />
                      </div>
                      {[...Array(5)].map((_, i) => (
                        <div key={i} className={cn("h-8 rounded-lg", i === 0 ? "bg-indigo-500/20" : "bg-white/5")} />
                      ))}
                    </div>
                    {/* Content skeleton */}
                    <div className="flex-1 p-6 space-y-4">
                      <div className="h-6 w-48 bg-white/10 rounded-lg mb-6" />
                      <div className="grid grid-cols-3 gap-4">
                        {[...Array(3)].map((_, i) => (
                          <div key={i} className="h-32 rounded-xl bg-white/5 animate-shimmer border border-white/5" style={{ animationDelay: `${i * 0.3}s` }} />
                        ))}
                      </div>
                      <div className="h-48 rounded-xl bg-white/5 mt-4 animate-shimmer border border-white/5" style={{ animationDelay: '0.9s' }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Features Bento Grid */}
        <section id="features" className="container mx-auto px-6 py-24 border-t border-white/5">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-6">Everything You Need</h2>
            <p className="text-gray-400 max-w-xl mx-auto text-lg">A complete toolkit for building, training, and deploying YOLO models.
              Designed for speed and precision.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-6xl mx-auto">
            {/* Large Card 1 */}
            <div className="md:col-span-2 glass-card p-8 rounded-3xl relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-10 opacity-10 group-hover:opacity-20 transition-opacity duration-500">
                <Database className="text-[12rem] text-blue-500" />
              </div>
              <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="relative z-10 h-full flex flex-col justify-end">
                <div className="w-14 h-14 rounded-2xl bg-blue-500/20 flex items-center justify-center text-blue-400 mb-6 backdrop-blur-md border border-blue-500/20">
                  <Database className="text-3xl" />
                </div>
                <h3 className="text-2xl font-bold mb-3">Dataset Management</h3>
                <p className="text-gray-400 leading-relaxed max-w-md">
                  Organize, version, and collaborate on your computer vision datasets with enterprise-grade lineage tracking.
                  Never lose track of your training data again.
                </p>
              </div>
            </div>

            {/* Tall Card */}
            <div className="glass-card p-8 rounded-3xl relative overflow-hidden group md:row-span-2 flex flex-col">
              <div className="absolute -bottom-10 -right-10 p-4 opacity-10 group-hover:opacity-20 transition-opacity duration-500">
                <Cpu className="text-[10rem] text-emerald-500" />
              </div>
              <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="relative z-10 flex-1">
                <div className="w-14 h-14 rounded-2xl bg-emerald-500/20 flex items-center justify-center text-emerald-400 mb-6 backdrop-blur-md border border-emerald-500/20">
                  <Cpu className="text-3xl" />
                </div>
                <h3 className="text-2xl font-bold mb-3">One-Click Training</h3>
                <p className="text-gray-400 leading-relaxed">
                  Train YOLOv8–v11 models on your GPU cluster. Full hyperparameter control, zero configuration hell.
                </p>
                <div className="mt-8 border border-white/10 rounded-xl bg-black/50 p-4 font-mono text-xs text-emerald-400/80">
                  &gt; yolo train model=yolov8n<br />
                  &gt; epochs=100 imgsz=640<br />
                  <span className="text-white animate-pulse">Training... 45%</span>
                </div>
              </div>
            </div>

            {/* Medium Card 2 */}
            <div className="glass-card p-8 rounded-3xl relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-br from-purple-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="relative z-10">
                <div className="w-14 h-14 rounded-2xl bg-purple-500/20 flex items-center justify-center text-purple-400 mb-6 backdrop-blur-md border border-purple-500/20">
                  <Image className="text-3xl" />
                </div>
                <h3 className="text-2xl font-bold mb-3">Smart Annotation</h3>
                <p className="text-gray-400 leading-relaxed">
                  Accelerate labeling with keyboard shortcuts, auto-labeling, and intelligent class management.
                </p>
              </div>
            </div>

            {/* Medium Card 3 */}
            <div className="glass-card p-8 rounded-3xl relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-br from-amber-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="relative z-10">
                <div className="w-14 h-14 rounded-2xl bg-amber-500/20 flex items-center justify-center text-amber-400 mb-6 backdrop-blur-md border border-amber-500/20">
                  <Activity className="text-3xl" />
                </div>
                <h3 className="text-2xl font-bold mb-3">Instant Inference</h3>
                <p className="text-gray-400 leading-relaxed">
                  Deploy models and run real-time object detection with visual bounding box overlays.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Workflow Section */}
        <section id="workflow" className="py-24 bg-zinc-950/50 border-t border-white/5">
          <div className="container mx-auto px-6">
            <div className="text-center mb-20">
              <h2 className="text-3xl md:text-5xl font-bold mb-6">Pipeline Velocity</h2>
              <p className="text-gray-400 max-w-xl mx-auto text-lg">From raw images to a production-ready API in minutes.</p>
            </div>

            <div className="relative max-w-6xl mx-auto">
              {/* Connecting Beam */}
              <div className="hidden md:block absolute top-[50%] left-0 w-full h-[2px] bg-white/5 -translate-y-1/2">
                <div className="absolute top-0 left-0 h-full w-full bg-gradient-to-r from-transparent via-indigo-500 to-transparent opacity-50 animate-pulse"></div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
                {[
                  { step: "01", title: "Upload", desc: "Drag & drop dataset", icon: Box, color: "text-blue-400", border: "group-hover:border-blue-500/50" },
                  { step: "02", title: "Annotate", desc: "Auto-label tool", icon: Image, color: "text-purple-400", border: "group-hover:border-purple-500/50" },
                  { step: "03", title: "Train", desc: "Serverless training", icon: Cpu, color: "text-emerald-400", border: "group-hover:border-emerald-500/50" },
                  { step: "04", title: "Deploy", desc: "Edge compatible", icon: Activity, color: "text-amber-400", border: "group-hover:border-amber-500/50" },
                ].map((item, i) => (
                  <div key={i} className="relative z-10 group">
                    <div className={cn(
                      "w-full aspect-square md:aspect-auto md:h-64 rounded-3xl bg-black border border-white/10 p-8 flex flex-col items-center justify-center text-center transition-all duration-300 hover:-translate-y-2 hover:shadow-[0_0_30px_rgba(0,0,0,0.5)]",
                      item.border
                    )}>
                      <div className="absolute inset-0 bg-gradient-to-b from-white/[0.03] to-transparent rounded-3xl pointer-events-none"></div>

                      <div className={cn("w-16 h-16 rounded-2xl flex items-center justify-center text-3xl mb-6 bg-white/5 border border-white/5 shadow-inner", item.color)}>
                        <item.icon />
                      </div>

                      <h3 className="text-xl font-bold mb-2 text-white">{item.title}</h3>
                      <p className="text-sm text-gray-400 mb-4">{item.desc}</p>

                      <span className="inline-block px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-mono text-gray-500">
                        STEP {item.step}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section id="stats-section" className="py-24 border-t border-white/5 relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom_left,rgba(79,70,229,0.1),transparent_50%)]"></div>
          <div className="container mx-auto px-6 relative z-10">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8 max-w-5xl mx-auto">
              {stats.map((stat, i) => (
                <div key={i} className="text-center group">
                  <div className="text-5xl md:text-6xl font-black mb-2 bg-gradient-to-b from-white to-white/50 bg-clip-text text-transparent tracking-tighter">
                    {stat.value}
                  </div>
                  <div className="flex items-center justify-center gap-2 text-indigo-300/80 mb-2">
                    <stat.icon />
                    <span className="text-sm font-semibold uppercase tracking-wider">{stat.label}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-24 border-t border-white/5">
          <div className="container mx-auto px-6">
            <div className="relative rounded-3xl border border-white/10 bg-zinc-900 overflow-hidden text-center group">
              <div className="absolute inset-0 bg-gradient-to-br from-indigo-600/20 via-purple-600/10 to-transparent opacity-80" />
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(99,102,241,0.15),transparent_70%)] animate-pulse-glow" />

              <div className="relative z-10 p-12 md:p-20">
                <h2 className="text-3xl md:text-5xl font-bold mb-6">Ready to Build?</h2>
                <p className="text-gray-400 max-w-lg mx-auto mb-8 text-lg">
                  Create your free account and start training YOLO models in under 5 minutes.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <Button
                    size="lg"
                    onClick={() => router.push(user ? '/dashboard' : '/register')}
                    className="h-14 px-8 rounded-full text-lg bg-white text-black hover:bg-white/90 font-semibold shadow-[0_0_40px_rgba(255,255,255,0.2)] transition-all hover:scale-105"
                  >
                    Get Started Free
                    <ArrowRight className="ml-2" />
                  </Button>
                  <Button
                    variant="outline"
                    size="lg"
                    className="h-14 px-8 rounded-full text-lg border-white/20 bg-black/40 hover:bg-white/10 text-white backdrop-blur-md"
                  >
                    <Star className="mr-2" />
                    Star on GitHub
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-white/5 py-12 bg-black">
          <div className="container mx-auto px-6">
            <div className="flex flex-col md:flex-row justify-between items-center gap-6">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                  <Zap className="text-5xl text-white drop-shadow-md" />
                </div>
                <span className="font-semibold text-gray-200">Nebula</span>
                <Badge variant="outline" className="border-white/10 text-xs text-gray-400">v2.1.0</Badge>
              </div>

              <div className="flex items-center gap-6">
                <a href="#" className="text-gray-500 hover:text-white transition-colors hover:scale-110 transform"><Github size={20} /></a>
                <a href="#" className="text-gray-500 hover:text-white transition-colors hover:scale-110 transform"><Twitter size={20} /></a>
                <a href="#" className="text-gray-500 hover:text-white transition-colors hover:scale-110 transform"><Mail size={20} /></a>
              </div>

              <p className="text-sm text-gray-600">
                &copy; {new Date().getFullYear()} Nebula ML. All rights reserved.
              </p>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}
