"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
    Activity, AlertTriangle, CheckCircle, PieChart,
    BarChart, AlertOctagon, RotateCcw, RefreshCw
} from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ProjectHealth({ params }) {
    const { token } = useAuth();
    const [analysis, setAnalysis] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchAnalysis = async () => {
        setLoading(true);
        setError(null);
        try {
            // Trigger new analysis
            const res = await fetch(API_ENDPOINTS.DATASETS.ANALYZE(params.id), {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (!res.ok) throw new Error("Analysis failed");
            const data = await res.json();
            setAnalysis(data.analysis || data);
        } catch (e) {
            console.error(e);
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAnalysis();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [params.id]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <RefreshCw className="w-8 h-8 animate-spin text-purple-500" />
                <p className="text-gray-400">Analyzing dataset health...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-4 text-center">
                <p className="text-red-400 mb-4">Failed to load analysis: {error}</p>
                <Button onClick={fetchAnalysis}>Retry</Button>
            </div>
        );
    }

    if (!analysis) return null;

    // Helpers
    const qualityColor = (score) => {
        if (score >= 80) return "text-emerald-400";
        if (score >= 50) return "text-yellow-400";
        return "text-red-400";
    };

    const balanceScore = analysis.class_balance_score || 0;
    const qualityScore = analysis.overall_quality_score || 0;

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Top Stats */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="bg-zinc-900 border-white/10">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Overall Quality</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className={`text-3xl font-bold ${qualityColor(qualityScore)}`}>
                            {Math.round(qualityScore)}/100
                        </div>
                        <Progress value={qualityScore} className="h-2 mt-2 bg-white/5" indicatorClassName={qualityScore >= 80 ? "bg-emerald-500" : (qualityScore >= 50 ? "bg-yellow-500" : "bg-red-500")} />
                    </CardContent>
                </Card>

                <Card className="bg-zinc-900 border-white/10">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Class Balance</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-white">
                            {(balanceScore * 100).toFixed(0)}%
                        </div>
                        <Progress value={balanceScore * 100} className="h-2 mt-2 bg-white/5" />
                        <p className="text-xs text-gray-500 mt-1">
                            {balanceScore < 0.5 ? "Critical Imbalance" : (balanceScore < 0.8 ? "Moderate Imbalance" : "Balanced")}
                        </p>
                    </CardContent>
                </Card>

                <Card className="bg-zinc-900 border-white/10">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-gray-400">Annotation Status</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-white">
                            {analysis.annotated_images} <span className="text-base font-normal text-gray-500">/ {analysis.total_images}</span>
                        </div>
                        <div className="flex gap-2 mt-2">
                            <Badge variant="outline" className="text-xs bg-white/5">
                                {analysis.total_annotations} objects
                            </Badge>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Issues & Warnings */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="space-y-4">
                    <h3 className="text-lg font-semibold flex items-center">
                        <AlertTriangle className="w-5 h-5 mr-2 text-yellow-500" />
                        Issues Detected
                    </h3>

                    {(!analysis.structure_valid) && (
                        <Alert variant="destructive" className="bg-red-950/30 border-red-900">
                            <AlertOctagon className="h-4 w-4" />
                            <AlertTitle>Structure Invalid</AlertTitle>
                            <AlertDescription>
                                {analysis.structure_issues?.join(", ")}
                            </AlertDescription>
                        </Alert>
                    )}

                    {analysis.warnings?.map((warn, i) => (
                        <Alert key={i} className="bg-yellow-950/20 border-yellow-900/50">
                            <AlertTriangle className="h-4 w-4 text-yellow-500" />
                            <AlertTitle className="text-yellow-500">Warning</AlertTitle>
                            <AlertDescription className="text-yellow-200/80">
                                {warn}
                            </AlertDescription>
                        </Alert>
                    ))}

                    {analysis.warnings?.length === 0 && analysis.structure_valid && (
                        <div className="p-8 border border-white/10 rounded-lg text-center bg-white/5">
                            <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
                            <p className="text-gray-400">No major issues detected!</p>
                        </div>
                    )}
                </div>

                {/* Recommendations */}
                <div className="space-y-4">
                    <h3 className="text-lg font-semibold flex items-center">
                        <Activity className="w-5 h-5 mr-2 text-purple-500" />
                        Recommendations
                    </h3>

                    <div className="grid gap-3">
                        {analysis.recommendations?.map((rec, i) => (
                            <div key={i} className="p-3 bg-white/5 border border-white/10 rounded-md flex items-start gap-3">
                                <div className="mt-0.5 p-1 bg-purple-500/20 rounded-full">
                                    <CheckCircle className="w-3 h-3 text-purple-400" />
                                </div>
                                <p className="text-sm text-gray-300">{rec}</p>
                            </div>
                        ))}

                        {/* Auto-generated Config */}
                        <div className="mt-4 p-4 border border-white/10 rounded-lg bg-zinc-950/50">
                            <h4 className="text-xs font-uppercase text-gray-500 font-bold mb-3 tracking-wider">SUGGESTED TRAINING CONFIG</h4>
                            <div className="grid grid-cols-2 gap-4 text-sm">
                                <div>
                                    <span className="text-gray-500">Image Size:</span>
                                    <span className="ml-2 text-white font-mono">{analysis.recommended_image_size}px</span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Batch Size:</span>
                                    <span className="ml-2 text-white font-mono">{analysis.recommended_batch_size}</span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Epochs:</span>
                                    <span className="ml-2 text-white font-mono">{analysis.recommended_epochs}</span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Augmentation:</span>
                                    <span className="ml-2 text-emerald-400">{analysis.augmentation_recommendations?.mosaic ? "Heavy (Mosaic)" : "Standard"}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Distributions */}
            <h3 className="text-lg font-semibold flex items-center mt-8">
                <PieChart className="w-5 h-5 mr-2 text-blue-500" />
                Class Distribution
            </h3>
            <div className="h-64 border border-white/10 rounded-lg p-4 bg-zinc-950/50 flex items-end space-x-2 overflow-x-auto">
                {Object.entries(analysis.class_frequency || {}).map(([className, count], i) => {
                    const max = Math.max(...Object.values(analysis.class_frequency));
                    const height = (count / max) * 100;
                    return (
                        <div key={i} className="flex-1 min-w-[50px] flex flex-col items-center group">
                            <div className="mb-2 opacity-0 group-hover:opacity-100 transition-opacity text-xs text-white">{count}</div>
                            <div
                                className="w-full bg-blue-500/20 border-t border-x border-blue-500/50 rounded-t hover:bg-blue-500/40 transition-colors relative"
                                style={{ height: `${height}%` }}
                            ></div>
                            <div className="mt-2 text-xs text-gray-400 truncate w-full text-center" title={className}>
                                {className}
                            </div>
                        </div>
                    )
                })}
            </div>

        </div>
    );
}
