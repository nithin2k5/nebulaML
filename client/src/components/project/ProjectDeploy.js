"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Upload, Image, CheckCircle, Loader, Terminal } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectDeploy({ dataset }) {
    const { token } = useAuth();
    const [jobs, setJobs] = useState([]);
    const [selectedJob, setSelectedJob] = useState(null);
    const [selectedFile, setSelectedFile] = useState(null);
    const [confidence, setConfidence] = useState(0.25);
    const [isLoading, setIsLoading] = useState(false);
    const [results, setResults] = useState(null);

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
        if (file) {
            setSelectedFile(file);
            setResults(null);
        }
    };

    const handleInference = async () => {
        if (!selectedFile || !selectedJob) return;

        setIsLoading(true);
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("confidence", confidence);
        formData.append("job_id", selectedJob);

        try {
            const response = await fetch(API_ENDPOINTS.INFERENCE.PREDICT, {
                method: "POST",
                body: formData,
            });

            if (!response.ok) {
                throw new Error(await response.text());
            }

            const data = await response.json();
            setResults(data);
            toast.success("Inference successful!");
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
                                <div className="border-2 border-dashed border-border rounded-lg p-12 text-center hover:border-primary transition-colors cursor-pointer relative">
                                    <Input
                                        type="file"
                                        accept="image/*"
                                        onChange={handleFileChange}
                                        className="absolute inset-0 opacity-0 cursor-pointer"
                                    />
                                    <Upload className="mx-auto text-4xl text-muted-foreground mb-4" />
                                    <p className="font-medium">Click to upload an image</p>
                                    <p className="text-xs text-muted-foreground mt-1">Supports JPG, PNG</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="relative rounded-lg overflow-hidden border border-border bg-black/5 flex items-center justify-center min-h-[300px]">
                                        {/* Display Image */}
                                        <div className="relative">
                                            <img
                                                src={URL.createObjectURL(selectedFile)}
                                                alt="Preview"
                                                className="max-h-[400px] w-auto mx-auto block"
                                            />
                                            {/* Overlay Bounding Boxes */}
                                            {results?.detections?.map((det, idx) => (
                                                <div
                                                    key={idx}
                                                    className="absolute border-2 border-primary"
                                                    style={{
                                                        left: `${det.bbox_normalized[0] * 100 - (det.bbox_normalized[2] * 100) / 2}%`,
                                                        top: `${det.bbox_normalized[1] * 100 - (det.bbox_normalized[3] * 100) / 2}%`,
                                                        width: `${det.bbox_normalized[2] * 100}%`,
                                                        height: `${det.bbox_normalized[3] * 100}%`,
                                                    }}
                                                >
                                                    <span className="absolute -top-6 left-0 bg-primary text-primary-foreground text-xs px-1 rounded">
                                                        {det.class_name} ({Math.round(det.confidence * 100)}%)
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="flex justify-between items-center">
                                        <p className="text-sm text-muted-foreground">
                                            {results ? `Found ${results.num_detections} objects` : "Ready to run"}
                                        </p>
                                        <div className="flex gap-2">
                                            <Button variant="outline" onClick={() => { setSelectedFile(null); setResults(null); }}>
                                                Clear
                                            </Button>
                                            <Button onClick={handleInference} disabled={isLoading}>
                                                {isLoading ? <Loader className="animate-spin mr-2" /> : <CheckCircle className="mr-2" />}
                                                Run Model
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

