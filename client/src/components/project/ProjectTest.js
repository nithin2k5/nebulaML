"use client";

import { useState, useEffect, useRef } from "react";
import { API_ENDPOINTS } from "@/lib/config";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Upload, Play, Download, X, Grid3x3, Maximize2, AlertCircle, CheckCircle2, Loader2, RefreshCw, Image as ImageIcon } from "lucide-react";

export default function ProjectTest({ dataset }) {
    const { token } = useAuth();
    const [models, setModels] = useState([]);
    const [selectedModel, setSelectedModel] = useState(null);
    const [testImages, setTestImages] = useState([]);
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [viewMode, setViewMode] = useState("grid");
    const [selectedResult, setSelectedResult] = useState(null);
    const [confidence, setConfidence] = useState(0.25);
    const [iou, setIou] = useState(0.45);
    const canvasRef = useRef(null);
    const fileInputRef = useRef(null);

    // Cleanup object URLs on unmount to prevent memory leaks
    useEffect(() => {
        return () => {
            setTestImages(current => {
                current.forEach(img => URL.revokeObjectURL(img.url));
                return [];
            });
        };
    }, []);

    useEffect(() => {
        fetchModels();
    }, []);

    const fetchModels = async () => {
        try {
            // Fetch all trained models and training jobs in parallel
            const [modelsRes, jobsRes] = await Promise.all([
                fetch(API_ENDPOINTS.MODELS.LIST, { headers: { Authorization: `Bearer ${token}` } }),
                fetch(API_ENDPOINTS.TRAINING.JOBS, { headers: { Authorization: `Bearer ${token}` } })
            ]);

            if (!modelsRes.ok) throw new Error("Failed to fetch models");

            const modelsData = await modelsRes.json();
            const allModels = modelsData.models || [];

            // Build a set of job IDs that belong to this dataset (completed/cancelled with weights)
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

            // Filter models: keep those whose directory name matches a job from this dataset.
            // Fall back to all models if none match (e.g., dataset_id not stored).
            const datasetModels = datasetJobIds.size > 0
                ? allModels.filter(m => datasetJobIds.has(m.name))
                : allModels;

            setModels(datasetModels);
            if (datasetModels.length > 0) {
                setSelectedModel(datasetModels[0].name);
            }
        } catch (error) {
            console.error(error);
            toast.error("Failed to load models");
        }
    };

    const handleFileSelect = async (e) => {
        const files = Array.from(e.target.files || []);
        if (files.length === 0) return;

        setUploading(true);
        const newImages = [];

        for (const file of files) {
            if (!file.type.startsWith('image/')) continue;
            
            // Use createObjectURL instead of FileReader to save massive amounts of browser memory
            newImages.push({
                id: Math.random().toString(36).substr(2, 9),
                file,
                name: file.name,
                url: URL.createObjectURL(file),
                result: null,
                loading: false
            });
        }

        setTestImages(prev => [...prev, ...newImages]);
        setUploading(false);
        toast.success(`Added ${newImages.length} image${newImages.length > 1 ? 's' : ''}`);
    };

    const runInference = async (imageId) => {
        if (!selectedModel) {
            toast.error("Please select a model first");
            return;
        }

        const imageIdx = testImages.findIndex(img => img.id === imageId);
        if (imageIdx === -1) return;

        setTestImages(prev => {
            const updated = [...prev];
            updated[imageIdx] = { ...updated[imageIdx], loading: true };
            return updated;
        });

        try {
            const formData = new FormData();
            formData.append("file", testImages[imageIdx].file);
            formData.append("model_name", selectedModel);
            formData.append("confidence", confidence.toString());
            formData.append("iou", iou.toString());

            const res = await fetch(API_ENDPOINTS.INFERENCE.PREDICT, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
                body: formData
            });

            if (!res.ok) throw new Error("Inference failed");

            const result = await res.json();

            const normalizedResult = {
                predictions: (result.detections || []).map(det => ({
                    class: det.class_name || det.class,
                    confidence: det.confidence,
                    bbox: det.bbox || [],
                    polygon: det.polygon || null
                }))
            };

            setTestImages(prev => {
                const updated = [...prev];
                updated[imageIdx] = { 
                    ...updated[imageIdx], 
                    loading: false,
                    result: normalizedResult
                };
                return updated;
            });

            setResults(prev => [...prev, { imageId, result }]);
            toast.success("Inference complete");

        } catch (error) {
            console.error(error);
            toast.error("Inference failed: " + error.message);
            setTestImages(prev => {
                const updated = [...prev];
                updated[imageIdx] = { ...updated[imageIdx], loading: false };
                return updated;
            });
        }
    };

    const runBatchInference = async () => {
        if (testImages.length === 0) {
            toast.error("Please upload images first");
            return;
        }

        const pendingImages = testImages.filter(img => !img.result);
        if (pendingImages.length === 0) return;

        setLoading(true);
        
        // Mark all pending as loading
        setTestImages(prev => prev.map(img => 
            pendingImages.some(p => p.id === img.id) ? { ...img, loading: true } : img
        ));

        // Process in chunks of 20 (backend limit)
        const chunkSize = 20;
        let successCount = 0;

        for (let i = 0; i < pendingImages.length; i += chunkSize) {
            const chunk = pendingImages.slice(i, i + chunkSize);
            try {
                const formData = new FormData();
                formData.append("model_name", selectedModel);
                formData.append("confidence", confidence.toString());
                formData.append("iou", iou.toString());
                
                chunk.forEach(img => {
                    formData.append("files", img.file, img.name);
                });

                const res = await fetch(API_ENDPOINTS.INFERENCE.PREDICT_BATCH, {
                    method: "POST",
                    headers: { Authorization: `Bearer ${token}` },
                    body: formData
                });

                if (!res.ok) throw new Error(`Batch inference failed for chunk ${i}`);
                
                const data = await res.json();
                const newResults = [];

                setTestImages(prev => {
                    const updated = [...prev];
                    data.results.forEach((resultData, idx) => {
                        // Find matching image in original array
                        const img = chunk[idx];
                        const imgIdx = updated.findIndex(u => u.id === img.id);
                        
                        if (imgIdx !== -1) {
                            const normalizedResult = {
                                predictions: (resultData.detections || []).map(det => ({
                                    class: det.class_name || det.class,
                                    confidence: det.confidence,
                                    bbox: det.bbox || [],
                                    polygon: det.polygon || null
                                }))
                            };
                            
                            updated[imgIdx] = { 
                                ...updated[imgIdx], 
                                loading: false,
                                result: normalizedResult
                            };
                            
                            newResults.push({ imageId: img.id, result: normalizedResult });
                        }
                    });
                    return updated;
                });
                
                setResults(prev => [...prev, ...newResults]);
                successCount += chunk.length;

            } catch (error) {
                console.error(error);
                toast.error(error.message);
                
                // Unmark loading on failure for this chunk
                setTestImages(prev => prev.map(img => 
                    chunk.some(c => c.id === img.id) ? { ...img, loading: false } : img
                ));
            }
        }
        
        setLoading(false);
        if (successCount > 0) {
            toast.success(`Batch inference complete (${successCount} images)`);
        }
    };

    const removeImage = (imageId) => {
        setTestImages(prev => {
            const img = prev.find(i => i.id === imageId);
            if (img && img.url) URL.revokeObjectURL(img.url);
            return prev.filter(i => i.id !== imageId);
        });
        setResults(prev => prev.filter(r => r.imageId !== imageId));
        if (selectedResult?.id === imageId) {
            setSelectedResult(null);
        }
    };

    const clearAll = () => {
        testImages.forEach(img => {
            if (img.url) URL.revokeObjectURL(img.url);
        });
        setTestImages([]);
        setResults([]);
        setSelectedResult(null);
    };

    const downloadResults = () => {
        const resultsData = testImages
            .filter(img => img.result)
            .map(img => ({
                image: img.name,
                predictions: img.result.predictions || [],
                confidence_avg: img.result.predictions?.length > 0
                    ? (img.result.predictions.reduce((sum, p) => sum + p.confidence, 0) / img.result.predictions.length).toFixed(3)
                    : 0,
                count: img.result.predictions?.length || 0
            }));

        const blob = new Blob([JSON.stringify(resultsData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `test_results_${dataset.name}_${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success("Results downloaded");
    };

    const viewResult = (img) => {
        setSelectedResult(img);
        setTimeout(() => drawResult(img), 100);
    };

    const drawResult = (img) => {
        const canvas = canvasRef.current;
        if (!canvas || !img.result) return;

        const ctx = canvas.getContext('2d');
        const image = new Image();
        image.onload = () => {
            canvas.width = image.width;
            canvas.height = image.height;
            ctx.drawImage(image, 0, 0);

            const predictions = img.result.predictions || [];
            predictions.forEach((pred, idx) => {
                const color = `hsl(${(idx * 137.5) % 360}, 70%, 50%)`;
                
                if (pred.bbox && pred.bbox.length >= 4) {
                    // bbox is [x1, y1, x2, y2] in absolute pixel coords (xyxy format from YOLO)
                    const [x1, y1, x2, y2] = pred.bbox;
                    const bw = x2 - x1;
                    const bh = y2 - y1;
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 3;
                    ctx.strokeRect(x1, y1, bw, bh);

                    ctx.fillStyle = color;
                    ctx.globalAlpha = 0.2;
                    ctx.fillRect(x1, y1, bw, bh);
                    ctx.globalAlpha = 1.0;

                    const label = `${pred.class} ${(pred.confidence * 100).toFixed(1)}%`;
                    ctx.font = 'bold 14px Inter';
                    const textWidth = ctx.measureText(label).width;

                    ctx.fillStyle = color;
                    ctx.fillRect(x1, y1 - 24, textWidth + 12, 24);

                    ctx.fillStyle = '#fff';
                    ctx.fillText(label, x1 + 6, y1 - 6);
                }

                if (pred.polygon && Array.isArray(pred.polygon)) {
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    for (let i = 0; i < pred.polygon.length; i += 2) {
                        const px = pred.polygon[i];
                        const py = pred.polygon[i + 1];
                        if (i === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    }
                    ctx.closePath();
                    ctx.stroke();

                    ctx.fillStyle = color;
                    ctx.globalAlpha = 0.15;
                    ctx.fill();
                    ctx.globalAlpha = 1.0;
                }
            });
        };
        image.src = img.url;
    };

    useEffect(() => {
        if (selectedResult) {
            drawResult(selectedResult);
        }
    }, [selectedResult]);

    if (models.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
                    <AlertCircle className="w-8 h-8 text-muted-foreground" />
                </div>
                <div>
                    <h3 className="text-lg font-semibold">No Models Available</h3>
                    <p className="text-sm text-muted-foreground mt-1">Train a model first to test your dataset</p>
                </div>
                <Button onClick={() => window.location.href = `?tab=train`}>
                    Go to Train Tab
                </Button>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold">Test Dataset</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        Upload test images and run inference using your trained models
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {testImages.length > 0 && (
                        <>
                            <Button variant="outline" size="sm" onClick={clearAll}>
                                <X className="w-4 h-4 mr-2" />
                                Clear All
                            </Button>
                            {results.length > 0 && (
                                <Button variant="outline" size="sm" onClick={downloadResults}>
                                    <Download className="w-4 h-4 mr-2" />
                                    Export Results
                                </Button>
                            )}
                        </>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-1 space-y-4">
                    <div className="rounded-lg border bg-card p-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <h3 className="font-semibold">Model Selection</h3>
                            <Button variant="ghost" size="icon" onClick={fetchModels}>
                                <RefreshCw className="w-4 h-4" />
                            </Button>
                        </div>
                        <select
                            value={selectedModel || ""}
                            onChange={(e) => setSelectedModel(e.target.value)}
                            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                        >
                            {models.map(m => (
                                <option key={m.name} value={m.name}>
                                    {m.name}
                                </option>
                            ))}
                        </select>
                        {selectedModel && (
                            <div className="text-xs text-muted-foreground space-y-4 mt-4">
                                <div className="flex items-center justify-between">
                                    <span>Format:</span>
                                    <Badge variant="outline" className="text-xs">
                                        {models.find(m => m.name === selectedModel)?.format || 'PyTorch'}
                                    </Badge>
                                </div>
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <label className="font-medium text-foreground">Confidence Threshold</label>
                                        <span>{confidence.toFixed(2)}</span>
                                    </div>
                                    <input 
                                        type="range" 
                                        min="0.05" max="0.95" step="0.05" 
                                        value={confidence} 
                                        onChange={(e) => setConfidence(parseFloat(e.target.value))}
                                        className="w-full accent-primary"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <label className="font-medium text-foreground">IoU Threshold</label>
                                        <span>{iou.toFixed(2)}</span>
                                    </div>
                                    <input 
                                        type="range" 
                                        min="0.1" max="0.9" step="0.05" 
                                        value={iou} 
                                        onChange={(e) => setIou(parseFloat(e.target.value))}
                                        className="w-full accent-primary"
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="rounded-lg border bg-card p-4 space-y-3">
                        <h3 className="font-semibold">Upload Test Images</h3>
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept="image/*"
                            onChange={handleFileSelect}
                            className="hidden"
                        />
                        <Button
                            variant="outline"
                            className="w-full"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={uploading}
                        >
                            {uploading ? (
                                <>
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    Uploading...
                                </>
                            ) : (
                                <>
                                    <Upload className="w-4 h-4 mr-2" />
                                    Choose Images
                                </>
                            )}
                        </Button>
                        <p className="text-xs text-muted-foreground">
                            Upload images to test model performance
                        </p>
                    </div>

                    {testImages.length > 0 && (
                        <div className="rounded-lg border bg-card p-4 space-y-3">
                            <h3 className="font-semibold">Actions</h3>
                            <Button
                                className="w-full"
                                onClick={runBatchInference}
                                disabled={loading || !selectedModel}
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        Running...
                                    </>
                                ) : (
                                    <>
                                        <Play className="w-4 h-4 mr-2" />
                                        Run Batch Inference
                                    </>
                                )}
                            </Button>
                        </div>
                    )}

                    <div className="rounded-lg border bg-card p-4 space-y-2">
                        <h3 className="font-semibold text-sm">Stats</h3>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="flex flex-col">
                                <span className="text-muted-foreground">Images</span>
                                <span className="font-semibold text-lg">{testImages.length}</span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-muted-foreground">Tested</span>
                                <span className="font-semibold text-lg">{results.length}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="lg:col-span-2 space-y-4">
                    {testImages.length === 0 ? (
                        <div className="rounded-lg border-2 border-dashed bg-card h-96 flex flex-col items-center justify-center text-center p-8">
                            <ImageIcon className="w-12 h-12 text-muted-foreground mb-4" />
                            <h3 className="font-semibold text-lg mb-2">No Test Images</h3>
                            <p className="text-sm text-muted-foreground mb-4 max-w-md">
                                Upload images to test your trained model's performance and validate predictions
                            </p>
                            <Button onClick={() => fileInputRef.current?.click()}>
                                <Upload className="w-4 h-4 mr-2" />
                                Upload Images
                            </Button>
                        </div>
                    ) : selectedResult ? (
                        <div className="rounded-lg border bg-card overflow-hidden">
                            <div className="flex items-center justify-between p-4 border-b">
                                <div>
                                    <h3 className="font-semibold">{selectedResult.name}</h3>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        {selectedResult.result?.predictions?.length || 0} detection(s)
                                    </p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Button variant="outline" size="sm" onClick={() => setSelectedResult(null)}>
                                        <Grid3x3 className="w-4 h-4 mr-2" />
                                        Back to Grid
                                    </Button>
                                </div>
                            </div>
                            <div className="p-4 bg-muted/50 overflow-auto max-h-[calc(100vh-24rem)]">
                                <canvas
                                    ref={canvasRef}
                                    className="max-w-full h-auto border rounded bg-background"
                                />
                            </div>
                            {selectedResult.result && (
                                <div className="p-4 border-t space-y-2 max-h-48 overflow-auto">
                                    <h4 className="text-sm font-semibold">Predictions</h4>
                                    {(selectedResult.result.predictions || []).map((pred, idx) => (
                                        <div key={idx} className="flex items-center justify-between text-xs p-2 rounded bg-muted/50">
                                            <div className="flex items-center gap-2">
                                                <div
                                                    className="w-3 h-3 rounded"
                                                    style={{ backgroundColor: `hsl(${(idx * 137.5) % 360}, 70%, 50%)` }}
                                                />
                                                <span className="font-medium">{pred.class}</span>
                                            </div>
                                            <Badge variant="outline">{(pred.confidence * 100).toFixed(1)}%</Badge>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                            {testImages.map(img => (
                                <div
                                    key={img.id}
                                    className="group relative rounded-lg border bg-card overflow-hidden hover:shadow-lg transition-shadow cursor-pointer"
                                    onClick={() => img.result && viewResult(img)}
                                >
                                    <div className="aspect-square relative overflow-hidden bg-muted">
                                        <img
                                            src={img.url}
                                            alt={img.name}
                                            className="w-full h-full object-cover"
                                        />
                                        {img.loading && (
                                            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                                                <Loader2 className="w-8 h-8 text-white animate-spin" />
                                            </div>
                                        )}
                                        {img.result && (
                                            <div className="absolute top-2 right-2">
                                                <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
                                                    <CheckCircle2 className="w-4 h-4 text-white" />
                                                </div>
                                            </div>
                                        )}
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                removeImage(img.id);
                                            }}
                                            className="absolute top-2 left-2 opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 rounded-full bg-red-500 hover:bg-red-600 flex items-center justify-center"
                                        >
                                            <X className="w-4 h-4 text-white" />
                                        </button>
                                    </div>
                                    <div className="p-3 space-y-2">
                                        <p className="text-xs font-medium truncate">{img.name}</p>
                                        {img.result ? (
                                            <div className="flex items-center justify-between text-xs">
                                                <span className="text-muted-foreground">
                                                    {img.result.predictions?.length || 0} detection(s)
                                                </span>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-6 px-2"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        viewResult(img);
                                                    }}
                                                >
                                                    <Maximize2 className="w-3 h-3" />
                                                </Button>
                                            </div>
                                        ) : (
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="w-full h-7 text-xs"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    runInference(img.id);
                                                }}
                                                disabled={img.loading || !selectedModel}
                                            >
                                                {img.loading ? (
                                                    <>
                                                        <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                                                        Testing...
                                                    </>
                                                ) : (
                                                    <>
                                                        <Play className="w-3 h-3 mr-1" />
                                                        Test
                                                    </>
                                                )}
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
