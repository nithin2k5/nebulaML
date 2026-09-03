"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { API_ENDPOINTS } from "@/lib/config";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Upload, Play, Download, X, Maximize2, AlertCircle, CheckCircle2,
  Loader2, RefreshCw, Image as ImageIcon, Cpu, ChevronDown, Target,
  Zap, BarChart2, Eye, Trash2, FlaskConical, SlidersHorizontal, ArrowLeft
} from "lucide-react";

// ── helpers ──────────────────────────────────────────────────────────────────

const CLASS_PALETTE = [
  "#6366f1","#f59e0b","#10b981","#ef4444","#3b82f6",
  "#8b5cf6","#f97316","#14b8a6","#ec4899","#84cc16",
];
function classColor(idx) { return CLASS_PALETTE[idx % CLASS_PALETTE.length]; }

function StatPill({ label, value, color = "indigo" }) {
  const colorMap = {
    indigo: "bg-violet-400/15 text-indigo-300 border-violet-500/30",
    emerald: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    amber:  "bg-amber-500/15  text-amber-300  border-amber-500/30",
    violet: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  };
  return (
    <div className={`flex flex-col items-center px-4 py-3 rounded-none border ${colorMap[color]}`}>
      <span className="text-xl font-bold tabular-nums">{value}</span>
      <span className="text-[10px] uppercase tracking-wider mt-0.5 opacity-70">{label}</span>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function ProjectTest({ dataset }) {
  const { token } = useAuth();
  const [models, setModels]               = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [modelOpen, setModelOpen]         = useState(false);
  const [testImages, setTestImages]       = useState([]);
  const [loading, setLoading]             = useState(false);
  const [batchProgress, setBatchProgress] = useState(0); // 0-100
  const [uploading, setUploading]         = useState(false);
  const [selectedResult, setSelectedResult] = useState(null);
  const [confidence, setConfidence]       = useState(0.25);
  const [iou, setIou]                     = useState(0.45);
  const [dragging, setDragging]           = useState(false);
  const canvasRef   = useRef(null);
  const fileInputRef = useRef(null);
  const dropRef     = useRef(null);

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      setTestImages(current => {
        current.forEach(img => URL.revokeObjectURL(img.url));
        return [];
      });
    };
  }, []);

  useEffect(() => { fetchModels(); }, []);

  // ── close model dropdown on outside click ──
  useEffect(() => {
    if (!modelOpen) return;
    const handler = (e) => {
      if (!e.target.closest("[data-model-selector]")) setModelOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelOpen]);

  // ── fetch models ──
  const fetchModels = async () => {
    try {
      const [modelsRes, jobsRes] = await Promise.all([
        fetch(API_ENDPOINTS.MODELS.LIST, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(API_ENDPOINTS.TRAINING.JOBS, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (!modelsRes.ok) throw new Error("Failed to fetch models");

      const modelsData = await modelsRes.json();
      const allModels  = modelsData.models || [];

      let datasetJobIds = new Set();
      if (jobsRes.ok) {
        const jobsData = await jobsRes.json();
        (jobsData.jobs || []).forEach(j => {
          if (
            j.dataset_id === dataset.id &&
            (j.status === "completed" || j.status === "success" || j.status === "cancelled")
          ) {
            datasetJobIds.add(`job_${j.job_id}`);
          }
        });
      }

      const datasetModels = datasetJobIds.size > 0
        ? allModels.filter(m => datasetJobIds.has(m.name))
        : allModels;

      setModels(datasetModels);
      if (datasetModels.length > 0) setSelectedModel(datasetModels[0].name);
    } catch (error) {
      console.error(error);
      toast.error("Failed to load models");
    }
  };

  // ── file handling ──
  const processFiles = useCallback(async (files) => {
    const valid = Array.from(files).filter(f => f.type.startsWith("image/"));
    if (!valid.length) return;
    setUploading(true);
    const newImages = valid.map(file => ({
      id: Math.random().toString(36).substr(2, 9),
      file,
      name: file.name,
      url: URL.createObjectURL(file),
      result: null,
      loading: false,
    }));
    setTestImages(prev => [...prev, ...newImages]);
    setUploading(false);
    toast.success(`Added ${newImages.length} image${newImages.length > 1 ? "s" : ""}`);
  }, []);

  const handleFileSelect = (e) => processFiles(e.target.files || []);

  // drag-and-drop
  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    processFiles(e.dataTransfer.files);
  };

  // ── single inference ──
  const runInference = async (imageId) => {
    if (!selectedModel) { toast.error("Select a model first"); return; }
    const idx = testImages.findIndex(img => img.id === imageId);
    if (idx === -1) return;

    setTestImages(prev => { const u = [...prev]; u[idx] = { ...u[idx], loading: true }; return u; });

    try {
      const formData = new FormData();
      formData.append("file", testImages[idx].file);
      if (selectedModel.startsWith("job_")) {
        formData.append("job_id", selectedModel.replace("job_", ""));
      } else {
        formData.append("model_name", selectedModel);
      }
      formData.append("confidence", confidence.toString());
      formData.append("iou", iou.toString());

      const res = await fetch(API_ENDPOINTS.INFERENCE.PREDICT, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) throw new Error("Inference failed");

      const data = await res.json();
      const normalised = {
        predictions: (data.detections || []).map(det => ({
          class: det.class_name || det.class,
          confidence: det.confidence,
          bbox: det.bbox || [],
          polygon: det.polygon || null,
        })),
      };

      setTestImages(prev => {
        const u = [...prev];
        u[idx] = { ...u[idx], loading: false, result: normalised };
        return u;
      });
      toast.success(`${normalised.predictions.length} detection${normalised.predictions.length !== 1 ? "s" : ""} found`);
    } catch (err) {
      console.error(err);
      toast.error("Inference failed: " + err.message);
      setTestImages(prev => { const u = [...prev]; u[idx] = { ...u[idx], loading: false }; return u; });
    }
  };

  // ── batch inference ──
  const runBatchInference = async () => {
    const pending = testImages.filter(img => !img.result);
    if (!pending.length) { toast.info("All images already processed"); return; }
    if (!selectedModel) { toast.error("Select a model first"); return; }

    setLoading(true);
    setBatchProgress(0);
    setTestImages(prev => prev.map(img => pending.some(p => p.id === img.id) ? { ...img, loading: true } : img));

    const chunkSize = 20;
    let done = 0;

    for (let i = 0; i < pending.length; i += chunkSize) {
      const chunk = pending.slice(i, i + chunkSize);
      try {
        const formData = new FormData();
        if (selectedModel.startsWith("job_")) {
          formData.append("job_id", selectedModel.replace("job_", ""));
        } else {
          formData.append("model_name", selectedModel);
        }
        formData.append("confidence", confidence.toString());
        formData.append("iou", iou.toString());
        chunk.forEach(img => formData.append("files", img.file, img.name));

        const res = await fetch(API_ENDPOINTS.INFERENCE.PREDICT_BATCH, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        if (!res.ok) throw new Error(`Batch failed at chunk ${i}`);

        const data = await res.json();
        setTestImages(prev => {
          const u = [...prev];
          (data.results || []).forEach((r, ridx) => {
            const img = chunk[ridx];
            if (!img) return;
            const imgIdx = u.findIndex(x => x.id === img.id);
            if (imgIdx === -1) return;
            u[imgIdx] = {
              ...u[imgIdx],
              loading: false,
              result: {
                predictions: (r.detections || []).map(det => ({
                  class: det.class_name || det.class,
                  confidence: det.confidence,
                  bbox: det.bbox || [],
                  polygon: det.polygon || null,
                })),
              },
            };
          });
          return u;
        });

        done += chunk.length;
        setBatchProgress(Math.round((done / pending.length) * 100));
      } catch (err) {
        console.error(err);
        toast.error(err.message);
        setTestImages(prev => prev.map(img => chunk.some(c => c.id === img.id) ? { ...img, loading: false } : img));
      }
    }

    setLoading(false);
    setBatchProgress(0);
    toast.success(`Batch inference complete — ${done} image${done !== 1 ? "s" : ""} processed`);
  };

  // ── remove / clear ──
  const removeImage = (imageId) => {
    setTestImages(prev => {
      const img = prev.find(i => i.id === imageId);
      if (img?.url) URL.revokeObjectURL(img.url);
      return prev.filter(i => i.id !== imageId);
    });
    if (selectedResult?.id === imageId) setSelectedResult(null);
  };

  const clearAll = () => {
    testImages.forEach(img => { if (img.url) URL.revokeObjectURL(img.url); });
    setTestImages([]);
    setSelectedResult(null);
  };

  // ── export ──
  const downloadResults = () => {
    const data = testImages.filter(i => i.result).map(i => ({
      image: i.name,
      count: i.result.predictions?.length || 0,
      avg_confidence: i.result.predictions?.length
        ? +(i.result.predictions.reduce((s, p) => s + p.confidence, 0) / i.result.predictions.length).toFixed(3)
        : 0,
      predictions: i.result.predictions || [],
    }));
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `test_results_${dataset.name}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Results downloaded");
  };

  // ── canvas draw ──
  const drawResult = useCallback((img) => {
    const canvas = canvasRef.current;
    if (!canvas || !img?.result) return;
    const ctx = canvas.getContext("2d");
    const image = new Image();
    image.onload = () => {
      canvas.width  = image.width;
      canvas.height = image.height;
      ctx.drawImage(image, 0, 0);

      (img.result.predictions || []).forEach((pred, idx) => {
        const color = classColor(idx);

        if (pred.bbox?.length >= 4) {
          const [x1, y1, x2, y2] = pred.bbox;
          const bw = x2 - x1, bh = y2 - y1;

          // Shadow glow
          ctx.shadowColor  = color;
          ctx.shadowBlur   = 10;
          ctx.strokeStyle  = color;
          ctx.lineWidth    = 2.5;
          ctx.strokeRect(x1, y1, bw, bh);
          ctx.shadowBlur   = 0;

          ctx.fillStyle    = color;
          ctx.globalAlpha  = 0.12;
          ctx.fillRect(x1, y1, bw, bh);
          ctx.globalAlpha  = 1.0;

          const label   = `${pred.class}  ${(pred.confidence * 100).toFixed(1)}%`;
          ctx.font      = "bold 13px Inter, sans-serif";
          const tw      = ctx.measureText(label).width;
          const lh      = 22;
          const lx      = x1;
          const ly      = y1 - lh < 0 ? y1 + 4 : y1 - lh;

          // Label pill
          ctx.fillStyle  = color;
          ctx.beginPath();
          ctx.roundRect?.(lx, ly, tw + 14, lh, 4) ||
            ctx.rect(lx, ly, tw + 14, lh);
          ctx.fill();

          ctx.fillStyle  = "#fff";
          ctx.fillText(label, lx + 7, ly + lh - 6);
        }

        if (pred.polygon && Array.isArray(pred.polygon)) {
          ctx.strokeStyle = color;
          ctx.lineWidth   = 2;
          ctx.beginPath();
          for (let i = 0; i < pred.polygon.length; i += 2) {
            i === 0 ? ctx.moveTo(pred.polygon[i], pred.polygon[i + 1])
                    : ctx.lineTo(pred.polygon[i], pred.polygon[i + 1]);
          }
          ctx.closePath();
          ctx.stroke();
          ctx.fillStyle   = color;
          ctx.globalAlpha = 0.15;
          ctx.fill();
          ctx.globalAlpha = 1.0;
        }
      });
    };
    image.src = img.url;
  }, []);

  useEffect(() => {
    if (selectedResult) {
      setTimeout(() => drawResult(selectedResult), 80);
    }
  }, [selectedResult, drawResult]);

  // ── derived stats ──
  const tested  = testImages.filter(i => i.result).length;
  const totalDet = testImages.reduce((s, i) => s + (i.result?.predictions?.length || 0), 0);
  const avgConf = tested > 0
    ? testImages.filter(i => i.result).reduce((s, i) => {
        const preds = i.result.predictions || [];
        return s + (preds.length ? preds.reduce((a, p) => a + p.confidence, 0) / preds.length : 0);
      }, 0) / tested
    : 0;

  const modelInfo = models.find(m => m.name === selectedModel);

  // ── no models state ──
  if (models.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center gap-6 p-12">
        <div className="w-20 h-20 rounded-none bg-violet-400/10 border border-violet-500/20 flex items-center justify-center">
          <FlaskConical className="w-9 h-9 text-violet-400" />
        </div>
        <div>
          <h3 className="text-xl font-semibold">No Models Available</h3>
          <p className="text-sm text-muted-foreground mt-2 max-w-sm">
            Train a model on this dataset first, then come back to test it against new images.
          </p>
        </div>
        <Button
          className="bg-violet-500 hover:bg-violet-400"
          onClick={() => window.location.href = "?tab=train"}
        >
          <Cpu className="w-4 h-4 mr-2" /> Go to Train
        </Button>
      </div>
    );
  }

  // ── main render ──
  return (
    <div className="flex flex-col gap-6 h-full">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-violet-400" />
            Test Model
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Run inference on new images using your trained models
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tested > 0 && (
            <Button variant="outline" size="sm" onClick={downloadResults} className="border-white/10 hover:bg-white/5 text-xs">
              <Download className="w-3.5 h-3.5 mr-1.5" /> Export Results
            </Button>
          )}
          {testImages.length > 0 && (
            <Button variant="outline" size="sm" onClick={clearAll} className="border-white/10 hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/30 text-xs">
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Clear All
            </Button>
          )}
        </div>
      </div>

      {/* ── Body: 3-column layout ── */}
      <div className="grid grid-cols-[260px_1fr] gap-5 flex-1 min-h-0">

        {/* ── Left Panel ── */}
        <div className="flex flex-col gap-4 overflow-y-auto pr-1" style={{ scrollbarWidth: "none" }}>

          {/* Model Selector */}
          <div className="rounded-none border border-white/8 bg-white/[0.03] p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Model</span>
              <button onClick={fetchModels} className="text-gray-500 hover:text-gray-300 transition-colors p-1 rounded-none hover:bg-white/5">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Custom styled dropdown */}
            <div className="relative" data-model-selector>
              <button
                onClick={() => setModelOpen(o => !o)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-none border border-white/10 bg-white/5 hover:bg-white/8 text-sm text-left transition-all"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-2 h-2 rounded-none bg-emerald-400 flex-shrink-0" />
                  <span className="truncate text-white">{selectedModel?.replace("job_", "Model ") || "Select model"}</span>
                </div>
                <ChevronDown className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform ${modelOpen ? "rotate-180" : ""}`} />
              </button>
              {modelOpen && (
                <div className="absolute z-50 top-full mt-1.5 w-full bg-zinc-900 border border-white/10 rounded-none shadow-none overflow-hidden">
                  {models.map(m => (
                    <button
                      key={m.name}
                      onClick={() => { setSelectedModel(m.name); setModelOpen(false); }}
                      className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm text-left transition-colors hover:bg-white/5 ${selectedModel === m.name ? "text-indigo-300 bg-violet-400/10" : "text-gray-300"}`}
                    >
                      <div className={`w-2 h-2 rounded-none flex-shrink-0 ${selectedModel === m.name ? "bg-indigo-400" : "bg-gray-600"}`} />
                      <span className="truncate">{m.name.replace("job_", "Model ")}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Model metadata */}
            {modelInfo && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                <span className="text-[10px] px-2 py-0.5 rounded-none bg-violet-400/10 text-indigo-300 border border-violet-500/20">
                  {modelInfo.format || "PyTorch"}
                </span>
                {modelInfo.size_mb && (
                  <span className="text-[10px] px-2 py-0.5 rounded-none bg-white/5 text-gray-400 border border-white/8">
                    {modelInfo.size_mb.toFixed(1)} MB
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Thresholds */}
          <div className="rounded-none border border-white/8 bg-white/[0.03] p-4 space-y-4">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-3.5 h-3.5 text-gray-400" />
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Thresholds</span>
            </div>

            {/* Confidence */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <label className="text-xs text-gray-400">Confidence</label>
                <span className="text-xs font-semibold text-indigo-300 tabular-nums">{(confidence * 100).toFixed(0)}%</span>
              </div>
              <div className="relative h-1.5 rounded-none bg-white/10">
                <div
                  className="absolute left-0 top-0 h-full rounded-none    transition-all"
                  style={{ width: `${((confidence - 0.05) / 0.90) * 100}%` }}
                />
                <input
                  type="range" min="0.05" max="0.95" step="0.05"
                  value={confidence}
                  onChange={e => setConfidence(parseFloat(e.target.value))}
                  className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
                />
              </div>
            </div>

            {/* IoU */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <label className="text-xs text-gray-400">IoU</label>
                <span className="text-xs font-semibold text-violet-300 tabular-nums">{(iou * 100).toFixed(0)}%</span>
              </div>
              <div className="relative h-1.5 rounded-none bg-white/10">
                <div
                  className="absolute left-0 top-0 h-full rounded-none    transition-all"
                  style={{ width: `${((iou - 0.1) / 0.80) * 100}%` }}
                />
                <input
                  type="range" min="0.1" max="0.9" step="0.05"
                  value={iou}
                  onChange={e => setIou(parseFloat(e.target.value))}
                  className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
                />
              </div>
            </div>
          </div>

          {/* Upload */}
          <div className="rounded-none border border-white/8 bg-white/[0.03] p-4 space-y-3">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Upload</span>
            <input ref={fileInputRef} type="file" multiple accept="image/*" onChange={handleFileSelect} className="hidden" />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="w-full flex items-center justify-center gap-2 h-10 rounded-none border border-dashed border-violet-500/40 bg-violet-400/5 hover:bg-violet-400/10 hover:border-violet-500/60 text-indigo-300 text-sm font-medium transition-all disabled:opacity-50"
            >
              {uploading
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Adding...</>
                : <><Upload className="w-4 h-4" /> Choose Images</>
              }
            </button>
          </div>

          {/* Stats */}
          {testImages.length > 0 && (
            <div className="grid grid-cols-2 gap-2">
              <StatPill label="Total"     value={testImages.length} color="indigo" />
              <StatPill label="Tested"    value={tested}            color="emerald" />
              <StatPill label="Objects"   value={totalDet}          color="amber" />
              <StatPill label="Avg Conf"  value={tested > 0 ? `${(avgConf * 100).toFixed(0)}%` : "—"} color="violet" />
            </div>
          )}

          {/* Run batch */}
          {testImages.length > 0 && (
            <Button
              onClick={runBatchInference}
              disabled={loading || !selectedModel}
              className="w-full    hover: hover: border-0 h-10 text-sm font-semibold"
            >
              {loading
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Running Batch...</>
                : <><Zap className="w-4 h-4 mr-2" /> Run Batch Inference</>
              }
            </Button>
          )}

          {/* Batch progress bar */}
          {loading && batchProgress > 0 && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-gray-500">
                <span>Batch progress</span>
                <span className="tabular-nums">{batchProgress}%</span>
              </div>
              <div className="h-1.5 rounded-none bg-white/10 overflow-hidden">
                <div
                  className="h-full rounded-none    transition-all duration-300"
                  style={{ width: `${batchProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Right Panel: canvas or grid ── */}
        <div className="min-h-0 flex flex-col gap-4 overflow-hidden">

          {/* Detail view */}
          {selectedResult ? (
            <div className="flex flex-col gap-3 h-full">
              {/* detail header */}
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setSelectedResult(null)}
                  className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" /> Back to grid
                </button>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 truncate max-w-[200px]">{selectedResult.name}</span>
                  <Badge className="bg-violet-400/20 text-indigo-300 border-violet-500/30 text-xs">
                    {selectedResult.result?.predictions?.length || 0} detection{selectedResult.result?.predictions?.length !== 1 ? "s" : ""}
                  </Badge>
                </div>
              </div>

              <div className="flex gap-4 flex-1 min-h-0">
                {/* canvas */}
                <div className="flex-1 rounded-none overflow-hidden bg-black/40 border border-white/8 flex items-center justify-center min-h-0">
                  <canvas
                    ref={canvasRef}
                    className="max-w-full max-h-full object-contain"
                    style={{ imageRendering: "crisp-edges" }}
                  />
                </div>

                {/* predictions list */}
                {selectedResult.result?.predictions?.length > 0 && (
                  <div className="w-52 flex-shrink-0 rounded-none border border-white/8 bg-white/[0.03] p-3 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Detections</p>
                    <div className="space-y-1.5">
                      {selectedResult.result.predictions.map((pred, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2 rounded-none bg-white/5 border border-white/5">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="w-2.5 h-2.5 rounded-none flex-shrink-0" style={{ backgroundColor: classColor(idx) }} />
                            <span className="text-xs truncate text-gray-200">{pred.class}</span>
                          </div>
                          <span className="text-[10px] font-semibold text-gray-400 flex-shrink-0 ml-1">
                            {(pred.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

          /* empty state: no images */
          ) : testImages.length === 0 ? (
            <div
              ref={dropRef}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex-1 rounded-none border-2 border-dashed flex flex-col items-center justify-center text-center cursor-pointer transition-all gap-4 p-12
                ${dragging
                  ? "border-violet-500/70 bg-violet-400/5 scale-[1.01]"
                  : "border-white/10 hover:border-violet-500/40 hover:bg-white/[0.02]"
                }`}
            >
              <div className={`w-20 h-20 rounded-none flex items-center justify-center transition-all ${dragging ? "bg-violet-400/20" : "bg-white/5 border border-white/10"}`}>
                <Upload className={`w-9 h-9 transition-colors ${dragging ? "text-violet-400" : "text-gray-500"}`} />
              </div>
              <div>
                <h3 className="font-semibold text-lg">{dragging ? "Drop to add images" : "Drop images here"}</h3>
                <p className="text-sm text-muted-foreground mt-1">or click to browse • JPG, PNG, WEBP supported</p>
              </div>
              {!dragging && (
                <span className="text-xs text-gray-600 border border-white/5 rounded-none px-4 py-1.5">
                  Select a model on the left, then upload images to test
                </span>
              )}
            </div>

          /* image grid */
          ) : (
            <div
              ref={dropRef}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              className={`flex-1 overflow-y-auto rounded-none transition-all ${dragging ? "ring-2 ring-indigo-500/50 ring-offset-2 ring-offset-black" : ""}`}
              style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(255,255,255,0.1) transparent" }}
            >
              <div className="grid grid-cols-2 xl:grid-cols-3 gap-3 pb-4">
                {testImages.map(img => (
                  <ImageCard
                    key={img.id}
                    img={img}
                    selectedModel={selectedModel}
                    onRun={runInference}
                    onRemove={removeImage}
                    onView={(i) => setSelectedResult(i)}
                  />
                ))}

                {/* Add more tile */}
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="aspect-[4/3] rounded-none border-2 border-dashed border-white/10 hover:border-violet-500/40 hover:bg-violet-400/5 flex flex-col items-center justify-center gap-2 text-gray-500 hover:text-violet-400 transition-all"
                >
                  <Upload className="w-6 h-6" />
                  <span className="text-xs">Add More</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── ImageCard sub-component ───────────────────────────────────────────────────

function ImageCard({ img, selectedModel, onRun, onRemove, onView }) {
  const hasResult = !!img.result;
  const detCount  = img.result?.predictions?.length || 0;

  return (
    <div className="group relative rounded-none overflow-hidden border border-white/8 bg-white/[0.03] hover:border-white/15 transition-all">
      {/* image */}
      <div className="aspect-[4/3] relative overflow-hidden bg-black/40">
        <img
          src={img.url}
          alt={img.name}
          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />

        {/* loading overlay */}
        {img.loading && (
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex flex-col items-center justify-center gap-2">
            <div className="w-8 h-8 border-2 border-indigo-400 border-t-transparent rounded-none animate-spin" />
            <span className="text-xs text-indigo-300">Detecting...</span>
          </div>
        )}

        {/* success badge */}
        {hasResult && !img.loading && (
          <div className="absolute top-2 left-2">
            <div className={`flex items-center gap-1 px-2 py-0.5 rounded-none text-[10px] font-semibold border ${
              detCount > 0
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                : "bg-gray-500/20 text-gray-400 border-gray-500/30"
            }`}>
              {detCount > 0 ? <><Target className="w-2.5 h-2.5" /> {detCount}</> : "0 det."}
            </div>
          </div>
        )}

        {/* remove button */}
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(img.id); }}
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 w-6 h-6 rounded-none bg-red-500/90 hover:bg-red-400 flex items-center justify-center transition-all"
        >
          <X className="w-3.5 h-3.5 text-white" />
        </button>

        {/* hover overlay for view */}
        {hasResult && (
          <div
            onClick={() => onView(img)}
            className="absolute inset-0 bg-black/0 hover:bg-black/40 flex items-center justify-center opacity-0 hover:opacity-100 transition-all cursor-pointer"
          >
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-white/15 backdrop-blur-sm text-white text-xs font-medium border border-white/20">
              <Eye className="w-3.5 h-3.5" /> Inspect
            </div>
          </div>
        )}
      </div>

      {/* card footer */}
      <div className="px-3 py-2.5 flex items-center justify-between gap-2">
        <p className="text-xs text-gray-400 truncate min-w-0">{img.name}</p>

        {hasResult ? (
          <button
            onClick={() => onView(img)}
            className="flex-shrink-0 flex items-center gap-1 text-[10px] text-indigo-300 hover:text-indigo-200 transition-colors"
          >
            <Maximize2 className="w-3 h-3" /> View
          </button>
        ) : (
          <button
            onClick={() => onRun(img.id)}
            disabled={img.loading || !selectedModel}
            className="flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-none bg-violet-500 hover:bg-violet-400 disabled:opacity-40 text-white text-[10px] font-semibold transition-all"
          >
            {img.loading
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <><Play className="w-3 h-3" /> Run</>
            }
          </button>
        )}
      </div>
    </div>
  );
}
