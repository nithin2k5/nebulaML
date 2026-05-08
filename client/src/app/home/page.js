"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { API_BASE_URL } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Zap, ArrowRight, Database, Cpu, Image as ImageIcon, Activity,
  CheckCircle, Box, Code, Star, Shield, TrendingUp, Github, Twitter, Mail, Layers, Command, ChevronDown, Plus
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect, useRef } from "react";
import { motion, useScroll, useTransform, useSpring, useMotionValue, useMotionTemplate, AnimatePresence } from "framer-motion";

function useCounter(end, duration = 2000) {
  const [count, setCount] = useState(0);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (!started) return;
    let startTime = null;
    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const easeProgress = 1 - Math.pow(1 - progress, 4);
      setCount(Math.floor(easeProgress * end));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [started, end, duration]);

  return { count, startCounter: () => setStarted(true) };
}

function SpotlightCard({ children, className }) {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function handleMouseMove({ currentTarget, clientX, clientY }) {
    const { left, top } = currentTarget.getBoundingClientRect();
    mouseX.set(clientX - left);
    mouseY.set(clientY - top);
  }

  return (
    <div
      className={cn("relative group overflow-hidden rounded-3xl bg-zinc-950 border border-white/5 transition-colors hover:border-white/10", className)}
      onMouseMove={handleMouseMove}
    >
      <motion.div
        className="pointer-events-none absolute -inset-px rounded-3xl opacity-0 transition duration-500 group-hover:opacity-100 z-10"
        style={{
          background: useMotionTemplate`radial-gradient(500px circle at ${mouseX}px ${mouseY}px, rgba(99,102,241,0.15), transparent 80%)`,
        }}
      />
      <div className="relative z-20 h-full">{children}</div>
    </div>
  );
}

function FAQItem({ question, answer }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="border-b border-white/5 last:border-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full py-6 flex items-center justify-between text-left focus:outline-none group"
      >
        <span className="text-lg font-medium text-white group-hover:text-indigo-400 transition-colors">{question}</span>
        <motion.div
          animate={{ rotate: isOpen ? 45 : 0 }}
          transition={{ duration: 0.3, ease: "anticipate" }}
          className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center border border-white/10 group-hover:border-indigo-500/30"
        >
          <Plus className="w-4 h-4 text-gray-400 group-hover:text-indigo-400" />
        </motion.div>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "anticipate" }}
            className="overflow-hidden"
          >
            <p className="pb-6 text-gray-400 leading-relaxed font-light">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const { user } = useAuth();
  const canvasRef = useRef(null);
  
  // Parallax scroll effects
  const { scrollY } = useScroll();
  const yBg = useTransform(scrollY, [0, 1000], [0, 300]);
  const yHero = useTransform(scrollY, [0, 800], [0, 200]);
  const opacityHero = useTransform(scrollY, [0, 400], [1, 0]);

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

  // Neural Particle Background
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
        this.size = Math.random() * 1.5 + 0.5;
        this.baseX = this.x;
        this.baseY = this.y;
        this.density = (Math.random() * 20) + 1;
        this.speedX = (Math.random() - 0.5) * 0.2;
        this.speedY = (Math.random() - 0.5) * 0.2;
      }

      update(mousePos) {
        this.x += this.speedX;
        this.y += this.speedY;

        if (this.x > canvas.width) this.x = 0;
        else if (this.x < 0) this.x = canvas.width;
        if (this.y > canvas.height) this.y = 0;
        else if (this.y < 0) this.y = canvas.height;

        // Neural interaction: slight magnetic pull to mouse
        if (mousePos.x) {
          const dx = mousePos.x - this.x;
          const dy = mousePos.y - this.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          const forceDirectionX = dx / distance;
          const forceDirectionY = dy / distance;
          const maxDistance = 150;
          const force = (maxDistance - distance) / maxDistance;
          const directionX = forceDirectionX * force * this.density * 0.05;
          const directionY = forceDirectionY * force * this.density * 0.05;
          
          if (distance < maxDistance) {
            this.x += directionX;
            this.y += directionY;
          }
        }
      }

      draw() {
        ctx.fillStyle = `rgba(99, 102, 241, ${0.3 + Math.random() * 0.3})`;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const init = () => {
      particles = [];
      for (let i = 0; i < 100; i++) {
        particles.push(new Particle());
      }
    };

    let mousePos = { x: null, y: null };
    const handleMouse = (e) => {
      mousePos.x = e.clientX;
      mousePos.y = e.clientY;
    };
    window.addEventListener('mousemove', handleMouse);

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach(particle => {
        particle.update(mousePos);
        particle.draw();
      });

      for (let i = 0; i < particles.length; i++) {
        for (let j = i; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance < 100) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(139, 92, 246, ${0.15 - distance / 1000})`;
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
      window.removeEventListener('mousemove', handleMouse);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const features = [
    {
      icon: Database,
      title: "Dataset Management",
      description: "Organize, version, and collaborate on your computer vision datasets with enterprise-grade lineage tracking.",
      color: "from-blue-500 to-cyan-400"
    },
    {
      icon: ImageIcon,
      title: "Smart Annotation",
      description: "Accelerate labeling with keyboard shortcuts, auto-labeling, and intelligent class management.",
      color: "from-purple-500 to-pink-400"
    },
    {
      icon: Cpu,
      title: "One-Click Training",
      description: "Train YOLOv8–v11 models on your GPU cluster. Full hyperparameter control, zero configuration hell.",
      color: "from-emerald-400 to-teal-400"
    },
    {
      icon: Activity,
      title: "Instant Inference",
      description: "Deploy models and run real-time object detection with visual bounding box overlays.",
      color: "from-amber-400 to-orange-400"
    }
  ];

  const statsList = [
    { value: counter1.count.toLocaleString() + "+", label: "Detections Run", icon: Zap },
    { value: counter2.count + ".2%", label: "Platform Uptime", icon: Shield },
    { value: counter3.count + "+", label: "Model Versions", icon: Box },
    { value: counter4.count + "x", label: "Faster Than Manual", icon: TrendingUp },
  ];

  return (
    <div className="min-h-screen bg-black text-white selection:bg-indigo-500/30 selection:text-indigo-200 font-sans overflow-x-hidden relative scroll-smooth">

      {/* Global Backgrounds */}
      <div className="fixed inset-0 z-0 pointer-events-none bg-black">
        <canvas ref={canvasRef} className="absolute inset-0 opacity-40 mix-blend-screen" />
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay"></div>
        <motion.div style={{ y: yBg }} className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[-20%] left-[20%] w-[800px] h-[800px] rounded-full bg-indigo-600/10 blur-[150px] animate-pulse-glow" />
          <div className="absolute bottom-[-10%] right-[10%] w-[600px] h-[600px] rounded-full bg-violet-600/10 blur-[150px]" />
          <div className="absolute top-[40%] left-[-10%] w-[500px] h-[500px] rounded-full bg-blue-600/10 blur-[150px]" />
        </motion.div>
      </div>

      {/* Header */}
      <motion.header 
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="fixed top-0 w-full z-50 border-b border-white/5 bg-black/40 backdrop-blur-2xl"
      >
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <motion.div 
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center gap-3 cursor-pointer group" 
            onClick={() => router.push("/")}
          >
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-[0_0_20px_rgba(99,102,241,0.4)] transition-all">
              <Zap className="text-white text-lg drop-shadow-[0_0_8px_rgba(255,255,255,0.8)]" />
            </div>
            <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent group-hover:text-white transition-colors">
              Nebula
            </span>
          </motion.div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-400">
            {['Features', 'Workflow', 'Stats'].map((item) => (
              <a key={item} href={`#${item.toLowerCase()}`} className="relative hover:text-white transition-colors group">
                {item}
                <span className="absolute -bottom-1 left-0 w-0 h-px bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300 group-hover:w-full" />
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <Button
                onClick={() => router.push("/dashboard")}
                className="bg-white text-black hover:bg-white/90 rounded-full px-6 font-semibold shadow-[0_0_20px_rgba(255,255,255,0.15)] transition-all hover:shadow-[0_0_30px_rgba(255,255,255,0.4)] hover:-translate-y-0.5 h-9 text-sm"
              >
                Dashboard
                <ArrowRight className="ml-2 w-4 h-4" />
              </Button>
            ) : (
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  onClick={() => router.push("/login")}
                  className="text-gray-400 hover:text-white h-9 text-sm hover:bg-white/5"
                >
                  Sign In
                </Button>
                <Button
                  onClick={() => router.push("/register")}
                  className="bg-white text-black hover:bg-white/90 rounded-full px-5 font-semibold h-9 text-sm shadow-[0_0_20px_rgba(255,255,255,0.2)] hover:shadow-[0_0_30px_rgba(255,255,255,0.4)] transition-all hover:-translate-y-0.5"
                >
                  Get Started
                </Button>
              </div>
            )}
          </div>
        </div>
      </motion.header>

      <main className="relative z-10 pt-24 md:pt-32">
        {/* Hero Section */}
        <section className="container mx-auto px-6 pb-24 lg:pb-36 relative min-h-[80vh] flex flex-col justify-center">
          <motion.div 
            style={{ y: yHero }}
            className="flex flex-col items-center text-center max-w-5xl mx-auto space-y-8"
          >
            <motion.div 
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.6, ease: "easeOut", delay: 0.1 }}
            >
              <Badge variant="outline" className="rounded-full px-4 py-1.5 border-white/10 bg-white/5 text-sm backdrop-blur-md hover:bg-white/10 hover:border-white/20 transition-all shadow-[0_0_15px_rgba(255,255,255,0.05)] flex items-center gap-2 cursor-default">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span className="text-gray-200">v2.0 — YOLO11 Now Supported</span>
              </Badge>
            </motion.div>

            <motion.h1 
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.2 }}
              className="text-6xl md:text-8xl font-black tracking-tighter leading-[1.05]"
            >
              Build Computer Vision{" "}
              <br className="hidden sm:block" />
              <span className="relative inline-block mt-2">
                <span className="absolute -inset-2 bg-gradient-to-r from-indigo-500/20 via-purple-500/20 to-pink-500/20 blur-xl rounded-full opacity-0 animate-pulse-glow" />
                <span className="relative bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent" style={{ textShadow: '0 0 40px rgba(99,102,241,0.4)' }}>
                  Without Limits
                </span>
              </span>
            </motion.h1>

            <motion.p 
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.4 }}
              className="text-lg md:text-xl text-gray-400 max-w-2xl leading-relaxed font-light"
            >
              Upload → Annotate → Train → Deploy. The complete ML pipeline for object detection,
              built for speed and unprecedented precision.
            </motion.p>

            <motion.div 
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.6 }}
              className="flex flex-col sm:flex-row items-center gap-4 pt-6"
            >
              <Button
                size="lg"
                onClick={() => router.push(user ? '/dashboard' : '/register')}
                className="h-14 px-8 rounded-full text-base bg-white text-black hover:bg-gray-100 font-semibold shadow-[0_0_30px_rgba(255,255,255,0.2)] transition-all hover:scale-105 hover:shadow-[0_0_40px_rgba(255,255,255,0.4)] group relative overflow-hidden"
              >
                <span className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/50 to-transparent -translate-x-[150%] skew-x-[-20deg] group-hover:animate-shine" />
                Start Building Free
                <ArrowRight className="ml-2 w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </Button>

              <Button
                variant="outline"
                size="lg"
                onClick={() => window.open(`${API_BASE_URL}/docs`, '_blank')}
                className="h-14 px-8 rounded-full text-base border-white/10 bg-black/40 hover:bg-white/10 hover:border-white/20 text-white backdrop-blur-md transition-all hover:scale-105"
              >
                <Command className="mr-2 w-4 h-4 text-gray-400" />
                View API Docs
              </Button>
            </motion.div>

            {/* Hero 3D Interactive Card */}
            <motion.div 
              initial={{ y: 100, opacity: 0, rotateX: 20 }}
              animate={{ y: 0, opacity: 1, rotateX: 0 }}
              transition={{ duration: 1.2, ease: "easeOut", delay: 0.8 }}
              className="mt-24 relative w-full aspect-[16/9] max-w-6xl group perspective-[2000px] mx-auto z-20"
            >
              <div className="absolute -inset-1 bg-gradient-to-b from-indigo-500/20 to-purple-500/0 rounded-[2rem] blur-2xl opacity-50 group-hover:opacity-100 transition-opacity duration-1000" />
              <motion.div 
                whileHover={{ rotateX: 5, rotateY: -2, scale: 1.02 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                className="w-full h-full rounded-[2rem] border border-white/10 overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)] bg-zinc-950/80 backdrop-blur-xl relative transform-gpu preserve-3d"
              >
                {/* Floating elements inside mockup */}
                <div className="absolute inset-0 bg-gradient-to-tr from-indigo-500/5 via-transparent to-purple-500/5" />
                <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
                
                <div className="flex items-center justify-center w-full h-full p-6 md:p-8">
                  <div className="w-full h-full rounded-xl border border-white/5 bg-black/40 overflow-hidden flex shadow-2xl relative">
                    
                    {/* Simulated live scanner overlay */}
                    <div className="absolute top-0 left-0 w-full h-[2px] bg-indigo-500/50 shadow-[0_0_10px_rgba(99,102,241,0.8)] animate-scanline z-30" />

                    {/* Sidebar skeleton */}
                    <div className="w-48 border-r border-white/5 p-4 space-y-5 hidden md:block bg-black/20">
                      <div className="flex items-center gap-3 mb-8">
                        <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.5)]">
                          <Zap className="text-white w-4 h-4" />
                        </div>
                        <div className="h-4 w-20 bg-white/10 rounded" />
                      </div>
                      {[...Array(6)].map((_, i) => (
                        <div key={i} className={cn("h-8 rounded-lg transition-colors", i === 0 ? "bg-white/10 border border-white/5" : "bg-white/5 hover:bg-white/10")} />
                      ))}
                    </div>
                    {/* Content skeleton */}
                    <div className="flex-1 p-6 md:p-8 space-y-6 bg-black/10 relative overflow-hidden">
                      {/* Floating toasts */}
                      <div className="absolute top-6 right-6 h-12 w-48 bg-zinc-900/80 backdrop-blur-md rounded-lg border border-white/10 shadow-xl flex items-center px-4 gap-3 animate-float-slow z-20">
                        <CheckCircle className="text-emerald-400 w-4 h-4" />
                        <div className="h-2 w-24 bg-white/20 rounded" />
                      </div>

                      <div className="h-8 w-64 bg-white/10 rounded-lg mb-8" />
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {[...Array(4)].map((_, i) => (
                          <div key={i} className="h-24 rounded-xl bg-gradient-to-br from-white/5 to-transparent border border-white/5 relative overflow-hidden group">
                             <div className="absolute inset-0 bg-indigo-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                        ))}
                      </div>
                      
                      {/* Live Training Chart Simulation */}
                      <div className="h-64 rounded-xl bg-zinc-950 border border-white/5 mt-6 relative overflow-hidden p-4 flex flex-col justify-end">
                         <div className="absolute top-4 left-4 h-4 w-32 bg-white/10 rounded" />
                         <div className="absolute top-4 right-4 flex items-center gap-2">
                           <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                           </span>
                           <span className="text-xs text-emerald-400 font-mono">Training Active</span>
                         </div>
                         {/* Faux Graph Lines */}
                         <div className="w-full h-32 flex items-end gap-1 opacity-50">
                           {[...Array(40)].map((_, i) => (
                             <motion.div 
                               key={i}
                               initial={{ height: "10%" }}
                               animate={{ height: `${20 + Math.random() * 80}%` }}
                               transition={{ duration: 2, repeat: Infinity, repeatType: "reverse", delay: i * 0.05 }}
                               className="flex-1 bg-gradient-to-t from-indigo-500/40 to-indigo-400 rounded-t-sm"
                             />
                           ))}
                         </div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          </motion.div>
        </section>

        {/* Interactive Demo Section */}
        <section className="py-32 border-t border-white/5 relative bg-black overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(16,185,129,0.05),transparent_70%)]" />
          <div className="container mx-auto px-6 relative z-10">
            <div className="flex flex-col md:flex-row items-center gap-16">
              <div className="flex-1 space-y-8">
                <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 bg-emerald-500/10">Real-time Inference</Badge>
                <h2 className="text-4xl md:text-5xl font-bold tracking-tight">See it in action. <br/> <span className="text-gray-500">Live edge deployment.</span></h2>
                <p className="text-gray-400 text-lg font-light leading-relaxed">
                  Our optimized ONNX runtime allows you to run your deployed YOLO models directly in the browser or at the edge with sub-millisecond latency. 
                  Experience the precision of foundation models fine-tuned to your custom datasets.
                </p>
                <ul className="space-y-4">
                  {[
                    "Zero server latency for edge devices.",
                    "WebAssembly & WebGL hardware acceleration.",
                    "Dynamic thresholding and NMS."
                  ].map((item, i) => (
                    <li key={i} className="flex items-center gap-3 text-gray-300">
                      <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                        <CheckCircle className="w-3 h-3 text-emerald-400" />
                      </div>
                      <span className="font-light">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex-1 w-full max-w-xl">
                <SpotlightCard className="aspect-video relative bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden p-0 flex items-center justify-center">
                  <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1494205577727-d32e58564756?auto=format&fit=crop&q=80')] bg-cover bg-center opacity-40"></div>
                  
                  {/* Faux Bounding Boxes */}
                  <motion.div 
                    initial={{ width: 0, height: 0, opacity: 0 }}
                    whileInView={{ width: "40%", height: "50%", opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.5, type: "spring" }}
                    className="absolute top-[20%] left-[10%] border-2 border-emerald-400 bg-emerald-400/10 z-10 flex items-start"
                  >
                    <span className="bg-emerald-400 text-black text-[10px] font-bold px-2 py-0.5">Vehicle 0.98</span>
                  </motion.div>
                  
                  <motion.div 
                    initial={{ width: 0, height: 0, opacity: 0 }}
                    whileInView={{ width: "25%", height: "40%", opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.8, type: "spring" }}
                    className="absolute top-[40%] right-[15%] border-2 border-indigo-400 bg-indigo-400/10 z-10 flex items-start"
                  >
                    <span className="bg-indigo-400 text-black text-[10px] font-bold px-2 py-0.5">Pedestrian 0.92</span>
                  </motion.div>
                  
                  {/* Scanner line over demo */}
                  <motion.div 
                    animate={{ left: ["0%", "100%", "0%"] }}
                    transition={{ duration: 4, ease: "linear", repeat: Infinity }}
                    className="absolute top-0 bottom-0 w-px bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.8)] z-20"
                  />
                </SpotlightCard>
              </div>
            </div>
          </div>
        </section>

        {/* Features Bento Grid */}
        <section id="features" className="container mx-auto px-6 py-32 relative z-20">
          <motion.div 
            initial={{ y: 40, opacity: 0 }}
            whileInView={{ y: 0, opacity: 1 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8 }}
            className="text-center mb-20"
          >
            <h2 className="text-4xl md:text-6xl font-bold mb-6 tracking-tight">Intelligence at Scale</h2>
            <p className="text-gray-400 max-w-2xl mx-auto text-lg md:text-xl font-light">
              A comprehensive toolkit engineered for high-performance AI. From raw pixels to deployed endpoints in minutes.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-7xl mx-auto">
            {features.map((feature, idx) => (
              <SpotlightCard 
                key={idx} 
                className={cn(
                  "p-8 md:p-10 flex flex-col justify-between",
                  idx === 0 ? "md:col-span-2 aspect-[2/1]" : 
                  idx === 1 ? "md:row-span-2 aspect-[1/2]" : 
                  "aspect-square"
                )}
              >
                <div className="absolute -bottom-10 -right-10 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity duration-500 transform group-hover:scale-110 pointer-events-none">
                  <feature.icon className="w-64 h-64" />
                </div>
                
                <div className="relative z-10">
                  <div className={cn("w-14 h-14 rounded-2xl flex items-center justify-center mb-8 shadow-lg", `bg-gradient-to-br ${feature.color} bg-opacity-10`)}>
                    <feature.icon className="text-white w-6 h-6" />
                  </div>
                  <h3 className="text-2xl font-bold mb-4 text-white tracking-tight">{feature.title}</h3>
                  <p className="text-gray-400 leading-relaxed font-light">{feature.description}</p>
                </div>
                
                {idx === 0 && (
                  <div className="mt-8 flex gap-3 opacity-50 group-hover:opacity-100 transition-opacity">
                     <div className="h-2 w-16 bg-blue-500/50 rounded-full" />
                     <div className="h-2 w-24 bg-blue-400/30 rounded-full" />
                     <div className="h-2 w-12 bg-blue-300/20 rounded-full" />
                  </div>
                )}
                {idx === 2 && (
                  <div className="mt-8 bg-black/50 border border-white/5 rounded-lg p-3 font-mono text-xs text-emerald-400">
                    $ nebula train --model yolov8n
                  </div>
                )}
              </SpotlightCard>
            ))}
          </div>
        </section>

        {/* Workflow Section */}
        <section id="workflow" className="py-32 relative overflow-hidden">
          <div className="absolute inset-0 bg-zinc-950" />
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#4f46e51a_1px,transparent_1px),linear-gradient(to_bottom,#4f46e51a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20" />
          
          <div className="container mx-auto px-6 relative z-10">
            <motion.div 
              initial={{ y: 40, opacity: 0 }}
              whileInView={{ y: 0, opacity: 1 }}
              viewport={{ once: true }}
              className="text-center mb-24"
            >
              <h2 className="text-4xl md:text-6xl font-bold mb-6 tracking-tight">Pipeline Velocity</h2>
              <p className="text-gray-400 max-w-2xl mx-auto text-lg md:text-xl font-light">Experience a fluid, uninterrupted workflow optimized for speed.</p>
            </motion.div>

            <div className="relative max-w-6xl mx-auto">
              <div className="hidden md:block absolute top-[50%] left-0 w-full h-[1px] bg-white/10 -translate-y-1/2">
                <motion.div 
                  initial={{ left: "-100%" }}
                  animate={{ left: "100%" }}
                  transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                  className="absolute top-[-1px] w-64 h-[3px] bg-gradient-to-r from-transparent via-indigo-500 to-transparent shadow-[0_0_15px_rgba(99,102,241,0.8)]"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-12 md:gap-8">
                {[
                  { step: "01", title: "Ingest", desc: "Raw data to curated dataset", icon: Database, shadow: "shadow-blue-500/20" },
                  { step: "02", title: "Annotate", desc: "Auto-label with foundation models", icon: ImageIcon, shadow: "shadow-purple-500/20" },
                  { step: "03", title: "Train", desc: "Distributed GPU training", icon: Cpu, shadow: "shadow-emerald-500/20" },
                  { step: "04", title: "Deploy", desc: "Scalable inference APIs", icon: Activity, shadow: "shadow-amber-500/20" },
                ].map((item, i) => (
                  <motion.div 
                    key={i}
                    initial={{ y: 50, opacity: 0 }}
                    whileInView={{ y: 0, opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.2, duration: 0.6 }}
                    className="relative group"
                  >
                    <div className={cn("w-full aspect-square rounded-3xl bg-zinc-900 border border-white/5 p-8 flex flex-col items-center justify-center text-center transition-all duration-500 hover:-translate-y-4 hover:border-white/20 bg-clip-padding backdrop-filter backdrop-blur-xl shadow-xl", `hover:${item.shadow}`)}>
                      <div className="absolute -top-4 -left-4 w-8 h-8 rounded-full bg-black border border-white/10 flex items-center justify-center text-xs font-mono font-bold text-gray-400 z-20 group-hover:text-white transition-colors">
                        {item.step}
                      </div>
                      
                      <div className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6 bg-black border border-white/5 relative group-hover:scale-110 transition-transform duration-500">
                        <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                        <item.icon className="w-8 h-8 text-gray-300 group-hover:text-white transition-colors" />
                      </div>

                      <h3 className="text-xl font-bold mb-3 text-white">{item.title}</h3>
                      <p className="text-sm text-gray-400 font-light">{item.desc}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Integrations & Export Targets */}
        <section className="py-24 border-t border-white/5 relative overflow-hidden bg-black">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(99,102,241,0.05),transparent_70%)]" />
          <div className="container mx-auto px-6 relative z-10">
            <div className="text-center mb-16">
              <p className="text-sm font-semibold tracking-widest text-indigo-400 uppercase mb-4">Export Anywhere</p>
              <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Deploy to Any Architecture</h2>
            </div>
            <div className="flex flex-wrap justify-center items-center gap-8 md:gap-16 opacity-60 hover:opacity-100 transition-opacity duration-700">
              {["PyTorch", "ONNX", "TensorRT", "CoreML", "TFLite", "OpenVINO"].map((target, idx) => (
                <motion.div 
                  key={idx}
                  whileHover={{ scale: 1.1, opacity: 1 }}
                  className="text-2xl md:text-4xl font-black tracking-tighter text-gray-500 hover:text-white transition-colors cursor-default"
                >
                  {target}
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section id="stats-section" className="py-32 relative overflow-hidden border-t border-white/5 bg-black">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(79,70,229,0.1),transparent_50%)]"></div>
          <div className="container mx-auto px-6 relative z-10">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-12 max-w-6xl mx-auto">
              {statsList.map((stat, i) => (
                <motion.div 
                  key={i} 
                  initial={{ scale: 0.9, opacity: 0 }}
                  whileInView={{ scale: 1, opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1, duration: 0.5 }}
                  className="text-center group"
                >
                  <div className="text-5xl md:text-7xl font-black mb-4 bg-gradient-to-b from-white to-white/30 bg-clip-text text-transparent tracking-tighter drop-shadow-sm">
                    {stat.value}
                  </div>
                  <div className="flex items-center justify-center gap-2 text-gray-400">
                    <stat.icon className="w-4 h-4 text-indigo-400" />
                    <span className="text-sm font-medium tracking-wide">{stat.label}</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing Section */}
        <section id="pricing" className="py-32 relative overflow-hidden bg-black border-t border-white/5">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,rgba(99,102,241,0.05),transparent_60%)]" />
          <div className="container mx-auto px-6 relative z-10">
            <motion.div 
              initial={{ y: 40, opacity: 0 }}
              whileInView={{ y: 0, opacity: 1 }}
              viewport={{ once: true }}
              className="text-center mb-20"
            >
              <h2 className="text-4xl md:text-6xl font-bold mb-4 tracking-tight">Simple, Transparent Pricing</h2>
              <p className="text-gray-400 max-w-2xl mx-auto text-lg md:text-xl font-light">Scale your vision without the surprise bills.</p>
            </motion.div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto">
              {[
                { name: "Starter", price: "Free", desc: "For personal projects and exploration.", features: ["3 Projects", "10,000 Annotations", "Community Support", "Basic Models"], button: "Start Free", popular: false },
                { name: "Pro", price: "$49", period: "/mo", desc: "For professionals building serious ML.", features: ["Unlimited Projects", "100,000 Annotations", "Priority Support", "Advanced Foundation Models", "Custom Exports"], button: "Get Pro", popular: true },
                { name: "Enterprise", price: "Custom", desc: "For teams deploying at massive scale.", features: ["Unlimited Everything", "Dedicated Account Manager", "On-Premises Options", "SLA Guarantees", "Custom Model Integration"], button: "Contact Sales", popular: false }
              ].map((tier, i) => (
                <motion.div 
                  key={i}
                  initial={{ y: 50, opacity: 0 }}
                  whileInView={{ y: 0, opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1, duration: 0.5 }}
                  className={cn("relative p-8 rounded-3xl border flex flex-col h-full bg-zinc-950 transition-all", tier.popular ? "border-indigo-500 shadow-[0_0_30px_rgba(99,102,241,0.15)] scale-[1.02] md:scale-105 z-10" : "border-white/10 hover:border-white/20")}
                >
                  {tier.popular && (
                    <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                      <span className="bg-indigo-500 text-white text-xs font-bold uppercase tracking-wider py-1 px-4 rounded-full shadow-lg">Most Popular</span>
                    </div>
                  )}
                  <h3 className="text-2xl font-bold mb-2">{tier.name}</h3>
                  <p className="text-gray-400 text-sm mb-6 h-10">{tier.desc}</p>
                  <div className="mb-8">
                    <span className="text-5xl font-black">{tier.price}</span>
                    {tier.period && <span className="text-gray-400">{tier.period}</span>}
                  </div>
                  <ul className="space-y-4 mb-8 flex-1">
                    {tier.features.map((feature, fIdx) => (
                      <li key={fIdx} className="flex items-center gap-3 text-gray-300">
                        <CheckCircle className="w-5 h-5 text-indigo-400 shrink-0" />
                        <span className="font-light">{feature}</span>
                      </li>
                    ))}
                  </ul>
                  <Button 
                    className={cn("w-full h-12 rounded-xl font-semibold transition-all", tier.popular ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40" : "bg-white/5 hover:bg-white/10 text-white border border-white/10")}
                  >
                    {tier.button}
                  </Button>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="py-32 border-t border-white/5 relative bg-zinc-950">
          <div className="container mx-auto px-6 max-w-4xl relative z-10">
            <motion.div 
              initial={{ y: 40, opacity: 0 }}
              whileInView={{ y: 0, opacity: 1 }}
              viewport={{ once: true }}
              className="text-center mb-16"
            >
              <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">Frequently Asked Questions</h2>
              <p className="text-gray-400 font-light">Everything you need to know about the platform.</p>
            </motion.div>
            
            <div className="space-y-2">
              <FAQItem 
                question="What models does NebulaML support?" 
                answer="We currently provide native, zero-config support for the entire Ultralytics YOLO ecosystem (v8, v9, v10, v11) for object detection, segmentation, and classification." 
              />
              <FAQItem 
                question="Can I export my datasets and models?" 
                answer="Yes. You maintain full ownership of your data. Datasets can be exported in standard YOLO format at any time. Trained models can be downloaded as PyTorch weights (.pt) or exported to ONNX, TensorRT, and CoreML." 
              />
              <FAQItem 
                question="How does the auto-annotation work?" 
                answer="We integrate with advanced foundation models to automatically propose bounding boxes and segmentation masks for your uploaded images, which you can quickly accept or adjust." 
              />
              <FAQItem 
                question="Do I need my own GPU?" 
                answer="No. Our distributed infrastructure handles all the training workload. You just click 'Train' and we provision the necessary A100/H100 instances behind the scenes." 
              />
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-32 relative border-t border-white/5">
          <div className="container mx-auto px-6">
            <SpotlightCard className="max-w-5xl mx-auto p-12 md:p-24 text-center border border-indigo-500/20 bg-zinc-950/80 backdrop-blur-2xl">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(99,102,241,0.1),transparent_80%)] animate-pulse-glow" />
              
              <div className="relative z-10">
                <h2 className="text-4xl md:text-6xl font-black mb-6 tracking-tight text-white">Deploy Intelligence Today.</h2>
                <p className="text-gray-400 max-w-xl mx-auto mb-10 text-xl font-light">
                  Join the next generation of AI development. Create your free account and train your first model in minutes.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <Button
                    size="lg"
                    onClick={() => router.push(user ? '/dashboard' : '/register')}
                    className="h-14 px-10 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-[0_0_40px_rgba(99,102,241,0.4)] transition-all hover:scale-105 hover:shadow-[0_0_60px_rgba(99,102,241,0.6)]"
                  >
                    Start Free Trial
                    <ArrowRight className="ml-2 w-5 h-5" />
                  </Button>
                </div>
              </div>
            </SpotlightCard>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-white/5 pt-16 pb-8 bg-black relative">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1/2 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          <div className="container mx-auto px-6">
            <div className="flex flex-col md:flex-row justify-between items-center gap-8 mb-12">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.3)]">
                  <Zap className="text-white drop-shadow-md" />
                </div>
                <span className="font-bold text-xl tracking-tight text-white">Nebula</span>
              </div>
              
              <div className="flex items-center gap-6">
                {['Product', 'Documentation', 'Pricing', 'Blog'].map(link => (
                  <a key={link} href="#" className="text-sm text-gray-400 hover:text-white transition-colors">{link}</a>
                ))}
              </div>

              <div className="flex items-center gap-4">
                {[Github, Twitter, Mail].map((Icon, i) => (
                  <a key={i} href="#" className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-gray-400 hover:text-white hover:bg-white/10 transition-all hover:scale-110">
                    <Icon size={18} />
                  </a>
                ))}
              </div>
            </div>
            
            <div className="flex flex-col md:flex-row justify-between items-center gap-4 pt-8 border-t border-white/5 text-xs text-gray-500">
              <p>&copy; {new Date().getFullYear()} Nebula ML, Inc. All rights reserved.</p>
              <div className="flex gap-4">
                <a href="#" className="hover:text-gray-300">Privacy Policy</a>
                <a href="#" className="hover:text-gray-300">Terms of Service</a>
              </div>
            </div>
          </div>
        </footer>
      </main>
      
      {/* Global CSS for custom animations */}
      <style dangerouslySetInnerHTML={{__html: `
        .preserve-3d { transform-style: preserve-3d; }
        .perspective-[2000px] { perspective: 2000px; }
        
        @keyframes scanline {
          0% { transform: translateY(0); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateY(300px); opacity: 0; }
        }
        .animate-scanline {
          animation: scanline 4s linear infinite;
        }
        
        @keyframes shine {
          100% { transform: translateX(150%) skew-x(-20deg); }
        }
        .animate-shine {
          animation: shine 2s ease-in-out infinite;
        }
        
        .animate-float-slow {
          animation: float 6s ease-in-out infinite;
        }
        
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }
        
        @keyframes pulse-glow {
          0%, 100% { opacity: 0.5; transform: scale(1); }
          50% { opacity: 0.8; transform: scale(1.05); }
        }
        .animate-pulse-glow {
          animation: pulse-glow 8s ease-in-out infinite;
        }
      `}} />
    </div>
  );
}
