"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, TrendingUp, TrendingDown, AlertTriangle, BarChart3, Clock, Trash2 } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectMonitoring({ dataset }) {
    const { token } = useAuth();
    const [stats, setStats] = useState(null);
    const [drift, setDrift] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchStats = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.MONITORING.STATS(dataset.id), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) setStats(await res.json());
        } catch (e) {
            console.error(e);
        }
    };

    const fetchDrift = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.MONITORING.DRIFT(dataset.id), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) setDrift(await res.json());
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        Promise.all([fetchStats(), fetchDrift()]).finally(() => setLoading(false));
    }, [dataset.id]);

    if (loading) return <div className="p-8 text-center text-muted-foreground">Loading monitoring data...</div>;

    const hasData = stats && stats.total_inferences > 0;

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Production Monitoring</h2>
                    <p className="text-muted-foreground text-sm">Track model performance, confidence trends, and detect data drift</p>
                </div>
                <Button variant="outline" size="sm" onClick={() => { fetchStats(); fetchDrift(); }}>
                    <Activity className="mr-2 w-4 h-4" /> Refresh
                </Button>
            </div>

            {/* Drift Alert */}
            {drift?.drift_detected && (
                <div className="p-4 rounded-lg border border-amber-500/50 bg-amber-500/10 flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                        <p className="font-semibold text-amber-500">Data Drift Detected ({drift.severity})</p>
                        <p className="text-sm text-muted-foreground mt-1">{drift.recommendation}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            Confidence shift: {(drift.confidence_shift * 100).toFixed(1)}% • Max class shift: {drift.max_class_shift}%
                        </p>
                    </div>
                </div>
            )}

            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                    <CardContent className="p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
                            <BarChart3 className="w-4 h-4" /> Total Inferences
                        </div>
                        <p className="text-2xl font-bold">{stats?.total_inferences || 0}</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
                            <TrendingUp className="w-4 h-4" /> Avg Confidence
                        </div>
                        <p className="text-2xl font-bold">
                            {stats?.avg_confidence ? `${(stats.avg_confidence * 100).toFixed(1)}%` : "—"}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
                            <Activity className="w-4 h-4" /> Avg Detections
                        </div>
                        <p className="text-2xl font-bold">{stats?.avg_detections_per_image?.toFixed(1) || "—"}</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
                            <AlertTriangle className="w-4 h-4" /> Drift Status
                        </div>
                        <div className="text-2xl font-bold">
                            {drift ? (
                                drift.drift_detected ?
                                    <Badge variant="destructive">Detected</Badge> :
                                    <Badge className="bg-green-600">Stable</Badge>
                            ) : "—"}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Class Distribution */}
            {hasData && stats.class_distribution && Object.keys(stats.class_distribution).length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Class Distribution</CardTitle>
                        <CardDescription>Detection frequency by class across all inferences</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {Object.entries(stats.class_distribution)
                                .sort(([, a], [, b]) => b - a)
                                .map(([className, count]) => {
                                    const maxCount = Math.max(...Object.values(stats.class_distribution));
                                    const pct = (count / maxCount) * 100;
                                    return (
                                        <div key={className} className="space-y-1">
                                            <div className="flex justify-between text-sm">
                                                <span className="font-medium">{className}</span>
                                                <span className="text-muted-foreground">{count}</span>
                                            </div>
                                            <div className="h-2 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-primary rounded-full transition-all"
                                                    style={{ width: `${pct}%` }}
                                                />
                                            </div>
                                        </div>
                                    );
                                })}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Confidence Trend */}
            {hasData && stats.confidence_trend?.length > 1 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Confidence Trend</CardTitle>
                        <CardDescription>Average confidence over time</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-end gap-1 h-32">
                            {stats.confidence_trend.map((point, idx) => {
                                const barHeight = point.avg_confidence * 100;
                                const isLow = point.avg_confidence < 0.5;
                                return (
                                    <div
                                        key={idx}
                                        className="flex-1 group relative"
                                        title={`Batch ${idx + 1}: ${(point.avg_confidence * 100).toFixed(1)}%`}
                                    >
                                        <div
                                            className={`rounded-t transition-all ${isLow ? "bg-amber-500" : "bg-primary"} hover:opacity-80`}
                                            style={{ height: `${barHeight}%` }}
                                        />
                                    </div>
                                );
                            })}
                        </div>
                        <div className="flex justify-between text-xs text-muted-foreground mt-2">
                            <span>Oldest</span>
                            <span>→ Most Recent</span>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Recent Predictions */}
            {hasData && stats.recent_predictions?.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Recent Predictions</CardTitle>
                        <CardDescription>Latest inference results</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-border">
                                        <th className="text-left py-2 font-medium">Image</th>
                                        <th className="text-left py-2 font-medium">Detections</th>
                                        <th className="text-left py-2 font-medium">Avg Confidence</th>
                                        <th className="text-left py-2 font-medium">Classes</th>
                                        <th className="text-left py-2 font-medium">Time</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {stats.recent_predictions.map((pred, idx) => (
                                        <tr key={idx} className="border-b border-border/50">
                                            <td className="py-2 truncate max-w-[150px]">{pred.image_name}</td>
                                            <td className="py-2">{pred.num_detections}</td>
                                            <td className="py-2">
                                                <Badge variant={pred.avg_confidence > 0.7 ? "default" : "destructive"} className="text-xs">
                                                    {(pred.avg_confidence * 100).toFixed(1)}%
                                                </Badge>
                                            </td>
                                            <td className="py-2">
                                                <div className="flex gap-1 flex-wrap">
                                                    {Object.entries(pred.class_counts || {}).map(([cls, cnt]) => (
                                                        <Badge key={cls} variant="outline" className="text-[10px]">
                                                            {cls}: {cnt}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </td>
                                            <td className="py-2 text-muted-foreground text-xs">
                                                {pred.timestamp ? new Date(pred.timestamp).toLocaleTimeString() : "—"}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}

            {!hasData && (
                <Card className="border-dashed">
                    <CardContent className="p-12 text-center">
                        <Activity className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                        <h3 className="font-semibold mb-2">No Monitoring Data Yet</h3>
                        <p className="text-muted-foreground text-sm">
                            Run inferences with your deployed model to start collecting monitoring data.
                            The system automatically logs each inference for trend analysis and drift detection.
                        </p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
