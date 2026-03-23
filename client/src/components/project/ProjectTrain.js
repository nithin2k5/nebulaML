"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Play, Cpu, Clock, AlertCircle } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";
import ProjectVersions from "@/components/project/ProjectVersions";

export default function ProjectTrain({ dataset, onTrainingStarted }) {
    const { token } = useAuth();
    const [versions, setVersions] = useState([]);
    const [selectedVersion, setSelectedVersion] = useState("");
    const [config, setConfig] = useState({
        epochs: 50,
        batch_size: 16,
        img_size: 640,
        model_name: "yolov8n.pt",
        learning_rate: 0.01
    });
    const [training, setTraining] = useState(false);
    const [selectedClasses, setSelectedClasses] = useState([]);

    // Initialize with all classes selected
    useEffect(() => {
        if (dataset?.classes) {
            setSelectedClasses([...dataset.classes]);
        }
    }, [dataset]);

    // Fetch dataset versions
    useEffect(() => {
        const fetchVersions = async () => {
            try {
                const res = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_LIST(dataset.id), {
                    headers: { "Authorization": `Bearer ${token}` }
                });
                if (res.ok) {
                    const data = await res.json();
                    setVersions(data.versions || []);
                    if (data.versions?.length > 0) {
                        setSelectedVersion(data.versions[0].id);
                    }
                }
            } catch(e) { console.error("Failed to fetch versions:", e); }
        };
        fetchVersions();
    }, [dataset.id, token]);

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

    const startTraining = async () => {
        if (!selectedVersion) {
            toast.error("Please select a dataset version first.");
            return;
        }
        setTraining(true);
        try {
            const response = await fetch(API_ENDPOINTS.TRAINING.START_FROM_DATASET, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}` 
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    version_id: selectedVersion,
                    config: config,
                    classes: selectedClasses // Send selected classes
                })
            });

            const data = await response.json();
            if (data.success) {
                toast.success("Training started! Job ID: " + data.job_id);
                if (onTrainingStarted) onTrainingStarted();
            } else {
                toast.error("Failed to start training: " + data.detail);
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setTraining(false);
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
                            <div className="space-y-2 mb-6 p-4 bg-muted/30 rounded-lg border border-border">
                                <Label className="text-base font-semibold">Dataset Version</Label>
                                {versions.length > 0 ? (
                                    <Select value={selectedVersion} onValueChange={setSelectedVersion}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select a version to train on" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {versions.map((ver) => (
                                                <SelectItem key={ver.id} value={ver.id.toString()}>
                                                    {ver.name} - {new Date(ver.created_at).toLocaleDateString()} ({ver.images_count} imgs)
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : (
                                    <div className="flex items-center text-amber-500 text-sm mt-2">
                                        <AlertCircle className="w-4 h-4 mr-2" />
                                        No dataset versions created yet. Please go to the Generate tab to create one before training.
                                    </div>
                                )}
                            </div>
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
                    {/* Jobs dashboard moved to ProjectVersions.js */}
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
                                disabled={training || selectedClasses.length === 0 || !selectedVersion}
                            >
                                {training ? "Starting..." : "Start Training"}
                                {!training && <Play className="ml-2" />}
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>

            {/* Model Registry & Jobs */}
            <div className="mt-8">
                <ProjectVersions dataset={dataset} onDeploy={() => {
                    // Navigate to deploy stage if it exists in route query or just trigger refresh
                    toast.info("Please navigate to the Deploy tab to deploy your model.");
                }} />
            </div>
        </div>
    );
}
