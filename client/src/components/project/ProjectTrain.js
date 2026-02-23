"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Play, Cpu, Clock, RefreshCw, CheckCircle2, AlertCircle, Trash2 } from "lucide-react";
import { API_ENDPOINTS, API_BASE_URL } from "@/lib/config";
import { toast } from 'sonner';

export default function ProjectTrain({ dataset }) {
    const [config, setConfig] = useState({
        epochs: 50,
        batch_size: 16,
        img_size: 640,
        model_name: "yolov8n.pt",
        learning_rate: 0.01
    });
    const [training, setTraining] = useState(false);
    const [selectedClasses, setSelectedClasses] = useState([]);
    const [jobs, setJobs] = useState([]);

    // Initialize with all classes selected
    useState(() => {
        if (dataset?.classes) {
            setSelectedClasses([...dataset.classes]);
        }
    }, [dataset]);

    const toggleClass = (cls) => {
        if (selectedClasses.includes(cls)) {
            // Don't allow deselecting the last class
            if (selectedClasses.length <= 1) {
                toast.error("At least one class must be selected");
                return;
            }
            setSelectedClasses(selectedClasses.filter(c => c !== cls));
        } else {
            setSelectedClasses([...selectedClasses, cls]);
        }
    };

    const toggleAll = () => {
        if (selectedClasses.length === dataset.classes.length) {
            setSelectedClasses([...dataset.classes]);
        } else {
            setSelectedClasses([...dataset.classes]);
        }
    };

    const fetchJobs = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/training/jobs`);
            if (res.ok) {
                const data = await res.json();
                // Filter jobs for this dataset? The API currently returns all jobs.
                // It would be better to return jobs per dataset, but for now we show all or try to guess.
                // We'll show all jobs since the backend doesn't filter by dataset ID yet in the /jobs endpoint easily.
                setJobs(data.jobs || []);
            }
        } catch (e) {
            console.error("Failed to fetch jobs:", e);
        }
    };

    useEffect(() => {
        fetchJobs();
        const interval = setInterval(() => {
            fetchJobs();
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    const startTraining = async () => {
        setTraining(true);
        try {
            const response = await fetch(API_ENDPOINTS.TRAINING.START_FROM_DATASET, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    config: config,
                    classes: selectedClasses // Send selected classes
                })
            });

            const data = await response.json();
            if (data.success) {
                toast.success("Training started! Job ID: " + data.job_id);
                fetchJobs();
            } else {
                toast.error("Failed to start training: " + data.detail);
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setTraining(false);
        }
    };

    const deleteJob = async (jobId) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/training/job/${jobId}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                toast.success("Job deleted");
                fetchJobs();
            }
        } catch (e) {
            toast.error("Failed to delete job");
        }
    };

    return (
        <div className="h-full flex flex-col gap-6 overflow-y-auto pb-10 custom-scrollbar pr-2">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Train Model</h2>
                    <p className="text-muted-foreground text-sm">Train a YOLOv8 model on your dataset version.</p>
                </div>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
                <div className="md:col-span-2 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Configuration</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Model Architecture</Label>
                                    <Select
                                        value={config.model_name}
                                        onValueChange={v => setConfig({ ...config, model_name: v })}
                                    >
                                        <SelectTrigger>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="yolov8n.pt">YOLOv8 Nano (Fastest)</SelectItem>
                                            <SelectItem value="yolov8s.pt">YOLOv8 Small</SelectItem>
                                            <SelectItem value="yolov8m.pt">YOLOv8 Medium</SelectItem>
                                            <SelectItem value="yolov8l.pt">YOLOv8 Large (Most Accurate)</SelectItem>
                                            <SelectItem value="yolov9c.pt">YOLOv9 Compact</SelectItem>
                                            <SelectItem value="yolov9e.pt">YOLOv9 Extended</SelectItem>
                                            <SelectItem value="yolov10n.pt">YOLOv10 Nano</SelectItem>
                                            <SelectItem value="yolov10s.pt">YOLOv10 Small</SelectItem>
                                            <SelectItem value="yolo11n.pt">YOLO11 Nano</SelectItem>
                                            <SelectItem value="yolo11s.pt">YOLO11 Small</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Epochs</Label>
                                    <Input
                                        type="number"
                                        value={config.epochs}
                                        onChange={e => setConfig({ ...config, epochs: parseInt(e.target.value) })}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Batch Size</Label>
                                    <Input
                                        type="number"
                                        value={config.batch_size}
                                        onChange={e => setConfig({ ...config, batch_size: parseInt(e.target.value) })}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Image Size</Label>
                                    <Select
                                        value={config.img_size.toString()}
                                        onValueChange={v => setConfig({ ...config, img_size: parseInt(v) })}
                                    >
                                        <SelectTrigger>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="416">416</SelectItem>
                                            <SelectItem value="640">640</SelectItem>
                                            <SelectItem value="1024">1024</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex justify-between items-center">
                                <span>Class Selection</span>
                                <Button variant="ghost" size="sm" onClick={toggleAll}>
                                    Select All ({dataset.classes?.length})
                                </Button>
                            </CardTitle>
                            <CardDescription>Select which classes to include in training</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-wrap gap-2">
                                {dataset.classes?.map((cls, i) => {
                                    const isSelected = selectedClasses.includes(cls);
                                    return (
                                        <Badge
                                            key={i}
                                            variant={isSelected ? "default" : "outline"}
                                            className="cursor-pointer text-sm py-1 px-3 hover:opacity-80 transition-all select-none"
                                            onClick={() => toggleClass(cls)}
                                        >
                                            {cls}
                                            {isSelected && <span className="ml-1">✓</span>}
                                        </Badge>
                                    );
                                })}
                            </div>
                            {selectedClasses.length === 0 && (
                                <p className="text-destructive text-sm mt-2">Please select at least one class.</p>
                            )}
                            <p className="text-muted-foreground text-xs mt-4">
                                {selectedClasses.length} of {dataset.classes?.length} classes selected.
                                Backend will create a temporary filtered dataset for this training job.
                            </p>
                        </CardContent>
                    </Card>

                    {/* Training Jobs Dashboard */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <div>
                                <CardTitle>Training Jobs</CardTitle>
                                <CardDescription>Monitor your current and previous training runs</CardDescription>
                            </div>
                            <Button variant="outline" size="icon" onClick={fetchJobs}>
                                <RefreshCw className="h-4 w-4" />
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {jobs.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground bg-muted/20 rounded-lg border border-dashed">
                                    <Cpu className="mx-auto h-8 w-8 mb-2 opacity-50" />
                                    <p>No training jobs found.</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {jobs.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)).map((job) => (
                                        <div key={job.job_id} className="border rounded-lg p-4 bg-card/50">
                                            <div className="flex justify-between items-start mb-2">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <h4 className="font-semibold text-sm">
                                                            {job.config?.model_name || 'Model'}
                                                            {job.strict_mode && <Badge variant="outline" className="ml-2 text-[10px] h-4 leading-none">Strict Mode</Badge>}
                                                        </h4>
                                                        {job.status === "running" && (
                                                            <Badge variant="secondary" className="bg-blue-500/10 text-blue-500 border-blue-500/20 flex items-center gap-1">
                                                                <RefreshCw className="h-3 w-3 animate-spin" /> Running
                                                            </Badge>
                                                        )}
                                                        {(job.status === "completed" || job.status === "success") && (
                                                            <Badge variant="secondary" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 flex items-center gap-1">
                                                                <CheckCircle2 className="h-3 w-3" /> Completed
                                                            </Badge>
                                                        )}
                                                        {job.status === "failed" && (
                                                            <Badge variant="secondary" className="bg-red-500/10 text-red-500 border-red-500/20 flex items-center gap-1">
                                                                <AlertCircle className="h-3 w-3" /> Failed
                                                            </Badge>
                                                        )}
                                                        {job.status === "pending" && (
                                                            <Badge variant="outline" className="text-muted-foreground flex items-center gap-1">
                                                                <Clock className="h-3 w-3" /> Pending
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-muted-foreground mt-1">Job ID: {job.job_id.substring(0, 8)}... | Epochs: {job.config?.epochs}</p>
                                                </div>
                                                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-red-400" onClick={() => deleteJob(job.job_id)}>
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>

                                            {job.status === "running" && (
                                                <div className="mt-3">
                                                    <div className="flex justify-between text-xs mb-1">
                                                        <span>Epoch {job.current_epoch || 0} / {job.config?.epochs || '?'}</span>
                                                        <span>{Math.round(job.progress || 0)}%</span>
                                                    </div>
                                                    <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                                                        <div
                                                            className="bg-primary h-2 rounded-full transition-all duration-500"
                                                            style={{ width: `${Math.max(5, job.progress || 0)}%` }}
                                                        />
                                                    </div>

                                                    {job.metrics && Object.keys(job.metrics).length > 0 && (
                                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-xs">
                                                            {Object.entries(job.metrics).map(([key, value]) => (
                                                                <div key={key} className="bg-muted/30 p-2 rounded flex flex-col">
                                                                    <span className="text-muted-foreground truncate" title={key}>{key.split('/').pop()}</span>
                                                                    <span className="font-semibold">{typeof value === 'number' ? value.toFixed(4) : value}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {job.status === "failed" && (
                                                <div className="mt-2 text-xs text-red-400 p-2 bg-red-500/10 rounded">
                                                    {job.error || "Unknown error occurred"}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>

                <div className="space-y-6">
                    <Card className="bg-muted/30">
                        <CardContent className="p-6">
                            <h3 className="font-semibold mb-4">Training Estimates</h3>
                            <div className="space-y-3 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground flex items-center gap-2">
                                        <Cpu /> GPU
                                    </span>
                                    <span>T4 (Free)</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground flex items-center gap-2">
                                        <Clock /> Time
                                    </span>
                                    <span>~{(config.epochs * 0.5 * (selectedClasses.length / (dataset.classes?.length || 1))).toFixed(1)} mins</span>
                                </div>
                            </div>

                            <Button
                                className="w-full mt-6"
                                onClick={startTraining}
                                disabled={training || selectedClasses.length === 0}
                            >
                                {training ? "Starting..." : "Start Training"}
                                {!training && <Play className="ml-2" />}
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
