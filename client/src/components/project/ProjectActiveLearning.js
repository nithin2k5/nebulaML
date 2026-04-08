"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { RefreshCw, Brain, CheckCircle, ArrowRight, Loader, Eye, Sparkles, XCircle, Layers, Cpu } from "lucide-react";
import { API_BASE_URL, API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectActiveLearning({ dataset, onNavigate }) {
    const { token } = useAuth();
    const [uncertainImages, setUncertainImages] = useState([]);
    const [collecting, setCollecting] = useState(false);
    const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);
    const [jobId, setJobId] = useState("");
    const [completedJobs, setCompletedJobs] = useState([]);
    const [selectedImages, setSelectedImages] = useState(new Set());
    const [approvedCount, setApprovedCount] = useState(0);
    const [showRetrainBanner, setShowRetrainBanner] = useState(false);

    const fetchCompletedJobs = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                const jobs = (data.jobs || []).filter(
                    j => j.dataset_id === dataset.id && (j.status === "completed" || j.status === "success")
                );
                setCompletedJobs(jobs);
                if (jobs.length > 0) setJobId(jobs[0].job_id);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const fetchUncertain = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.ACTIVE_LEARNING.UNCERTAIN(dataset.id), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setUncertainImages(data.images || []);
            }
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchCompletedJobs();
        fetchUncertain();
    }, [dataset.id]);

    const handleCollect = async () => {
        if (!jobId) {
            toast.error("Please select a trained model");
            return;
        }
        setCollecting(true);
        try {
            const res = await fetch(API_ENDPOINTS.ACTIVE_LEARNING.COLLECT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    model_job_id: jobId,
                    confidence_threshold: confidenceThreshold,
                    max_images: 50
                })
            });

            if (res.ok) {
                const data = await res.json();
                toast.success(`Found ${data.uncertain_count} uncertain images`);
                fetchUncertain();
            } else {
                const err = await res.json();
                toast.error(err.detail || "Failed to collect predictions");
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setCollecting(false);
        }
    };

    const handleReject = async () => {
        const toReject = [...selectedImages];
        if (toReject.length === 0) {
            toast.error("No images selected");
            return;
        }
        try {
            const res = await fetch(API_ENDPOINTS.ACTIVE_LEARNING.REJECT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    image_ids: toReject
                })
            });
            if (res.ok) {
                const data = await res.json();
                toast.success(`Rejected ${data.rejected_count} images`);
                setSelectedImages(new Set());
                fetchUncertain();
            } else {
                const err = await res.json();
                toast.error(err.detail || "Failed to reject images");
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        }
    };

    const handleApprove = async () => {
        const toApprove = uncertainImages
            .filter(img => selectedImages.has(img.image_id))
            .map(img => ({
                image_id: img.image_id,
                filename: img.filename,
                width: 640,
                height: 640,
                boxes: [...img.low_confidence_detections, ...img.high_confidence_detections]
            }));

        if (toApprove.length === 0) {
            toast.error("No images selected");
            return;
        }

        try {
            const res = await fetch(API_ENDPOINTS.ACTIVE_LEARNING.APPROVE, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    predictions: toApprove
                })
            });

            if (res.ok) {
                const data = await res.json();
                setApprovedCount(data.approved_count);
                toast.success(`Approved ${data.approved_count} images`);
                setSelectedImages(new Set());
                fetchUncertain();
                setShowRetrainBanner(true);
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        }
    };

    const toggleSelect = (imageId) => {
        const next = new Set(selectedImages);
        if (next.has(imageId)) next.delete(imageId);
        else next.add(imageId);
        setSelectedImages(next);
    };

    const selectAll = () => {
        if (selectedImages.size === uncertainImages.length) {
            setSelectedImages(new Set());
        } else {
            setSelectedImages(new Set(uncertainImages.map(i => i.image_id)));
        }
    };

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Active Learning</h2>
                    <p className="text-muted-foreground text-sm">
                        Collect low-confidence predictions, review, and re-train to improve your model.
                    </p>
                </div>
            </div>

            {/* Pipeline Visualization */}
            <div className="flex items-center gap-3 p-4 rounded-lg border border-border bg-muted/20">
                <div className="flex items-center gap-2 text-sm flex-wrap">
                    <Badge variant="outline" className="gap-1"><Brain className="w-3 h-3" />Deploy Model</Badge>
                    <ArrowRight className="w-4 h-4 text-muted-foreground" />
                    <Badge variant="outline" className="gap-1"><Eye className="w-3 h-3" />Collect Uncertain</Badge>
                    <ArrowRight className="w-4 h-4 text-muted-foreground" />
                    <Badge variant="outline" className="gap-1"><CheckCircle className="w-3 h-3" />Review & Approve</Badge>
                    <ArrowRight className="w-4 h-4 text-muted-foreground" />
                    <Badge variant="outline" className="gap-1"><RefreshCw className="w-3 h-3" />Re-train</Badge>
                </div>
            </div>

            {/* Re-train CTA Banner (shown after approval) */}
            {showRetrainBanner && (
                <div className="flex items-center justify-between p-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10">
                    <div className="flex items-center gap-3">
                        <Sparkles className="w-5 h-5 text-emerald-500 shrink-0" />
                        <div>
                            <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
                                {approvedCount} image{approvedCount !== 1 ? "s" : ""} approved and merged into training data!
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Option A: Generate a new dataset version, then train. &nbsp;|&nbsp; Option B: Re-train directly on the current version.
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => { setShowRetrainBanner(false); onNavigate?.("generate"); }}
                        >
                            <Layers className="w-4 h-4 mr-1.5" />
                            New Version
                        </Button>
                        <Button
                            size="sm"
                            onClick={() => { setShowRetrainBanner(false); onNavigate?.("train"); }}
                        >
                            <Cpu className="w-4 h-4 mr-1.5" />
                            Re-train Now
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setShowRetrainBanner(false)}>Dismiss</Button>
                    </div>
                </div>
            )}

            {/* Collection Controls */}
            <Card>
                <CardHeader>
                    <CardTitle>Collect Uncertain Predictions</CardTitle>
                    <CardDescription>Scan images with your trained model and flag low-confidence detections</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Trained Model</Label>
                            {completedJobs.length === 0 ? (
                                <p className="text-sm text-muted-foreground py-2">No trained models yet. Go to the Train tab first.</p>
                            ) : (
                                <Select value={jobId} onValueChange={setJobId}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select a trained model" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {completedJobs.map(job => (
                                            <SelectItem key={job.job_id} value={job.job_id}>
                                                {job.config?.model_name || "Unknown Model"} — {job.created_at ? new Date(job.created_at).toLocaleDateString() : "Unknown date"}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            )}
                        </div>
                        <div className="space-y-2">
                            <Label>Confidence Threshold: {confidenceThreshold.toFixed(2)}</Label>
                            <Slider
                                min={0.1}
                                max={0.9}
                                step={0.05}
                                value={[confidenceThreshold]}
                                onValueChange={([v]) => setConfidenceThreshold(v)}
                            />
                            <p className="text-xs text-muted-foreground">
                                Predictions below this confidence are flagged for review
                            </p>
                        </div>
                    </div>
                    <Button onClick={handleCollect} disabled={collecting || !jobId}>
                        {collecting ? <Loader className="mr-2 animate-spin w-4 h-4" /> : <Brain className="mr-2 w-4 h-4" />}
                        {collecting ? "Scanning..." : "Scan for Uncertain Images"}
                    </Button>
                </CardContent>
            </Card>

            {/* Review Section */}
            {uncertainImages.length > 0 && (
                <Card>
                    <CardHeader>
                        <div className="flex justify-between items-center">
                            <div>
                                <CardTitle>Review Uncertain Images ({uncertainImages.length})</CardTitle>
                                <CardDescription>Review and approve predictions to add to training data</CardDescription>
                            </div>
                            <div className="flex gap-2">
                                <Button variant="outline" size="sm" onClick={selectAll}>
                                    {selectedImages.size === uncertainImages.length ? "Deselect All" : "Select All"}
                                </Button>
                                <Button
                                    size="sm"
                                    variant="destructive"
                                    onClick={handleReject}
                                    disabled={selectedImages.size === 0}
                                >
                                    <XCircle className="mr-2 w-4 h-4" />
                                    Reject ({selectedImages.size})
                                </Button>
                                <Button size="sm" onClick={handleApprove} disabled={selectedImages.size === 0}>
                                    <CheckCircle className="mr-2 w-4 h-4" />
                                    Approve ({selectedImages.size})
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                            {uncertainImages.map((img) => (
                                <div
                                    key={img.image_id}
                                    onClick={() => toggleSelect(img.image_id)}
                                    className={`relative group rounded-lg border-2 p-2 cursor-pointer transition-all ${selectedImages.has(img.image_id)
                                            ? "border-primary bg-primary/5"
                                            : "border-border hover:border-primary/50"
                                        }`}
                                >
                                    <div className="aspect-square bg-muted rounded overflow-hidden mb-2">
                                        <img
                                            src={`${API_BASE_URL}/api/annotations/image/${dataset.id}/${img.filename}`}
                                            alt={img.filename}
                                            className="w-full h-full object-cover"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <p className="text-xs font-medium truncate">{img.filename}</p>
                                        <div className="flex gap-1 flex-wrap">
                                            <Badge variant="destructive" className="text-[10px]">
                                                {img.low_confidence_detections?.length || 0} uncertain
                                            </Badge>
                                            <Badge variant="secondary" className="text-[10px]">
                                                {img.high_confidence_detections?.length || 0} confident
                                            </Badge>
                                        </div>
                                        {img.min_confidence > 0 && (
                                            <p className="text-[10px] text-muted-foreground">
                                                Min conf: {(img.min_confidence * 100).toFixed(1)}%
                                            </p>
                                        )}
                                    </div>
                                    {selectedImages.has(img.image_id) && (
                                        <div className="absolute top-3 right-3 w-6 h-6 bg-primary rounded-full flex items-center justify-center">
                                            <CheckCircle className="w-4 h-4 text-primary-foreground" />
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {uncertainImages.length === 0 && (
                <Card className="border-dashed">
                    <CardContent className="p-12 text-center">
                        <Brain className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                        <h3 className="font-semibold mb-2">No Uncertain Images</h3>
                        <p className="text-muted-foreground text-sm">
                            {completedJobs.length > 0
                                ? "Select a model above and scan your dataset to find images that need review."
                                : "Train a model first, then come back to run active learning."}
                        </p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
