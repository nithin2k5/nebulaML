"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Upload, CheckCircle, Loader, Terminal, X } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectDeploy({ dataset }) {
    const { token } = useAuth();
    const [jobs, setJobs] = useState([]);
    const [selectedJob, setSelectedJob] = useState(null);
    const [selectedFile, setSelectedFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [confidence, setConfidence] = useState(0.25);
    const [isLoading, setIsLoading] = useState(false);
    const [results, setResults] = useState(null);
    const canvasRef = useRef(null);
    // Keep a stable ref to the current preview URL so the draw effect always has fresh data
    const previewUrlRef = useRef(null);

    const fetchJobs = useCallback(async () => {
        if (!dataset?.id || !token) return;
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                const projectJobs = (data.jobs || []).filter(j => j.dataset_id === dataset.id && (j.status === "completed" || j.status === "success"));
                setJobs(projectJobs);
                if (projectJobs.length > 0) {
                    setSelectedJob(projectJobs[0].job_id);
                }
            } else {
                toast.error("Failed to load trained models");
            }
        } catch (e) {
            toast.error("Error loading models: " + e.message);
        }
    }, [dataset?.id, token]);

    useEffect(() => {
        if (token) fetchJobs();
    }, [token, fetchJobs]);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        const newUrl = URL.createObjectURL(file);
        previewUrlRef.current = newUrl;
        setSelectedFile(file);
        setPreviewUrl(newUrl);
        setResults(null);
    };

    const clearFile = () => {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setSelectedFile(null);
        setPreviewUrl(null);
        setResults(null);
    };

    const drawDetections = (detections, imageUrl) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const img = new Image();
        img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);
            detections.forEach((det, idx) => {
                const color = `hsl(${(idx * 137.5) % 360}, 70%, 55%)`;
                const [x1, y1, x2, y2] = det.bbox;
                const bw = x2 - x1;
                const bh = y2 - y1;

                // Fill
                ctx.fillStyle = color;
                ctx.globalAlpha = 0.18;
                ctx.fillRect(x1, y1, bw, bh);
                ctx.globalAlpha = 1;

                // Border
                ctx.strokeStyle = color;
                ctx.lineWidth = Math.max(2, img.width / 400);
                ctx.strokeRect(x1, y1, bw, bh);

                // Label background
                const label = `${det.class_name} ${Math.round(det.confidence * 100)}%`;
                const fontSize = Math.max(12, img.width / 60);
                ctx.font = `bold ${fontSize}px Inter, sans-serif`;
                const tw = ctx.measureText(label).width;
                const th = fontSize + 8;
                ctx.fillStyle = color;
                ctx.fillRect(x1, y1 - th, tw + 10, th);

                // Label text
                ctx.fillStyle = "#fff";
                ctx.fillText(label, x1 + 5, y1 - 6);
            });
        };
        img.src = imageUrl;
    };

    // Draw bounding boxes whenever results arrive and canvas is mounted
    useEffect(() => {
        if (!results?.detections?.length) return;
        const canvas = canvasRef.current;
        if (!canvas) return;
        drawDetections(results.detections, previewUrlRef.current);
    }, [results]);

    const handleInference = async () => {
        if (!selectedFile) { toast.error("Please upload an image first."); return; }
        if (!selectedJob) { toast.error("Please select a trained model."); return; }
        setIsLoading(true);
        setResults(null);

        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("confidence", confidence);
        formData.append("job_id", selectedJob);

        try {
            const response = await fetch(API_ENDPOINTS.INFERENCE.PREDICT, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
                body: formData,
            });

            if (!response.ok) {
                const errBody = await response.json().catch(() => ({}));
                const detail = errBody.detail || response.statusText;
                if (response.status === 404 && detail.includes("not found")) {
                    throw new Error("Model weights not found. Ensure training completed successfully and the server has not been moved.");
                }
                throw new Error(detail);
            }

            const data = await response.json();
            setResults(data);
            if (data.num_detections > 0) {
                toast.success(`Found ${data.num_detections} object${data.num_detections !== 1 ? "s" : ""}`);
            } else {
                toast.info("No objects detected above the confidence threshold.");
            }
        } catch (error) {
            console.error("Inference error:", error);
            toast.error("Inference failed: " + error.message);
        } finally {
            setIsLoading(false);
        }
    };

    if (jobs.length === 0) {
        return (
            <div className="h-full flex flex-col items-center justify-center text-center p-8">
                <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mb-4">
                    <Terminal className="text-2xl text-muted-foreground" />
                </div>
                <h3 className="text-xl font-semibold mb-2">No Trained Models Available</h3>
                <p className="text-muted-foreground max-w-md mb-6">
                    You haven&apos;t trained any models for this project yet. Go to the <strong>Train</strong> tab to create your first model version.
                </p>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Deploy & Inference</h2>
                    <p className="text-muted-foreground text-sm">Test your trained models directly in the browser.</p>
                </div>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
                <div className="md:col-span-1 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Configuration</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="space-y-2">
                                <Label>Select Model Version</Label>
                                <Select value={selectedJob} onValueChange={setSelectedJob}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select a trained model" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {jobs.map((job) => (
                                            <SelectItem key={job.job_id} value={job.job_id}>
                                                {job.config?.model_name || "Unknown Model"} - {job.created_at ? new Date(job.created_at).toLocaleDateString() : "Unknown date"}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-2">
                                <Label>Confidence Threshold: {confidence}</Label>
                                <Input
                                    type="range"
                                    min="0"
                                    max="1"
                                    step="0.05"
                                    value={confidence}
                                    onChange={(e) => setConfidence(parseFloat(e.target.value))}
                                />
                            </div>

                            <div className="pt-4 border-t border-border mt-4">
                                <div className="flex items-center justify-between">
                                    <div className="space-y-0.5 mr-4">
                                        <Label>Active Learning (Auto-Collect)</Label>
                                        <p className="text-xs text-muted-foreground">
                                            Low confidence predictions (&lt; {confidence}) will be automatically flagged in the Active Learn tab for human review.
                                        </p>
                                    </div>
                                    <Switch checked={true} onCheckedChange={() => toast.success("Active Learning feedback loop enabled!")} />
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>API Usage</CardTitle>
                            <CardDescription>Python Example</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                                {`import requests

url = "${API_ENDPOINTS.INFERENCE.PREDICT}"
files = {'file': open('image.jpg', 'rb')}
data = {'job_id': '${selectedJob}', 'confidence': ${confidence}}

response = requests.post(url, files=files, data=data)
print(response.json())`}
                            </pre>
                        </CardContent>
                    </Card>
                </div>

                <div className="md:col-span-2 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Test Inference</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {!selectedFile ? (
                                <label className="border-2 border-dashed border-border rounded-xl p-12 text-center hover:border-primary transition-colors cursor-pointer flex flex-col items-center gap-3">
                                    <Input
                                        type="file"
                                        accept="image/*"
                                        onChange={handleFileChange}
                                        className="hidden"
                                    />
                                    <div className="w-14 h-14 rounded-full bg-muted flex items-center justify-center">
                                        <Upload className="w-6 h-6 text-muted-foreground" />
                                    </div>
                                    <div>
                                        <p className="font-medium">Click to upload an image</p>
                                        <p className="text-xs text-muted-foreground mt-1">JPG, PNG — max 10 MB</p>
                                    </div>
                                </label>
                            ) : (
                                <div className="space-y-4">
                                    {/* Image + canvas overlay — canvas is always mounted so ref is stable */}
                                    <div className="rounded-xl border border-border bg-muted/10 overflow-hidden flex items-center justify-center p-3 relative">
                                        {/* Plain preview: shown while no results */}
                                        <img
                                            src={previewUrl}
                                            alt="Preview"
                                            className={`max-w-full max-h-[420px] rounded object-contain ${results ? "hidden" : ""}`}
                                        />
                                        {/* Canvas: always in DOM; drawDetections populates it after results arrive */}
                                        <canvas
                                            ref={canvasRef}
                                            className={`max-w-full max-h-[420px] rounded object-contain ${results ? "" : "hidden"}`}
                                        />
                                    </div>

                                    {/* Detection list */}
                                    {results?.detections?.length > 0 && (
                                        <div className="rounded-xl border border-border overflow-hidden">
                                            <div className="bg-muted/40 px-4 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide border-b border-border">
                                                {results.num_detections} Detection{results.num_detections !== 1 ? "s" : ""}
                                            </div>
                                            <div className="divide-y divide-border max-h-40 overflow-y-auto">
                                                {results.detections.map((det, idx) => (
                                                    <div key={idx} className="flex items-center justify-between px-4 py-2">
                                                        <div className="flex items-center gap-2">
                                                            <div
                                                                className="w-2.5 h-2.5 rounded-full shrink-0"
                                                                style={{ backgroundColor: `hsl(${(idx * 137.5) % 360}, 70%, 55%)` }}
                                                            />
                                                            <span className="text-sm font-medium">{det.class_name}</span>
                                                        </div>
                                                        <Badge variant="outline" className="text-xs tabular-nums">
                                                            {Math.round(det.confidence * 100)}%
                                                        </Badge>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {results?.num_detections === 0 && (
                                        <p className="text-sm text-muted-foreground text-center py-2">
                                            No objects detected above the confidence threshold.
                                        </p>
                                    )}

                                    <div className="flex justify-between items-center">
                                        <p className="text-sm text-muted-foreground">
                                            {selectedFile.name}
                                        </p>
                                        <div className="flex gap-2">
                                            <Button variant="outline" size="sm" onClick={clearFile}>
                                                <X className="w-4 h-4 mr-1.5" /> Clear
                                            </Button>
                                            <Button size="sm" onClick={handleInference} disabled={isLoading || !selectedJob}>
                                                {isLoading
                                                    ? <><Loader className="w-4 h-4 mr-1.5 animate-spin" /> Running…</>
                                                    : <><CheckCircle className="w-4 h-4 mr-1.5" /> Run Model</>
                                                }
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>

            {/* Edge Deployment Section */}
            <Card className="mt-2">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Terminal className="w-5 h-5" />
                        Edge Deployment
                    </CardTitle>
                    <CardDescription>Export your model for deployment on edge devices</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[
                            { platform: "Raspberry Pi", format: "onnx", desc: "ONNX Runtime on ARM" },
                            { platform: "Jetson Nano", format: "engine", desc: "TensorRT optimized" },
                            { platform: "iOS / macOS", format: "coreml", desc: "Apple CoreML" },
                            { platform: "Web Browser", format: "onnx", desc: "ONNX.js in-browser" },
                        ].map((target) => (
                            <div
                                key={target.platform}
                                className="p-4 rounded-lg border border-border hover:border-primary/50 transition-all"
                            >
                                <p className="font-medium text-sm">{target.platform}</p>
                                <p className="text-xs text-muted-foreground mb-3">{target.desc}</p>
                                <Badge variant="outline" className="text-[10px]">{target.format.toUpperCase()}</Badge>
                            </div>
                        ))}
                    </div>

                    {selectedJob && (
                        <div className="mt-4">
                            <Label className="text-sm font-medium mb-2 block">Inference Script (Python)</Label>
                            <pre className="bg-muted p-4 rounded-md text-xs overflow-x-auto">
                                {`# Edge Inference Script for NebulaML Models
# Platform: Raspberry Pi / Jetson / Desktop
# Requirements: pip install ultralytics opencv-python

from ultralytics import YOLO
import cv2

# Load exported model
model = YOLO("best.onnx")  # or best.pt, best.engine

# Run inference on camera
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Run detection
    results = model(frame, conf=${confidence})
    
    # Draw results
    annotated = results[0].plot()
    cv2.imshow("Detection", annotated)
    
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()`}
                            </pre>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}

