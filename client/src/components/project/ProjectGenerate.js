"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Layers, RefreshCw, Eye, Download } from "lucide-react";
import { toast } from 'sonner';
import { API_BASE_URL, API_ENDPOINTS } from "@/lib/config";
import { useAuth } from "@/context/AuthContext";

export default function ProjectGenerate({ dataset, stats, onGenerate }) {
    const { token } = useAuth();
    const [augmentations, setAugmentations] = useState({
        flipHorizontal: false,
        flipVertical: false,
        rotate: false,
        blur: false,
        noise: false
    });
    const [generating, setGenerating] = useState(false);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [previewData, setPreviewData] = useState(null);
    const [exportFormat, setExportFormat] = useState("yolo");

    const handleGenerate = async () => {
        // Annotation QA Gate
        if (!stats || stats.total_images === 0) {
            toast.error("QA Error: Dataset is empty. Please upload some images first.");
            return;
        }
        
        if (stats.annotated_images < stats.total_images) {
            const missing = stats.total_images - stats.annotated_images;
            toast.error(`QA Error: ${missing} images are still missing annotations. Please completely annotate the dataset before generating a version.`);
            return;
        }

        setGenerating(true);
        try {
            const response = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_GENERATE, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    name: `Version ${new Date().toLocaleDateString()}`,
                    preprocessing: {},
                    augmentations: augmentations
                })
            });

            if (response.ok) {
                toast.success("Version generated successfully! Head to Train tab.");
                if (onGenerate) onGenerate();
            } else {
                toast.error("Failed to generate version");
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setGenerating(false);
        }
    };

    const handlePreview = async () => {
        setPreviewLoading(true);
        try {
            const response = await fetch(API_ENDPOINTS.TRAINING.PREVIEW_AUGMENTATION, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    preprocessing: {},
                    augmentations: augmentations
                })
            });

            if (response.ok) {
                const data = await response.json();
                setPreviewData(data);
            } else {
                toast.error("Preview failed");
            }
        } catch (e) {
            toast.error("Preview error: " + e.message);
        } finally {
            setPreviewLoading(false);
        }
    };

    const handleDownloadFormat = () => {
        const url = API_ENDPOINTS.DATASETS.DOWNLOAD_FORMAT(dataset.id, exportFormat);
        window.open(url, "_blank");
    };

    const exportFormats = [
        { value: "yolo", label: "YOLO", desc: "Ultralytics format" },
        { value: "coco", label: "COCO JSON", desc: "MS COCO format" },
        { value: "voc", label: "Pascal VOC", desc: "XML annotations" },
        { value: "csv", label: "CSV", desc: "Spreadsheet format" },
        { value: "createml", label: "CreateML", desc: "Apple CoreML" },
    ];

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Generate Version</h2>
                    <p className="text-muted-foreground text-sm">Apply augmentations, preview, and freeze your dataset for training.</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={handlePreview} disabled={previewLoading}>
                        {previewLoading ? <RefreshCw className="mr-2 animate-spin w-4 h-4" /> : <Eye className="mr-2 w-4 h-4" />}
                        Preview
                    </Button>
                    <Button onClick={handleGenerate} disabled={generating}>
                        {generating ? <RefreshCw className="mr-2 animate-spin w-4 h-4" /> : <Layers className="mr-2 w-4 h-4" />}
                        {generating ? "Generating..." : "Generate Version"}
                    </Button>
                </div>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
                {/* Pre-processing */}
                <Card>
                    <CardHeader>
                        <CardTitle>Preprocessing</CardTitle>
                        <CardDescription>Applied to all images</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center justify-between">
                            <Label>Auto-Orient</Label>
                            <Badge variant="secondary">Applied</Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <Label>Resize</Label>
                            <Badge variant="outline">640x640 (Stretch)</Badge>
                        </div>
                    </CardContent>
                </Card>

                {/* Augmentations */}
                <Card>
                    <CardHeader>
                        <CardTitle>Augmentations</CardTitle>
                        <CardDescription>Creates new training examples</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-5">
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Horizontal Flip</Label>
                                <p className="text-xs text-muted-foreground">Randomly flip images horizontally</p>
                            </div>
                            <Switch
                                checked={augmentations.flipHorizontal}
                                onCheckedChange={c => setAugmentations({ ...augmentations, flipHorizontal: c })}
                            />
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Vertical Flip</Label>
                                <p className="text-xs text-muted-foreground">Randomly flip images vertically</p>
                            </div>
                            <Switch
                                checked={augmentations.flipVertical}
                                onCheckedChange={c => setAugmentations({ ...augmentations, flipVertical: c })}
                            />
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Rotation</Label>
                                <p className="text-xs text-muted-foreground">Random rotation ±15°</p>
                            </div>
                            <Switch
                                checked={augmentations.rotate}
                                onCheckedChange={c => setAugmentations({ ...augmentations, rotate: c })}
                            />
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Blur</Label>
                                <p className="text-xs text-muted-foreground">Apply gaussian blur</p>
                            </div>
                            <Switch
                                checked={augmentations.blur}
                                onCheckedChange={c => setAugmentations({ ...augmentations, blur: c })}
                            />
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Grayscale</Label>
                                <p className="text-xs text-muted-foreground">Convert to black and white</p>
                            </div>
                            <Switch
                                checked={augmentations.noise}
                                onCheckedChange={c => setAugmentations({ ...augmentations, noise: c })}
                            />
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Augmentation Preview */}
            {previewData && (
                <Card>
                    <CardHeader>
                        <CardTitle>Augmentation Preview</CardTitle>
                        <CardDescription>Random sample: {previewData.original?.filename}</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <p className="text-sm font-medium mb-2 text-center">Original</p>
                                <div className="rounded-lg overflow-hidden border border-border bg-muted">
                                    <img
                                        src={`data:image/jpeg;base64,${previewData.original.base64}`}
                                        alt="Original"
                                        className="w-full h-auto"
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground text-center mt-1">
                                    {previewData.original.width}×{previewData.original.height}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm font-medium mb-2 text-center">Augmented</p>
                                <div className="rounded-lg overflow-hidden border border-primary/50 bg-muted">
                                    <img
                                        src={`data:image/jpeg;base64,${previewData.augmented.base64}`}
                                        alt="Augmented"
                                        className="w-full h-auto"
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground text-center mt-1">
                                    {previewData.augmented.width}×{previewData.augmented.height}
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Export Format Selection */}
            <Card>
                <CardHeader>
                    <CardTitle>Export Format</CardTitle>
                    <CardDescription>Download annotations in different formats</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-2 mb-4">
                        {exportFormats.map(fmt => (
                            <button
                                key={fmt.value}
                                onClick={() => setExportFormat(fmt.value)}
                                className={`px-3 py-2 rounded-lg border text-sm transition-all ${exportFormat === fmt.value
                                        ? "border-primary bg-primary/10 text-primary"
                                        : "border-border hover:border-primary/50"
                                    }`}
                            >
                                <span className="font-medium">{fmt.label}</span>
                                <span className="text-xs text-muted-foreground ml-1">({fmt.desc})</span>
                            </button>
                        ))}
                    </div>
                    <Button variant="outline" onClick={handleDownloadFormat}>
                        <Download className="mr-2 w-4 h-4" />
                        Download as {exportFormats.find(f => f.value === exportFormat)?.label}
                    </Button>
                </CardContent>
            </Card>

            <Card className="bg-muted/30 border-dashed">
                <CardContent className="p-6 text-center">
                    <h3 className="font-semibold mb-2">Estimated Version Size</h3>
                    <p className="text-muted-foreground">
                        {stats?.train_images || 0} → ~{Math.round((stats?.train_images || 0) * (1 + Object.values(augmentations).filter(Boolean).length * 0.5))} images
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
