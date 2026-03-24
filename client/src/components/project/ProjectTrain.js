"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Play, Cpu, Clock, AlertCircle, Zap, Scale, Target, ShieldCheck, AlertTriangle, XCircle, CheckCircle2, Loader2 } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";
import ProjectVersions from "@/components/project/ProjectVersions";
import TrainingLive from "@/components/project/TrainingLive";

const PRESET_META = {
    fast: { icon: Zap, color: "text-amber-500", label: "Fast", desc: "~5 min • Quick iteration, lower accuracy", epochs: 25, batch_size: 32, img_size: 416, model_name: "yolov8n.pt", learning_rate: 0.01, patience: 10 },
    balanced: { icon: Scale, color: "text-blue-500", label: "Balanced", desc: "~30 min • Good speed/accuracy tradeoff", epochs: 100, batch_size: 16, img_size: 640, model_name: "yolov8s.pt", learning_rate: 0.01, patience: 50 },
    accurate: { icon: Target, color: "text-emerald-500", label: "Accurate", desc: "~2 hrs • Maximum accuracy for production", epochs: 300, batch_size: 8, img_size: 1024, model_name: "yolov8m.pt", learning_rate: 0.001, patience: 80 },
};

export default function ProjectTrain({ dataset, onTrainingStarted, versionRefreshKey = 0 }) {
    const { token } = useAuth();
    const [versions, setVersions] = useState([]);
    const [selectedVersion, setSelectedVersion] = useState("");
    const [activePreset, setActivePreset] = useState("balanced");
    const [config, setConfig] = useState({
        epochs: 100,
        batch_size: 16,
        img_size: 640,
        model_name: "yolov8s.pt",
        learning_rate: 0.01
    });
    const [training, setTraining] = useState(false);
    const [selectedClasses, setSelectedClasses] = useState([]);
    const [preflight, setPreflight] = useState(null);
    const [preflightLoading, setPreflightLoading] = useState(false);
    const [activeJobId, setActiveJobId] = useState(null);

    // Initialize with all classes selected
    useEffect(() => {
        if (dataset?.classes) {
            setSelectedClasses([...dataset.classes]);
        }
    }, [dataset]);

    // Apply preset on change
    useEffect(() => {
        if (activePreset && PRESET_META[activePreset]) {
            const p = PRESET_META[activePreset];
            setConfig({
                epochs: p.epochs,
                batch_size: p.batch_size,
                img_size: p.img_size,
                model_name: p.model_name,
                learning_rate: p.learning_rate
            });
        }
    }, [activePreset]);

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
    }, [dataset.id, token, versionRefreshKey]);

    // Run preflight check when version changes
    useEffect(() => {
        if (dataset?.id) runPreflight();
    }, [dataset?.id, selectedVersion]);

    const runPreflight = async () => {
        setPreflightLoading(true);
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.PREFLIGHT(dataset.id), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setPreflight(data);
            }
        } catch(e) { console.error("Preflight failed:", e); }
        finally { setPreflightLoading(false); }
    };

    const toggleClass = (cls) => {
        if (selectedClasses.includes(cls)) {
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
            setSelectedClasses([]);
        } else {
            setSelectedClasses([...dataset.classes]);
        }
    };

    const startTraining = async () => {
        if (!selectedVersion) {
            toast.error("Please select a dataset version first.");
            return;
        }
        if (preflight && !preflight.can_train) {
            toast.error("Fix blocking issues before training.");
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
                    config: { ...config, preset: activePreset },
                    classes: selectedClasses
                })
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || `Server error ${response.status}`);
            }
            const data = await response.json();
            if (data.success) {
                toast.success("Training started!");
                setActiveJobId(data.job_id);
                if (onTrainingStarted) onTrainingStarted();
            } else {
                toast.error("Failed to start training: " + (data.detail || "Unknown error"));
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setTraining(false);
        }
    };

    // If we have an active job, show the live training view
    if (activeJobId) {
        return (
            <div className="h-full flex flex-col gap-6 overflow-y-auto pb-10 custom-scrollbar pr-2">
                <TrainingLive 
                    jobId={activeJobId} 
                    dataset={dataset}
                    onBack={() => setActiveJobId(null)} 
                />
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col gap-6 overflow-y-auto pb-10 custom-scrollbar pr-2">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Train Model</h2>
                    <p className="text-muted-foreground text-sm">Train a YOLO model on your dataset version.</p>
                </div>
            </div>

            {/* Pre-flight Check Banner */}
            {preflightLoading && (
                <div className="p-3 rounded-lg border border-border bg-muted/30 flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin" /> Running pre-flight checks...
                </div>
            )}
            {preflight && !preflightLoading && (
                <div className="space-y-2">
                    {/* Quality Score */}
                    <div className={`p-3 rounded-lg border flex items-center justify-between ${
                        preflight.quality_score >= 70 ? 'border-emerald-500/30 bg-emerald-500/5' :
                        preflight.quality_score >= 40 ? 'border-amber-500/30 bg-amber-500/5' : 
                        'border-red-500/30 bg-red-500/5'
                    }`}>
                        <div className="flex items-center gap-2">
                            <ShieldCheck className={`w-4 h-4 ${
                                preflight.quality_score >= 70 ? 'text-emerald-500' :
                                preflight.quality_score >= 40 ? 'text-amber-500' : 'text-red-500'
                            }`} />
                            <span className="text-sm font-medium">Dataset Quality Score</span>
                        </div>
                        <Badge variant={preflight.quality_score >= 70 ? "default" : "destructive"}>
                            {preflight.quality_score}/100
                        </Badge>
                    </div>

                    {/* Blockers */}
                    {preflight.blockers?.map((b, i) => (
                        <div key={`b-${i}`} className="p-3 rounded-lg border border-red-500/40 bg-red-500/10 flex items-start gap-2">
                            <XCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                            <div className="text-sm">
                                <span className="font-medium text-red-500">Blocker: </span>
                                {b.message}
                                <p className="text-muted-foreground text-xs mt-1">{b.suggestion}</p>
                            </div>
                        </div>
                    ))}

                    {/* Warnings */}
                    {preflight.warnings?.map((w, i) => (
                        <div key={`w-${i}`} className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5 flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                            <div className="text-sm">
                                <span className="font-medium text-amber-500">Warning: </span>
                                {w.message}
                                <p className="text-muted-foreground text-xs mt-1">{w.suggestion}</p>
                            </div>
                        </div>
                    ))}

                    {preflight.can_train && preflight.warnings?.length === 0 && preflight.blockers?.length === 0 && (
                        <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 flex items-center gap-2 text-sm">
                            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                            <span className="text-emerald-600 font-medium">All pre-flight checks passed!</span>
                        </div>
                    )}
                </div>
            )}

            <div className="grid md:grid-cols-3 gap-6">
                <div className="md:col-span-2 space-y-6">
                    {/* Presets */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Training Preset</CardTitle>
                            <CardDescription>Choose a preset or customize settings below</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-3 gap-3">
                                {Object.entries(PRESET_META).map(([key, p]) => {
                                    const Icon = p.icon;
                                    const isActive = activePreset === key;
                                    return (
                                        <button
                                            key={key}
                                            onClick={() => setActivePreset(key)}
                                            className={`p-4 rounded-lg border-2 transition-all text-left ${
                                                isActive 
                                                    ? 'border-primary bg-primary/5 shadow-sm' 
                                                    : 'border-border hover:border-muted-foreground/30'
                                            }`}
                                        >
                                            <Icon className={`w-5 h-5 mb-2 ${p.color}`} />
                                            <p className="font-semibold text-sm">{p.label}</p>
                                            <p className="text-xs text-muted-foreground mt-1">{p.desc}</p>
                                        </button>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Configuration */}
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
                                        onValueChange={v => { setConfig({ ...config, model_name: v }); setActivePreset(null); }}
                                    >
                                        <SelectTrigger>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="yolov8n.pt">YOLOv8 Nano (3.2M params, fastest)</SelectItem>
                                            <SelectItem value="yolov8s.pt">YOLOv8 Small (11.2M params)</SelectItem>
                                            <SelectItem value="yolov8m.pt">YOLOv8 Medium (25.9M params)</SelectItem>
                                            <SelectItem value="yolov8l.pt">YOLOv8 Large (43.7M params, most accurate)</SelectItem>
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
                                        min={1}
                                        max={1000}
                                        value={config.epochs}
                                        onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1) { setConfig({ ...config, epochs: v }); setActivePreset(null); } }}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Batch Size</Label>
                                    <Input
                                        type="number"
                                        min={1}
                                        max={128}
                                        value={config.batch_size}
                                        onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1) { setConfig({ ...config, batch_size: v }); setActivePreset(null); } }}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Image Size</Label>
                                    <Select
                                        value={config.img_size.toString()}
                                        onValueChange={v => { setConfig({ ...config, img_size: parseInt(v) }); setActivePreset(null); }}
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
                            </p>
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
                                {activePreset && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Preset</span>
                                        <Badge variant="outline" className="text-xs">{PRESET_META[activePreset]?.label}</Badge>
                                    </div>
                                )}
                                {preflight && (
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Quality</span>
                                        <Badge variant={preflight.quality_score >= 70 ? "default" : "destructive"} className="text-xs">
                                            {preflight.quality_score}/100
                                        </Badge>
                                    </div>
                                )}
                            </div>

                            <Button
                                className="w-full mt-6"
                                onClick={startTraining}
                                disabled={training || selectedClasses.length === 0 || !selectedVersion || (preflight && !preflight.can_train)}
                            >
                                {training ? "Starting..." : "Start Training"}
                                {!training && <Play className="ml-2" />}
                            </Button>
                            {preflight && !preflight.can_train && (
                                <p className="text-destructive text-xs mt-2 text-center">Fix blocking issues above before training</p>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>

            {/* Model Registry & Jobs */}
            <div className="mt-8">
                <ProjectVersions dataset={dataset} onDeploy={() => {
                    toast.info("Please navigate to the Deploy tab to deploy your model.");
                }} />
            </div>
        </div>
    );
}
