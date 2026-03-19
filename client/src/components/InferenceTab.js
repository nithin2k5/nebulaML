"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Webcam from "react-webcam";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Upload, Image as ImageIcon, Zap, Copy, Box, Trash2,
  Loader, Clock, Play, Camera, Video, StopCircle
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";

export default function InferenceTab() {
  const { token } = useAuth();
  const [mode, setMode] = useState("upload"); // 'upload' or 'webcam'
  const [image, setImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [running, setRunning] = useState(false);
  const [webcamRunning, setWebcamRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [inferenceTime, setInferenceTime] = useState(null);
  const [model, setModel] = useState("yolov8n");
  const [confidence, setConfidence] = useState(0.25);

  const fileInputRef = useRef(null);
  const canvasRef = useRef(null);
  const webcamRef = useRef(null);
  const imageObjRef = useRef(null);
  const intervalRef = useRef(null);

  const models = [
    { id: "yolov8n", name: "YOLOv8 Nano", desc: "Fastest · 3.2M params", badge: "Speed" },
    { id: "yolov8s", name: "YOLOv8 Small", desc: "Balanced · 11.2M params", badge: null },
    { id: "yolov8m", name: "YOLOv8 Medium", desc: "High accuracy · 25.9M params", badge: null },
    { id: "yolov8l", name: "YOLOv8 Large", desc: "Very accurate · 43.7M params", badge: "Accuracy" },
    { id: "yolov8x", name: "YOLOv8 XLarge", desc: "Max precision · 68.2M params", badge: null },
  ];

  const classColors = [
    '#6366f1', '#f43f5e', '#10b981', '#f59e0b', '#8b5cf6',
    '#06b6d4', '#ec4899', '#84cc16', '#ef4444', '#3b82f6',
  ];

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      setImage(file);
      setImagePreview(URL.createObjectURL(file));
      setResults(null);
      setInferenceTime(null);
    }
  }, []);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setImage(file);
      setImagePreview(URL.createObjectURL(file));
      setResults(null);
      setInferenceTime(null);
    }
  };

  // Draw bounding boxes on canvas (Upload Mode)
  useEffect(() => {
    if (mode !== "upload" || !results || !imagePreview) return;

    const img = new Image();
    img.onload = () => {
      imageObjRef.current = img;
      const canvas = canvasRef.current;
      if (!canvas) return;

      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');

      // Draw the image
      ctx.drawImage(img, 0, 0);

      drawDetections(ctx, results.detections, img.naturalWidth, img.naturalHeight);
    };
    img.src = imagePreview;
  }, [results, imagePreview, mode]);

  const drawDetections = (ctx, detections, width, height) => {
    if (!detections) return;

    detections.forEach((det, idx) => {
      const color = classColors[idx % classColors.length];

      let x, y, w, h;
      if (det.bbox_normalized) {
        // Center-x, center-y, width, height format (normalized)
        x = (det.bbox_normalized[0] - det.bbox_normalized[2] / 2) * width;
        y = (det.bbox_normalized[1] - det.bbox_normalized[3] / 2) * height;
        w = det.bbox_normalized[2] * width;
        h = det.bbox_normalized[3] * height;
      } else if (det.bbox) {
        [x, y, w, h] = det.bbox;
      } else {
        return;
      }

      // Semi-transparent fill
      ctx.fillStyle = color + '25';
      ctx.fillRect(x, y, w, h);

      // Stroke
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, w, h);

      // Label
      const label = `${det.class_name} ${Math.round(det.confidence * 100)}%`;
      ctx.font = 'bold 14px Inter, system-ui, sans-serif';
      const labelW = ctx.measureText(label).width + 12;
      const labelH = 24;

      ctx.fillStyle = color;
      ctx.fillRect(x, y - labelH, labelW, labelH);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, x + 6, y - 7);
    });
  };

  const runInference = async () => {
    if (!image) return;
    setRunning(true);
    const startTime = Date.now();

    const formData = new FormData();
    formData.append("file", image);
    formData.append("model", model);
    formData.append("confidence", confidence);

    try {
      const response = await fetch(API_ENDPOINTS.INFERENCE.PREDICT, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData,
      });
      const data = await response.json();
      setResults(data);
      setInferenceTime(Date.now() - startTime);
      toast.success(`Detected ${data.num_detections || 0} object(s)`);
    } catch (error) {
      toast.error("Inference failed: " + error.message);
    } finally {
      setRunning(false);
    }
  };

  // --- Webcam Logic ---

  const startWebcamInference = () => {
    setWebcamRunning(true);
    setResults(null);
    // Start loop
    intervalRef.current = setInterval(captureAndInfer, 500); // 2 FPS to be safe
  };

  const stopWebcamInference = () => {
    setWebcamRunning(false);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    // Clear canvas
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  };

  // Cleanup on unmount or mode change
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  useEffect(() => {
    if (mode === "upload") {
      stopWebcamInference();
    }
  }, [mode]);

  const captureAndInfer = async () => {
    if (!webcamRef.current) return;

    // Get screenshot
    const imageSrc = webcamRef.current.getScreenshot();
    if (!imageSrc) return;

    // Convert base64 to blob
    const res = await fetch(imageSrc);
    const blob = await res.blob();
    const file = new File([blob], "webcam-frame.jpg", { type: "image/jpeg" });

    const startTime = Date.now();
    const formData = new FormData();
    formData.append("file", file);
    formData.append("model", model);
    formData.append("confidence", confidence);

    try {
      // Create a specific webcam endpoint or reuse predict? reusing for now.
      // Ideally we'd optimize this to accept base64 json to avoid multipart overhead,
      // but multipart is robust enough for 2-5fps on localhost.
      const response = await fetch(API_ENDPOINTS.INFERENCE.PREDICT, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) return;

      const data = await response.json();

      // Update stats
      setInferenceTime(Date.now() - startTime);
      setResults(data);

      // Draw immediately on overlay canvas
      const video = webcamRef.current.video;
      const canvas = canvasRef.current;

      if (video && canvas && data.detections) {
        // Match canvas dimensions to video
        if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
        }

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawDetections(ctx, data.detections, canvas.width, canvas.height);
      }

    } catch (error) {
      console.error("Webcam inference error:", error);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in text-gray-100">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">Inference Playground</h2>
          <p className="text-muted-foreground mt-1">
            {mode === 'upload' ? 'Upload an image and run real-time object detection.' : 'Real-time object detection using your webcam.'}
          </p>
        </div>

        {/* Mode Toggle */}
        <div className="flex items-center gap-2 bg-white/5 p-1 rounded-lg border border-white/10">
          <Button
            size="sm"
            variant={mode === "upload" ? "secondary" : "ghost"}
            onClick={() => setMode("upload")}
            className="gap-2"
          >
            <ImageIcon className="w-4 h-4" /> Upload
          </Button>
          <Button
            size="sm"
            variant={mode === "webcam" ? "secondary" : "ghost"}
            onClick={() => setMode("webcam")}
            className="gap-2"
          >
            <Camera className="w-4 h-4" /> Webcam
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configuration Panel */}
        <div className="space-y-6">
          <Card className="bg-card/40 border-white/5">
            <CardHeader>
              <CardTitle className="text-base">Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label className="text-sm">Model</Label>
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger className="bg-black/30 border-white/10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map(m => (
                      <SelectItem key={m.id} value={m.id}>
                        <div className="flex items-center gap-2">
                          <span>{m.name}</span>
                          {m.badge && <Badge variant="outline" className="text-[10px] h-4">{m.badge}</Badge>}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">{models.find(m => m.id === model)?.desc}</p>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between">
                  <Label className="text-sm">Confidence</Label>
                  <span className="text-xs font-mono text-indigo-400">{confidence.toFixed(2)}</span>
                </div>
                <Input
                  type="range"
                  min="0.05"
                  max="0.95"
                  step="0.05"
                  value={confidence}
                  onChange={(e) => setConfidence(parseFloat(e.target.value))}
                  className="accent-indigo-500"
                />
              </div>

              {mode === "upload" ? (
                <Button
                  onClick={runInference}
                  disabled={!image || running}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  {running ? <Loader className="animate-spin mr-2" /> : <Play className="mr-2" />}
                  {running ? "Running..." : "Run Inference"}
                </Button>
              ) : (
                <Button
                  onClick={webcamRunning ? stopWebcamInference : startWebcamInference}
                  variant={webcamRunning ? "destructive" : "default"}
                  className={cn(
                    "w-full",
                    !webcamRunning && "bg-indigo-600 hover:bg-indigo-500 text-white"
                  )}
                >
                  {webcamRunning ? (
                    <>
                      <StopCircle className="mr-2 h-4 w-4" /> Stop Webcam
                    </>
                  ) : (
                    <>
                      <Video className="mr-2 h-4 w-4" /> Start Webcam
                    </>
                  )}
                </Button>
              )}
            </CardContent>
          </Card>

          {/* Results Summary */}
          {(results || webcamRunning) && (
            <Card className="bg-card/40 border-white/5 animate-slide-up">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    {mode === "webcam" ? "Live Stats" : "Results"}
                  </CardTitle>
                  {mode === "upload" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-gray-400 hover:text-white"
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(results, null, 2));
                        toast.success("Copied JSON to clipboard");
                      }}
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-400 flex items-center gap-2"><Box /> Objects</span>
                  <span className="font-bold text-white">{results?.num_detections || 0}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-400 flex items-center gap-2"><Clock /> Latency</span>
                  <span className="font-mono text-emerald-400">{inferenceTime ? `${inferenceTime}ms` : "-"}</span>
                </div>

                {/* Detection list for Upload Mode */}
                {mode === "upload" && results?.detections?.length > 0 && (
                  <div className="pt-3 border-t border-white/5 space-y-2">
                    {results.detections.map((det, i) => (
                      <div key={i} className="flex items-center justify-between text-sm p-2 rounded-lg bg-white/[0.03]">
                        <div className="flex items-center gap-2">
                          <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: classColors[i % classColors.length] }} />
                          <span className="text-gray-200">{det.class_name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all"
                              style={{
                                width: `${det.confidence * 100}%`,
                                backgroundColor: classColors[i % classColors.length]
                              }}
                            />
                          </div>
                          <span className="text-xs font-mono text-gray-400 w-10 text-right">{Math.round(det.confidence * 100)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Display Area */}
        <div className="lg:col-span-2">
          {mode === "upload" ? (
            // --- Upload Mode Display ---
            !imagePreview ? (
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "h-[500px] border-2 border-dashed rounded-2xl flex flex-col items-center justify-center cursor-pointer transition-all",
                  isDragging
                    ? "border-indigo-500 bg-indigo-500/5 scale-[0.99]"
                    : "border-white/10 hover:border-white/20 bg-white/[0.02] hover:bg-white/[0.03]"
                )}
              >
                <div className={cn(
                  "w-20 h-20 rounded-2xl flex items-center justify-center mb-6 transition-all",
                  isDragging ? "bg-indigo-500/20 text-indigo-400 scale-110" : "bg-white/5 text-gray-500"
                )}>
                  <Upload className="text-3xl" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{isDragging ? "Drop here" : "Upload an Image"}</h3>
                <p className="text-sm text-gray-500 mb-6">Drag & drop or click to browse. JPG, PNG, WEBP supported.</p>
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileSelect} className="hidden" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="relative rounded-2xl overflow-hidden border border-white/5 bg-black flex items-center justify-center min-h-[400px]">
                  <canvas
                    ref={canvasRef}
                    className="max-w-full max-h-[500px]"
                    style={{ display: results ? 'block' : 'none', width: 'auto', height: 'auto', maxWidth: '100%', maxHeight: '500px' }}
                  />
                  <img
                    src={imagePreview}
                    alt="Preview"
                    className="max-w-full max-h-[500px] object-contain"
                    style={{ display: results ? 'none' : 'block' }}
                  />

                  {running && (
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center">
                      <div className="text-center">
                        <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                        <p className="text-sm text-gray-300">Running inference...</p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex justify-between items-center">
                  <p className="text-sm text-muted-foreground">
                    {results ? `Detected ${results.num_detections || 0} objects` : "Ready to run inference"}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-white/10"
                      onClick={() => { setImage(null); setImagePreview(null); setResults(null); setInferenceTime(null); }}
                    >
                      <Trash2 className="mr-2" /> Clear
                    </Button>
                    <Button
                      size="sm"
                      onClick={runInference}
                      disabled={running}
                      className="bg-indigo-600 hover:bg-indigo-500"
                    >
                      {running ? <Loader className="animate-spin mr-2" /> : <Zap className="mr-2" />}
                      Re-run
                    </Button>
                  </div>
                </div>
              </div>
            )
          ) : (
            // --- Webcam Mode Display ---
            <div className="space-y-4">
              <div className="relative rounded-2xl overflow-hidden border border-white/5 bg-black flex items-center justify-center aspect-video">
                <Webcam
                  ref={webcamRef}
                  screenshotFormat="image/jpeg"
                  className="w-full h-full object-cover"
                  videoConstraints={{
                    facingMode: "user"
                  }}
                />
                {/* Overlay Canvas */}
                <canvas
                  ref={canvasRef}
                  className="absolute inset-0 w-full h-full pointer-events-none"
                />

                {!webcamRunning && (
                  <div className="absolute inset-0 bg-black/80 flex items-center justify-center">
                    <div className="text-center p-6">
                      <Camera className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                      <h3 className="text-xl font-semibold mb-2">Webcam Paused</h3>
                      <Button onClick={startWebcamInference}>
                        <Play className="mr-2 h-4 w-4" /> Start Camera & Inference
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between p-4 bg-white/[0.03] rounded-xl border border-white/5">
                <div className="flex items-center gap-3">
                  <div className={cn("w-3 h-3 rounded-full animate-pulse", webcamRunning ? "bg-red-500" : "bg-gray-500")} />
                  <span className="font-medium text-sm">
                    {webcamRunning ? "Live Inference Active" : "Camera Idle"}
                  </span>
                </div>
                {webcamRunning && (
                  <Badge variant="outline" className="border-indigo-500/30 text-indigo-400 bg-indigo-500/10">
                    {intervalRef.current ? "Processing..." : "Ready"}
                  </Badge>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
