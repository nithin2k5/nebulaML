"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Activity, TrendingUp, CheckCircle2, XCircle, Loader2, BarChart3, Square } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function TrainingLive({ jobId, dataset, onBack }) {
    const { token } = useAuth();
    const [job, setJob] = useState(null);
    const [metrics, setMetrics] = useState([]);
    const [perClass, setPerClass] = useState([]);
    const [confusionMatrix, setConfusionMatrix] = useState(null);
    const [cancelling, setCancelling] = useState(false);
    const pollRef = useRef(null);
    const canvasRef = useRef(null);

    // Poll job status
    useEffect(() => {
        const poll = async () => {
            try {
                // Job status
                const statusRes = await fetch(API_ENDPOINTS.TRAINING.JOB(jobId), {
                    headers: { "Authorization": `Bearer ${token}` }
                });
                if (statusRes.ok) {
                    const data = await statusRes.json();
                    setJob(data);

                    if (data.status === "completed" || data.status === "failed" || data.status === "cancelled") {
                        clearInterval(pollRef.current);
                        if (data.status === "completed") fetchPostTraining();
                    }
                }

                // Metrics (live curves)
                const metricsRes = await fetch(API_ENDPOINTS.TRAINING.JOB_METRICS(jobId), {
                    headers: { "Authorization": `Bearer ${token}` }
                });
                if (metricsRes.ok) {
                    const data = await metricsRes.json();
                    if (data.metrics?.length > 0) setMetrics(data.metrics);
                }
            } catch(e) { console.error("Poll error:", e); }
        };

        poll(); // initial
        pollRef.current = setInterval(poll, 3000);
        return () => clearInterval(pollRef.current);
    }, [jobId, token]);

    const handleCancelTraining = async () => {
        if (!window.confirm("Stop training? The run ends after the current epoch finishes.")) return;
        setCancelling(true);
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.CANCEL(jobId), {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                toast.success(data.message || "Cancellation requested");
            } else {
                toast.error(data.detail || "Could not cancel");
            }
        } catch (e) {
            toast.error(e.message || "Cancel failed");
        } finally {
            setCancelling(false);
        }
    };

    const fetchPostTraining = async () => {
        try {
            // Per-class metrics
            const pcRes = await fetch(API_ENDPOINTS.TRAINING.PER_CLASS_METRICS(jobId), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (pcRes.ok) {
                const data = await pcRes.json();
                if (data.per_class_metrics?.length > 0) setPerClass(data.per_class_metrics);
            }

            // Confusion matrix
            setConfusionMatrix(API_ENDPOINTS.TRAINING.CONFUSION_MATRIX(jobId));
        } catch(e) { console.error(e); }
    };

    // Draw live charts on canvas
    useEffect(() => {
        if (!canvasRef.current || metrics.length === 0) return;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext("2d");
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        // Background grid
        ctx.strokeStyle = "rgba(255,255,255,0.05)";
        ctx.lineWidth = 1;
        for (let i = 0; i < 5; i++) {
            const y = (h / 5) * i;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
        }

        const drawLine = (key, color, yMax = null) => {
            const values = metrics.map(m => {
                const k = Object.keys(m).find(mk => mk.includes(key));
                return k ? parseFloat(m[k]) : 0;
            }).filter(v => !isNaN(v));
            
            if (values.length === 0) return;
            const max = yMax || Math.max(...values, 0.01);
            const step = w / Math.max(values.length - 1, 1);

            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            values.forEach((v, i) => {
                const x = i * step;
                const y = h - (v / max) * (h - 20) - 10;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();

            // Last value label
            const lastVal = values[values.length - 1];
            const lastX = (values.length - 1) * step;
            const lastY = h - (lastVal / max) * (h - 20) - 10;
            ctx.fillStyle = color;
            ctx.font = "bold 11px Inter, system-ui, sans-serif";
            ctx.fillText(lastVal.toFixed(4), Math.min(lastX + 4, w - 60), lastY - 4);
        };

        // Draw losses
        drawLine("train/box_loss", "#6366f1");
        drawLine("train/cls_loss", "#f43f5e");
        drawLine("train/dfl_loss", "#f59e0b");

        // Draw mAP
        drawLine("mAP50(B)", "#10b981", 1.0);
        drawLine("mAP50-95(B)", "#06b6d4", 1.0);

    }, [metrics]);

    const flatMetrics =
        job?.metrics && typeof job.metrics === "object"
            ? job.metrics.metrics && typeof job.metrics.metrics === "object"
                ? job.metrics.metrics
                : job.metrics
            : null;

    const progress = job?.progress || 0;
    const currentEpoch = job?.current_epoch || 0;
    const totalEpochs = job?.config?.epochs || 0;
    const isRunning = job?.status === "running" || job?.status === "pending";
    const isCompleted = job?.status === "completed";
    const isFailed = job?.status === "failed";
    const isCancelled = job?.status === "cancelled";

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <Button variant="ghost" size="sm" onClick={onBack}>
                    <ArrowLeft className="w-4 h-4 mr-1" /> Back
                </Button>
                <div className="flex-1">
                    <h2 className="text-xl font-semibold flex items-center gap-2">
                        Training Job
                        {isRunning && <Loader2 className="w-5 h-5 animate-spin text-primary" />}
                        {isCompleted && <CheckCircle2 className="w-5 h-5 text-emerald-500" />}
                        {isFailed && <XCircle className="w-5 h-5 text-red-500" />}
                        {isCancelled && <Square className="w-5 h-5 text-amber-500" />}
                    </h2>
                    <p className="text-sm text-muted-foreground">Job ID: {jobId.slice(0, 8)}...</p>
                </div>
                <div className="flex items-center gap-2">
                    {isRunning && (
                        <Button variant="outline" size="sm" className="border-amber-500/40 text-amber-600 hover:bg-amber-500/10" disabled={cancelling} onClick={handleCancelTraining}>
                            {cancelling ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Square className="w-4 h-4 mr-1" />}
                            Cancel training
                        </Button>
                    )}
                    <Badge variant={isRunning ? "default" : isCompleted ? "outline" : isCancelled ? "secondary" : "destructive"}>
                        {job?.status || "loading..."}
                    </Badge>
                </div>
            </div>

            {/* Progress */}
            <Card>
                <CardContent className="p-4">
                    <div className="flex justify-between text-sm mb-2">
                        <span>Epoch {currentEpoch} / {totalEpochs}</span>
                        <span>{progress.toFixed(1)}%</span>
                    </div>
                    <div className="h-3 bg-muted rounded-full overflow-hidden">
                        <div 
                            className="h-full bg-primary rounded-full transition-all duration-500"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                    {flatMetrics && (
                        <div className="grid grid-cols-4 gap-3 mt-4 text-center">
                            <div>
                                <p className="text-xs text-muted-foreground">mAP50</p>
                                <p className="font-semibold text-sm">{((typeof flatMetrics.map50 === "number" ? flatMetrics.map50 : Number(flatMetrics.map50) || 0) * 100).toFixed(1)}%</p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">mAP50-95</p>
                                <p className="font-semibold text-sm">{((typeof flatMetrics["map50-95"] === "number" ? flatMetrics["map50-95"] : typeof flatMetrics.map50_95 === "number" ? flatMetrics.map50_95 : 0) * 100).toFixed(1)}%</p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">Precision</p>
                                <p className="font-semibold text-sm">{(typeof flatMetrics.precision === "number" ? flatMetrics.precision * 100 : 0).toFixed(1)}%</p>
                            </div>
                            <div>
                                <p className="text-xs text-muted-foreground">Recall</p>
                                <p className="font-semibold text-sm">{(typeof flatMetrics.recall === "number" ? flatMetrics.recall * 100 : 0).toFixed(1)}%</p>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Live Training Curves */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="w-5 h-5" /> Training Curves
                    </CardTitle>
                    <CardDescription>Loss and mAP over epochs (updates every 3s)</CardDescription>
                </CardHeader>
                <CardContent>
                    {metrics.length > 0 ? (
                        <>
                            <canvas 
                                ref={canvasRef} 
                                width={700} 
                                height={250} 
                                className="w-full rounded-lg bg-black/20 border border-border"
                            />
                            <div className="flex flex-wrap gap-4 mt-3 text-xs">
                                <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-indigo-500 inline-block"/> Box Loss</span>
                                <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-rose-500 inline-block"/> Cls Loss</span>
                                <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-amber-500 inline-block"/> DFL Loss</span>
                                <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-emerald-500 inline-block"/> mAP50</span>
                                <span className="flex items-center gap-1"><span className="w-3 h-1 rounded bg-cyan-500 inline-block"/> mAP50-95</span>
                            </div>
                        </>
                    ) : (
                        <div className="text-center text-muted-foreground py-8">
                            <Loader2 className="w-6 h-6 mx-auto animate-spin mb-2" />
                            Waiting for training metrics...
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Post-training: Confusion Matrix */}
            {isCompleted && confusionMatrix && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <BarChart3 className="w-5 h-5" /> Confusion Matrix
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <img 
                            src={confusionMatrix}
                            alt="Confusion Matrix"
                            className="w-full max-w-2xl mx-auto rounded-lg border border-border"
                            onError={() => setConfusionMatrix(null)}
                        />
                    </CardContent>
                </Card>
            )}

            {/* Post-training: Per-class Metrics */}
            {isCompleted && perClass.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <TrendingUp className="w-5 h-5" /> Per-Class Performance
                        </CardTitle>
                        <CardDescription>Sorted by weakest mAP50 first</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-border">
                                        <th className="text-left py-2 font-medium">Class</th>
                                        <th className="text-right py-2 font-medium">Precision</th>
                                        <th className="text-right py-2 font-medium">Recall</th>
                                        <th className="text-right py-2 font-medium">mAP50</th>
                                        <th className="text-right py-2 font-medium">mAP50-95</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {[...perClass].sort((a, b) => a.mAP50 - b.mAP50).map((cls) => (
                                        <tr key={cls.class_id} className="border-b border-border/50">
                                            <td className="py-2 font-medium">{cls.class_name}</td>
                                            <td className="py-2 text-right">
                                                <Badge variant={cls.precision > 0.7 ? "default" : "destructive"} className="text-xs">
                                                    {(cls.precision * 100).toFixed(1)}%
                                                </Badge>
                                            </td>
                                            <td className="py-2 text-right">
                                                <Badge variant={cls.recall > 0.7 ? "default" : "destructive"} className="text-xs">
                                                    {(cls.recall * 100).toFixed(1)}%
                                                </Badge>
                                            </td>
                                            <td className="py-2 text-right">
                                                <Badge variant={cls.mAP50 > 0.5 ? "default" : "destructive"} className="text-xs">
                                                    {(cls.mAP50 * 100).toFixed(1)}%
                                                </Badge>
                                            </td>
                                            <td className="py-2 text-right text-muted-foreground">
                                                {(cls.mAP50_95 * 100).toFixed(1)}%
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Error display */}
            {isFailed && job?.error && (
                <Card className="border-red-500/30">
                    <CardContent className="p-4">
                        <p className="text-red-500 font-medium mb-1">Training Failed</p>
                        <p className="text-sm text-muted-foreground">{job.error}</p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
