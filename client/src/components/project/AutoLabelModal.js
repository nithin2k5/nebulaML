"use client";

import { useState, useEffect } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from "@/components/ui/select";
import { Loader2, Sparkles, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { API_ENDPOINTS } from "@/lib/config";

export default function AutoLabelModal({ isOpen, onClose, datasetId, onComplete }) {
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [models, setModels] = useState([]);
    const [selectedModel, setSelectedModel] = useState("yolov8n.pt");
    const [confidence, setConfidence] = useState(0.25);
    const [target, setTarget] = useState("all"); // 'all' or 'unlabeled' (though currently backend supports 'all' or 'ids')

    useEffect(() => {
        if (isOpen) {
            fetchModels();
        }
    }, [isOpen]);

    const fetchModels = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.MODELS.LIST);
            if (res.ok) {
                const data = await res.json();
                setModels(data.models || []);
            }
        } catch (error) {
            console.error("Failed to fetch models:", error);
        }
    };

    const handleAutoLabel = async () => {
        setLoading(true);
        try {
            const formData = new FormData();
            formData.append("dataset_id", datasetId);
            formData.append("image_ids", "all"); // For now, we only support labeling all images in the frontend UI
            formData.append("model_name", selectedModel);
            formData.append("confidence", confidence);

            const res = await fetch(`${API_ENDPOINTS.BASE}/annotations/auto-label`, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) throw new Error("Auto-labeling failed");

            const data = await res.json();
            if (data.job_id) {
                const interval = setInterval(async () => {
                    try {
                        const statusRes = await fetch(`${API_ENDPOINTS.BASE}/annotations/datasets/${datasetId}/auto-label-status/${data.job_id}`);
                        if (statusRes.ok) {
                            const statusData = await statusRes.json();
                            if (statusData.status === "completed") {
                                clearInterval(interval);
                                toast.success(`Successfully auto-labeled ${statusData.labeled_count} images!`, {
                                    description: "Review them and approve to finalize.",
                                    icon: <Sparkles className="h-4 w-4 text-amber-500" />,
                                });
                                setLoading(false);
                                setProgress(0);
                                onComplete?.();
                                onClose();
                            } else if (statusData.status === "failed") {
                                clearInterval(interval);
                                toast.error("Auto-label failed", { description: statusData.error });
                                setLoading(false);
                                setProgress(0);
                            } else {
                                setProgress(statusData.progress || 0);
                            }
                        }
                    } catch (e) {
                        console.error("Polling error:", e);
                    }
                }, 1000);
            } else {
                toast.success(`Successfully auto-labeled ${data.labeled_count} images!`);
                setLoading(false);
                onComplete?.();
                onClose();
            }
        } catch (error) {
            toast.error("Failed to start auto-labeling", {
                description: error.message
            });
            setLoading(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[425px] glass-panel border-white/10">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-indigo-400" />
                        AI Auto-Labeling
                    </DialogTitle>
                    <DialogDescription>
                        Use a pre-trained model to automatically generate bounding boxes for your images.
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    <div className="grid gap-2">
                        <Label>Model</Label>
                        <Select value={selectedModel} onValueChange={setSelectedModel}>
                            <SelectTrigger className="bg-background/50 border-white/10">
                                <SelectValue placeholder="Select model" />
                            </SelectTrigger>
                            <SelectContent>
                                {models.map((model) => (
                                    <SelectItem key={model.name} value={model.name}>
                                        {model.name} ({model.size})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                            Choose a model that best matches your object classes.
                        </p>
                    </div>

                    <div className="grid gap-2">
                        <Label>Confidence Threshold: {Math.round(confidence * 100)}%</Label>
                        <Slider
                            value={[confidence]}
                            onValueChange={([val]) => setConfidence(val)}
                            min={0.1}
                            max={0.9}
                            step={0.05}
                            className="py-2"
                        />
                    </div>

                    <div className="bg-amber-500/10 border border-amber-500/20 rounded-md p-3 text-sm flex gap-2 text-amber-200/90">
                        <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                        <p>
                            Auto-labeled boxes will be marked as &quot;Predicted&quot;. You should review and approve them.
                        </p>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="ghost" onClick={onClose} disabled={loading}>
                        Cancel
                    </Button>
                    <Button
                        onClick={handleAutoLabel}
                        disabled={loading}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2 relative overflow-hidden"
                    >
                        {loading && (
                            <div
                                className="absolute left-0 top-0 bottom-0 bg-white/20 transition-all duration-300 pointer-events-none"
                                style={{ width: `${progress}%` }}
                            />
                        )}
                        {loading ? (
                            <>
                                <Loader2 className="h-4 w-4 animate-spin z-10" />
                                <span className="z-10">Processing {progress}%</span>
                            </>
                        ) : (
                            <>
                                <Sparkles className="h-4 w-4" />
                                Start Auto-Labeling
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
