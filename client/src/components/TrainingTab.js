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
  Zap, Terminal
} from "lucide-react";
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
  }, [jobId, status]);

  if (metrics.length === 0) return null;
  return (
    <div className="h-48 w-full mt-3 bg-black/20 rounded-xl p-3 border border-white/5">
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
    <div className="text-center p-2 rounded-lg bg-white/[0.03] border border-white/5">
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

// ─────────────────────────────────────────────────────────────────────────────
export default function TrainingTab() {
  const { token } = useAuth();
  const [config, setConfig] = useState({
    model_name: "yolov8n.pt",
    epochs: 50,
    batch_size: 16,
    img_size: 640,
    dataset_yaml: null,
    dataset_yaml_name: "",
  });
  const [jobs, setJobs] = useState([]);
  const [models, setModels] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [expandedLogs, setExpandedLogs] = useState({});

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

  // ── Fetch models ────────────────────────────────────────────────────────────
  const fetchModels = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(API_ENDPOINTS.MODELS.LIST, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setModels(d.models || []);
      }
    } catch (_) {}
  }, [token]);

  useEffect(() => {
    fetchJobs();
    fetchModels();
    const jt = setInterval(fetchJobs, 5000);
    const mt = setInterval(fetchModels, 10000);
    return () => { clearInterval(jt); clearInterval(mt); };
  }, [token]);

  // ── Start training ──────────────────────────────────────────────────────────
  const handleStart = async () => {
    if (!config.dataset_yaml) { toast.error("Upload a dataset YAML first"); return; }
    setSubmitting(true);
    const fd = new FormData();
    fd.append("dataset_yaml", config.dataset_yaml);
    fd.append("model_name", config.model_name);
    fd.append("epochs", config.epochs);
    fd.append("batch_size", config.batch_size);
    fd.append("img_size", config.img_size);
    try {
      const res = await fetch(API_ENDPOINTS.TRAINING.START, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      const d = await res.json();
      if (res.ok) { toast.success(`Training started — Job ${d.job_id}`); fetchJobs(); }
      else toast.error(d.detail || "Failed to start");
    } catch (e) { toast.error(e.message); }
    finally { setSubmitting(false); }
  };

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

  // ── Download model ──────────────────────────────────────────────────────────
  const handleDownload = async (name) => {
    try {
      const res = await fetch(API_ENDPOINTS.MODELS.DOWNLOAD(name), {
        headers: { Authorization: `Bearer ${token}` },
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${name}_best.pt`;
      document.body.appendChild(a); a.click();
      URL.revokeObjectURL(url); a.remove();
      toast.success(`Downloading ${name}…`);
    } catch (e) { toast.error("Download failed"); }
  };

  // ── Delete model ────────────────────────────────────────────────────────────
  const handleDeleteModel = async (name) => {
    if (!confirm(`Delete model "${name}"?`)) return;
    try {
      const res = await fetch(API_ENDPOINTS.MODELS.DELETE(name), {
        method: "DELETE", headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) { toast.success("Deleted"); fetchModels(); }
      else toast.error("Delete failed");
    } catch (e) { toast.error(e.message); }
  };

  const activeJobs  = jobs.filter(j => j.status === "running" || j.status === "pending");
  const finishedJobs = jobs.filter(j => j.status !== "running" && j.status !== "pending");

  return (
    <div className="space-y-10 animate-fade-in text-gray-100">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">
            Training
          </h2>
          <p className="text-muted-foreground mt-1">Configure runs, monitor progress, and manage trained models.</p>
        </div>
        <Button onClick={() => { fetchJobs(); fetchModels(); }} variant="outline" size="sm"
          className="border-white/10 bg-white/5 hover:bg-white/10">
          <RefreshCw className="mr-2 w-3.5 h-3.5" /> Refresh
        </Button>
      </div>

      {/* ── Layout: Config | Jobs+Models ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Config panel */}
        <div className="space-y-4 bg-card/40 border border-white/5 rounded-2xl p-5">
          <h3 className="font-semibold text-white flex items-center gap-2 text-sm">
            <Cpu className="w-4 h-4 text-indigo-400" /> New Training Run
          </h3>

          {/* YAML upload */}
          <div className="space-y-1.5">
            <Label className="text-xs text-gray-400">Dataset Config (YAML)</Label>
            <div onClick={() => document.getElementById("yaml-up")?.click()}
              className="border-2 border-dashed border-white/10 rounded-xl p-4 text-center cursor-pointer hover:border-indigo-500/40 hover:bg-white/[0.02] transition-all">
              <Upload className="mx-auto w-5 h-5 text-gray-500 mb-1" />
              <p className="text-xs text-gray-400">{config.dataset_yaml_name || "Click to upload .yaml"}</p>
              <input id="yaml-up" type="file" accept=".yaml,.yml" className="hidden"
                onChange={e => {
                  const f = e.target.files[0];
                  if (f) setConfig({ ...config, dataset_yaml: f, dataset_yaml_name: f.name });
                }} />
            </div>
          </div>

          {/* Model */}
          <div className="space-y-1.5">
            <Label className="text-xs text-gray-400">Model</Label>
            <Select value={config.model_name} onValueChange={v => setConfig({ ...config, model_name: v })}>
              <SelectTrigger className="bg-black/30 border-white/10 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="yolov8n.pt">YOLOv8 Nano — fastest</SelectItem>
                <SelectItem value="yolov8s.pt">YOLOv8 Small</SelectItem>
                <SelectItem value="yolov8m.pt">YOLOv8 Medium</SelectItem>
                <SelectItem value="yolov8l.pt">YOLOv8 Large</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Hyperparams */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: "Epochs",  key: "epochs",     min: 1  },
              { label: "Batch",   key: "batch_size", min: 1  },
            ].map(({ label, key, min }) => (
              <div key={key} className="col-span-1 space-y-1.5">
                <Label className="text-xs text-gray-400">{label}</Label>
                <Input type="number" value={config[key]} min={min}
                  onChange={e => setConfig({ ...config, [key]: parseInt(e.target.value) || min })}
                  className="bg-black/30 border-white/10 text-sm" />
              </div>
            ))}
            <div className="col-span-1 space-y-1.5">
              <Label className="text-xs text-gray-400">Img Size</Label>
              <Select value={config.img_size.toString()} onValueChange={v => setConfig({ ...config, img_size: +v })}>
                <SelectTrigger className="bg-black/30 border-white/10 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="416">416</SelectItem>
                  <SelectItem value="640">640</SelectItem>
                  <SelectItem value="1024">1024</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button onClick={handleStart} disabled={submitting || !config.dataset_yaml}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white">
            {submitting ? <Loader2 className="animate-spin mr-2 w-4 h-4" /> : <Play className="mr-2 w-4 h-4" />}
            {submitting ? "Starting…" : "Start Training"}
          </Button>
        </div>

        {/* Right: Active + Finished jobs + Models */}
        <div className="lg:col-span-2 space-y-8">

          {/* ── Active Runs ─────────────────────────────────────────────────── */}
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400 animate-pulse" />
              <span className="text-sm font-semibold text-blue-400">
                Active Runs {activeJobs.length > 0 && `(${activeJobs.length})`}
              </span>
            </div>

            {activeJobs.length === 0 ? (
              <div className="py-10 text-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] text-sm text-gray-500">
                No active runs. Start a training run to see live progress here.
              </div>
            ) : activeJobs.map(job => (
              <div key={job.job_id}
                className="rounded-2xl border border-blue-500/30 bg-blue-500/[0.04] overflow-hidden shadow-[0_0_20px_rgba(59,130,246,0.06)]">
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
                    <Button onClick={() => handleStop(job.job_id)} variant="ghost" size="sm"
                      className="text-red-400 hover:bg-red-400/10 h-8 px-2">
                      <Square className="w-3.5 h-3.5 mr-1" /> Stop
                    </Button>
                  </div>
                </div>

                <div className="p-4 space-y-3">
                  {/* Progress bar */}
                  <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-blue-600 to-blue-400 transition-all duration-500"
                      style={{ width: `${Math.max(2, job.progress || 0)}%` }} />
                  </div>

                  {/* Live metrics */}
                  {job.metrics && Object.keys(job.metrics).length > 0 && (
                    <div className="grid grid-cols-3 gap-2">
                      {job.metrics.loss != null && (
                        <Pill label="Box Loss" value={Number(job.metrics.loss).toFixed(4)} color="text-amber-400" />
                      )}
                      {(job.metrics.mAP50 ?? job.metrics.map50) != null && (
                        <Pill label="mAP@50" value={Number(job.metrics.mAP50 ?? job.metrics.map50).toFixed(3)} color="text-emerald-400" />
                      )}
                      {job.metrics.epoch != null && (
                        <Pill label="Epoch" value={formatMetricValue(job.metrics.epoch)} color="text-blue-400" />
                      )}
                    </div>
                  )}

                  <JobChart jobId={job.job_id} status={job.status} />
                  <GamifiedTerminal output={job.output} isRunning={job.status === "running"} />
                </div>
              </div>
            ))}
          </section>

          {/* ── Trained Models ──────────────────────────────────────────────── */}
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Box className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-semibold text-emerald-400">
                Trained Models {models.length > 0 && `(${models.length})`}
              </span>
            </div>

            {models.length === 0 ? (
              <div className="py-10 text-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] text-sm text-gray-500">
                No trained models yet. Completed training runs will appear here.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {models.map((model, i) => (
                  <div key={i}
                    className="group rounded-2xl bg-card/40 border border-white/5 hover:border-emerald-500/30 hover:bg-white/5 transition-all duration-300 flex flex-col overflow-hidden">
                    <div className="p-5 flex-1">
                      <div className="flex items-start justify-between mb-4">
                        <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-400 group-hover:bg-emerald-500/20 transition-all">
                          <Box className="w-5 h-5" />
                        </div>
                        <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-xs">Ready</Badge>
                      </div>
                      <h3 className="font-bold text-white truncate mb-1" title={model.name}>{model.name}</h3>
                      <div className="space-y-2 mt-3 text-sm text-gray-400">
                        <div className="flex justify-between">
                          <div className="flex items-center gap-1.5"><HardDrive className="w-3.5 h-3.5 text-gray-500" /> Size</div>
                          <span className="text-gray-200 font-mono text-xs">{fmtBytes(model.size)}</span>
                        </div>
                        <div className="flex justify-between">
                          <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-gray-500" /> Created</div>
                          <span className="text-gray-200 text-xs">{new Date(model.created * 1000).toLocaleDateString()}</span>
                        </div>
                        {model.metrics?.mAP50 != null && (
                          <div className="flex justify-between">
                            <div className="flex items-center gap-1.5"><TrendingUp className="w-3.5 h-3.5 text-gray-500" /> mAP@50</div>
                            <span className="text-emerald-400 font-mono text-xs font-semibold">
                              {Number(model.metrics.mAP50).toFixed(3)}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="p-3 bg-white/[0.02] border-t border-white/5 flex gap-2">
                      <Button onClick={() => handleDownload(model.name)} size="sm"
                        className="flex-1 bg-white text-black hover:bg-gray-200 text-xs h-8">
                        <Download className="w-3.5 h-3.5 mr-1.5" /> Download .pt
                      </Button>
                      <Button onClick={() => handleDeleteModel(model.name)} variant="ghost" size="icon"
                        className="text-gray-400 hover:text-red-400 hover:bg-red-400/10 h-8 w-8">
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Finished Job History ─────────────────────────────────────────── */}
          {finishedJobs.length > 0 && (
            <section className="space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Run History</p>
              <div className="space-y-2">
                {finishedJobs.map((job, i) => {
                  const open = expandedLogs[job.job_id];
                  return (
                    <div key={job.job_id || i}
                      className="rounded-xl border border-white/5 bg-card/30 overflow-hidden">
                      <button className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors"
                        onClick={() => setExpandedLogs(p => ({ ...p, [job.job_id]: !p[job.job_id] }))}>
                        <div className="flex items-center gap-3">
                          <StatusBadge status={job.status} />
                          <div className="text-left">
                            <p className="text-sm font-medium">{job.config?.model_name || "yolov8n"}</p>
                            <p className="text-xs text-gray-500">{job.config?.epochs} epochs · batch {job.config?.batch_size}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          {(job.metrics?.mAP50 ?? job.metrics?.map50) != null && (
                            <span className="text-xs font-mono text-emerald-400">
                              mAP {Number(job.metrics.mAP50 ?? job.metrics.map50).toFixed(3)}
                            </span>
                          )}
                          {open ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
                        </div>
                      </button>
                      {open && (
                        <div className="border-t border-white/5">
                          {job.metrics && (
                            <div className="grid grid-cols-3 gap-2 p-4">
                              {job.metrics.loss != null && <Pill label="Loss" value={Number(job.metrics.loss).toFixed(4)} color="text-amber-400" />}
                              {(job.metrics.mAP50 ?? job.metrics.map50) != null && <Pill label="mAP@50" value={Number(job.metrics.mAP50 ?? job.metrics.map50).toFixed(3)} color="text-emerald-400" />}
                              {job.metrics.epoch != null && <Pill label="Epoch" value={formatMetricValue(job.metrics.epoch)} color="text-blue-400" />}
                            </div>
                          )}
                          <JobChart jobId={job.job_id} status={job.status} />
                          <GamifiedTerminal output={job.output} isRunning={false} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
