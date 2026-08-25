"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn, formatMetricValue } from "@/lib/utils";
import { toast } from "sonner";
import {
  Upload, Play, Square, RefreshCw, CheckCircle, XCircle,
  Clock, Cpu, Activity, Loader2, Download, Trash2,
  Box, HardDrive, TrendingUp, ChevronDown, ChevronUp,
  Zap, Terminal, Plus
} from "lucide-react";
import { useRouter } from "next/navigation";
import GamifiedTerminal from "./GamifiedTerminal";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

// ── Mini chart for a single job ───────────────────────────────────────────────
function JobChart({ jobId, status }) {
  const { token } = useAuth();
  const [metrics, setMetrics] = useState([]);

  const fetch_ = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(API_ENDPOINTS.TRAINING.JOB_METRICS(jobId), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        if (d.metrics) setMetrics(d.metrics);
      }
    } catch (_) {}
  }, [jobId, token]);

  useEffect(() => {
    fetch_();
    if (status === "running") {
      const t = setInterval(fetch_, 3000);
      return () => clearInterval(t);
    }
  }, [jobId, status, fetch_]);

  if (metrics.length === 0) return null;
  return (
    <div className="h-48 w-full mt-3 bg-black/20 rounded-none p-3 border border-white/5">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={metrics}>
          <CartesianGrid strokeDasharray="3 3" stroke="#222" />
          <XAxis dataKey="epoch" stroke="#555" fontSize={10} tickFormatter={v => `E${v}`} />
          <YAxis stroke="#555" fontSize={10} />
          <Tooltip contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 11 }} />
          <Line type="monotone" dataKey="train/box_loss" stroke="#f59e0b" dot={false} strokeWidth={2} name="Box Loss" />
          <Line type="monotone" dataKey="metrics/mAP50(B)" stroke="#10b981" dot={false} strokeWidth={2} name="mAP@50" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const map = {
    running:   { cls: "bg-blue-500/20 text-blue-400 border-blue-500/30",    icon: Clock,        label: "Running"   },
    completed: { cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", icon: CheckCircle, label: "Done"  },
    success:   { cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", icon: CheckCircle, label: "Done"  },
    cancelled: { cls: "bg-amber-500/20 text-amber-400 border-amber-500/30",  icon: Square,       label: "Stopped"   },
    failed:    { cls: "bg-red-500/20 text-red-400 border-red-500/30",        icon: XCircle,      label: "Failed"    },
  };
  const cfg = map[status] || { cls: "bg-white/10 text-gray-400 border-white/10", icon: Clock, label: status };
  const Icon = cfg.icon;
  return (
    <Badge className={cn("gap-1 border text-xs", cfg.cls)}>
      <Icon className="w-3 h-3" /> {cfg.label}
    </Badge>
  );
}

// ── Metric pill ───────────────────────────────────────────────────────────────
function Pill({ label, value, color = "text-white" }) {
  return (
    <div className="text-center p-2 rounded-none bg-white/[0.03] border border-white/5">
      <p className="text-[10px] text-gray-500 uppercase mb-0.5">{label}</p>
      <p className={cn("text-sm font-mono font-semibold", color)}>{value}</p>
    </div>
  );
}

// ── Format bytes ──────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (!b) return "—";
  const i = Math.floor(Math.log(b) / Math.log(1024));
  return (b / Math.pow(1024, i)).toFixed(1) + " " + ["B","KB","MB","GB"][i];
}

// ── Job Details (Confusion Matrix & Per-Class Metrics) ────────────────────────
function JobDetails({ jobId, status }) {
  const { token } = useAuth();
  const [perClass, setPerClass] = useState([]);
  const [cmUrl, setCmUrl] = useState(null);

  useEffect(() => {
    if (status !== "completed" && status !== "success") return;
    
    // Fetch per-class metrics
    fetch(API_ENDPOINTS.TRAINING.PER_CLASS_METRICS(jobId), {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(d => {
        if (d.success && d.per_class_metrics) {
          setPerClass(d.per_class_metrics);
        }
      })
      .catch(() => {});
      
    // Fetch confusion matrix image blob
    fetch(API_ENDPOINTS.TRAINING.CONFUSION_MATRIX(jobId), {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.blob() : null)
      .then(blob => {
        if (blob) setCmUrl(URL.createObjectURL(blob));
      })
      .catch(() => {});
  }, [jobId, status, token]);

  if (status !== "completed" && status !== "success") return null;
  if (!perClass.length && !cmUrl) return null;

  return (
    <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4 px-4 pb-4">
      {cmUrl && (
        <div className="border border-white/5 bg-black/20 rounded-none p-3">
          <p className="text-xs font-semibold text-gray-400 mb-2 uppercase">Confusion Matrix</p>
          <img src={cmUrl} alt="Confusion Matrix" className="w-full h-auto rounded-none" />
        </div>
      )}
      {perClass.length > 0 && (
        <div className="border border-white/5 bg-black/20 rounded-none p-3 overflow-hidden flex flex-col">
          <p className="text-xs font-semibold text-gray-400 mb-2 uppercase">Per-Class Metrics</p>
          <div className="overflow-auto custom-scrollbar flex-1 max-h-[300px]">
            <table className="w-full text-xs text-left">
              <thead className="text-gray-500 bg-white/[0.02] sticky top-0">
                <tr>
                  <th className="px-2 py-1.5 rounded-none">Class</th>
                  <th className="px-2 py-1.5">mAP@50</th>
                  <th className="px-2 py-1.5">mAP@50-95</th>
                  <th className="px-2 py-1.5">Precision</th>
                  <th className="px-2 py-1.5 rounded-none">Recall</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {perClass.map((c, i) => (
                  <tr key={i} className="hover:bg-white/[0.02]">
                    <td className="px-2 py-1.5 font-medium text-gray-300">{c.class_name}</td>
                    <td className="px-2 py-1.5 font-mono text-emerald-400">{Number(c.mAP50).toFixed(3)}</td>
                    <td className="px-2 py-1.5 font-mono text-cyan-400">{Number(c.mAP50_95).toFixed(3)}</td>
                    <td className="px-2 py-1.5 font-mono text-amber-400">{Number(c.precision).toFixed(3)}</td>
                    <td className="px-2 py-1.5 font-mono text-blue-400">{Number(c.recall).toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Live Job Tracker (SSE) ───────────────────────────────────────────────────
function LiveJobTracker({ initialJob, onStop }) {
  const { token } = useAuth();
  const [job, setJob] = useState(initialJob);

  useEffect(() => {
    if (!token) return;
    if (job.status !== "running" && job.status !== "pending") return;

    const controller = new AbortController();
    
    const streamData = async () => {
      try {
        const response = await fetch(API_ENDPOINTS.TRAINING.STREAM(job.job_id), {
          headers: { "Authorization": `Bearer ${token}` },
          signal: controller.signal
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop(); // keep the last incomplete chunk in buffer
          
          for (const part of parts) {
            if (part.startsWith('data: ')) {
              try {
                const data = JSON.parse(part.slice(6));
                setJob(data);
              } catch(e) {}
            }
          }
        }
      } catch(e) {
        if (e.name !== 'AbortError') console.error("Stream error:", e);
      }
    };
    
    streamData();
    return () => controller.abort();
  }, [job.job_id, token, job.status]);

  return (
    <div className="rounded-none border border-blue-500/30 bg-blue-500/[0.04] overflow-hidden shadow-none_0_20px_rgba(59,130,246,0.06)]">
      {/* Job header */}
      <div className="p-4 flex items-center justify-between border-b border-blue-500/10">
        <div className="flex items-center gap-3">
          <StatusBadge status={job.status} />
          <div>
            <p className="text-sm font-semibold">{job.config?.model_name || "yolov8n"}</p>
            <p className="text-xs text-muted-foreground font-mono">
              {job.config?.epochs} epochs · batch {job.config?.batch_size}
              {job.current_epoch != null && ` · epoch ${job.current_epoch}/${job.config?.epochs}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-2xl font-black font-mono text-blue-400 tabular-nums">
            {Math.round(job.progress || 0)}%
          </span>
          <Button onClick={() => onStop(job.job_id)} variant="ghost" size="sm"
            className="text-red-400 hover:bg-red-400/10 h-8 px-2">
            <Square className="w-3.5 h-3.5 mr-1" /> Stop
          </Button>
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Progress bar */}
        <div className="h-2.5 rounded-none bg-white/5 overflow-hidden">
          <div className="h-full rounded-none    transition-all duration-500"
            style={{ width: `${Math.max(2, job.progress || 0)}%` }} />
        </div>

        {/* Live metrics */}
        {job.metrics && Object.keys(job.metrics).length > 0 && (
          <div className="grid grid-cols-4 gap-2">
            {(job.metrics.map50 ?? job.metrics.mAP50) != null && (
              <Pill label="mAP@50" value={Number(job.metrics.map50 ?? job.metrics.mAP50).toFixed(3)} color="text-emerald-400" />
            )}
            {(job.metrics["map50-95"] ?? job.metrics.mAP50_95) != null && (
              <Pill label="mAP@50-95" value={Number(job.metrics["map50-95"] ?? job.metrics.mAP50_95).toFixed(3)} color="text-cyan-400" />
            )}
            {(job.metrics.precision) != null && (
              <Pill label="Precision" value={Number(job.metrics.precision).toFixed(3)} color="text-amber-400" />
            )}
            {(job.metrics.recall) != null && (
              <Pill label="Recall" value={Number(job.metrics.recall).toFixed(3)} color="text-blue-400" />
            )}
          </div>
        )}

        <JobChart jobId={job.job_id} status={job.status} />
        <GamifiedTerminal output={job.output} isRunning={job.status === "running"} />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
export default function TrainingTab() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [expandedLogs, setExpandedLogs] = useState({});
  const router = useRouter();

  // ── Fetch jobs ──────────────────────────────────────────────────────────────
  const fetchJobs = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setJobs((d.jobs || []).reverse());
      }
    } catch (_) {}
  }, [token]);

  useEffect(() => {
    fetchJobs();
    const jt = setInterval(fetchJobs, 5000);
    return () => { clearInterval(jt); };
  }, [fetchJobs]);

  // ── Stop job ────────────────────────────────────────────────────────────────
  const handleStop = async (jobId) => {
    if (!confirm("Stop this training run?")) return;
    try {
      const res = await fetch(API_ENDPOINTS.TRAINING.CANCEL(jobId), {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { toast.success(d.message || "Stopped"); fetchJobs(); }
      else toast.error(d.detail || "Failed");
    } catch (e) { toast.error(e.message); }
  };

  const toggleLogs = (jid) => setExpandedLogs((prev) => ({ ...prev, [jid]: !prev[jid] }));

  return (
    <div className="space-y-8 animate-fade-in text-gray-100">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight    bg-clip-text text-transparent">Training Hub</h2>
          <p className="text-muted-foreground mt-1">Monitor and manage training jobs across all your projects.</p>
        </div>
        <Button 
          onClick={() => router.push("/dashboard")} 
          className="bg-violet-500 hover:bg-violet-400 shadow-none shadow-none"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Training (Go to Projects)
        </Button>
      </div>

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-semibold flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-400" /> Training Queue
          </h3>
          <Button variant="outline" size="sm" onClick={fetchJobs} className="h-8 bg-white/5 border-white/10 hover:bg-white/10">
            <RefreshCw className="w-3.5 h-3.5 mr-2" /> Refresh
          </Button>
        </div>

        <div className="space-y-4">
          {jobs.length === 0 ? (
            <div className="p-12 border border-white/5 bg-white/[0.02] rounded-none flex flex-col items-center justify-center text-center">
              <Cpu className="w-12 h-12 text-gray-600 mb-4" />
              <p className="text-gray-400 font-medium">No training jobs found.</p>
              <p className="text-sm text-gray-500 mt-1">Configure and start a job from within a project.</p>
            </div>
          ) : (
            jobs.map(job => (
              <div key={job.job_id} className="rounded-none border border-white/10 bg-black/40 overflow-hidden shadow-none backdrop-blur-md">
                {/* Job Header */}
                <div className="p-5 border-b border-white/5 flex flex-wrap items-center justify-between gap-4 bg-white/[0.02]">
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "w-10 h-10 rounded-none flex items-center justify-center shrink-0 border",
                      job.status === "running" ? "bg-blue-500/20 border-blue-500/30 text-blue-400" :
                      job.status === "completed" || job.status === "success" ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400" :
                      job.status === "cancelled" ? "bg-amber-500/20 border-amber-500/30 text-amber-400" :
                      "bg-red-500/20 border-red-500/30 text-red-400"
                    )}>
                      <Cpu className={cn("w-5 h-5", job.status === "running" && "animate-pulse")} />
                    </div>
                    <div>
                      <div className="flex items-center gap-3">
                        <h4 className="font-semibold text-gray-100">{job.config?.model_name || "YOLOv8 Model"}</h4>
                        <StatusBadge status={job.status} />
                      </div>
                      <p className="text-xs text-gray-500 mt-1 font-mono">{job.job_id}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-3">
                    {job.status === "running" && (
                      <Button variant="destructive" size="sm" onClick={() => handleStop(job.job_id)} className="h-8 shadow-none shadow-none">
                        <Square className="w-3.5 h-3.5 mr-2" /> Stop
                      </Button>
                    )}
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={() => toggleLogs(job.job_id)}
                      className="h-8 bg-white/5 border-white/10 hover:bg-white/10 text-gray-300"
                    >
                      <Terminal className="w-3.5 h-3.5 mr-2" />
                      {expandedLogs[job.job_id] ? "Hide Details" : "Details"}
                      {expandedLogs[job.job_id] ? <ChevronUp className="w-3.5 h-3.5 ml-2" /> : <ChevronDown className="w-3.5 h-3.5 ml-2" />}
                    </Button>
                  </div>
                </div>

                {/* Job Info Grid */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-white/5">
                  <Pill label="Epochs" value={`${job.current_epoch || 0} / ${job.config?.epochs || 0}`} />
                  <Pill label="Batch Size" value={job.config?.batch_size || "—"} />
                  <Pill label="Img Size" value={job.config?.img_size || "—"} />
                  <Pill label="mAP@50" value={formatMetricValue(job.results?.map50)} color="text-emerald-400" />
                  <Pill label="Duration" value={`${job.duration_seconds ? Math.floor(job.duration_seconds/60) + "m" : "—"}`} />
                </div>

                {/* Expanded Content: Chart + Logs + Details */}
                {expandedLogs[job.job_id] && (
                  <div className="p-4 border-t border-white/5 bg-[#0a0a0a]">
                    {job.status === "running" ? (
                      <LiveJobTracker initialJob={job} onStop={handleStop} />
                    ) : (
                      <>
                        <div className="mb-4">
                          <JobChart jobId={job.job_id} status={job.status} />
                        </div>
                        
                        {(job.status === "completed" || job.status === "success") && (
                          <div className="mb-4 border-t border-white/5 pt-4">
                              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-emerald-400"/> Detailed Evaluation</h4>
                              <JobDetails jobId={job.job_id} status={job.status} />
                          </div>
                        )}
                        
                        <div className="mt-4">
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2 flex items-center gap-2">
                            <Terminal className="w-3.5 h-3.5" /> Output Stream
                          </h4>
                          <div className="rounded-none overflow-hidden border border-white/10 shadow-none">
                              <GamifiedTerminal output={job.output} isRunning={job.status === "running"} />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
