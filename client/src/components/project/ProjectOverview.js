"use client";

import DatasetWorkflow from "@/components/DatasetWorkflow";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { 
    ImageIcon, Tag, CheckCircle2, ShieldCheck, 
    Activity, Clock, ChevronRight, BarChart2
} from "lucide-react";
import { cn } from "@/lib/utils";

function StatCard({ icon: Icon, label, value, color }) {
    return (
        <div className={cn(
            "relative flex flex-col items-center justify-center p-5 rounded-2xl border border-white/[0.07]",
            "bg-white/[0.02] backdrop-blur-sm hover:bg-white/[0.04] transition-all duration-300 group"
        )}>
            <div className={cn("absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-xl -z-10", color)} />
            <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center mb-3 border border-white/10", color)}>
                <Icon className="w-5 h-5" />
            </div>
            <p className="text-3xl font-black tabular-nums tracking-tight text-white">{value ?? "—"}</p>
            <p className="text-[11px] text-gray-500 uppercase tracking-wider mt-1">{label}</p>
        </div>
    );
}

export default function ProjectOverview({ dataset, stats, trainingJobs, onRefresh }) {
    // Determine quality score color
    const score = stats?.completion_percentage || 0;
    const qualityColor = score >= 90 ? "text-emerald-400" : score >= 50 ? "text-amber-400" : "text-red-400";
    
    // Get latest job if any
    const latestJob = trainingJobs && Object.values(trainingJobs).length > 0 
        ? Object.values(trainingJobs).sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
        : null;

    // Get top 5 classes by count
    const topClasses = stats?.class_counts 
        ? Object.entries(stats.class_counts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
        : [];

    return (
        <div className="h-full space-y-6 max-w-6xl mx-auto animate-fade-in pb-10">
            
            {/* ── Hero / Stats ── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard icon={ImageIcon} label="Total Images" value={stats?.total_images || 0} color="bg-indigo-500/10 text-indigo-400" />
                <StatCard icon={Tag} label="Classes" value={stats?.total_classes || 0} color="bg-violet-500/10 text-violet-400" />
                <StatCard icon={CheckCircle2} label="Annotated" value={stats?.annotated_images || 0} color="bg-emerald-500/10 text-emerald-400" />
                <StatCard icon={ShieldCheck} label="Completion %" value={`${Math.round(score)}%`} color={`bg-white/5 ${qualityColor}`} />
            </div>

            {/* ── Dashboard Grid ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                
                {/* Left: Class Balance Snapshot */}
                <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] backdrop-blur-sm overflow-hidden flex flex-col">
                    <div className="px-6 py-5 border-b border-white/[0.06] flex items-center gap-2">
                        <BarChart2 className="w-4 h-4 text-violet-400" />
                        <h3 className="text-sm font-semibold text-white">Class Balance</h3>
                    </div>
                    <div className="p-6 flex-1">
                        {topClasses.length > 0 ? (
                            <div className="space-y-4">
                                {topClasses.map(([cls, count], idx) => {
                                    const maxCount = topClasses[0][1];
                                    const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                                    return (
                                        <div key={cls} className="space-y-1.5">
                                            <div className="flex justify-between text-xs">
                                                <span className="text-gray-300 font-medium">{cls}</span>
                                                <span className="text-gray-500">{count} labels</span>
                                            </div>
                                            <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                                                <div 
                                                    className="h-full bg-violet-500 rounded-full transition-all duration-1000" 
                                                    style={{ width: `${pct}%` }} 
                                                />
                                            </div>
                                        </div>
                                    );
                                })}
                                {stats?.total_classes > 5 && (
                                    <p className="text-xs text-gray-500 text-center mt-4">
                                        + {stats.total_classes - 5} more classes
                                    </p>
                                )}
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-500 text-sm py-8">
                                <Tag className="w-8 h-8 opacity-20 mb-3" />
                                <p>No annotations yet</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Recent Training */}
                <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] backdrop-blur-sm overflow-hidden flex flex-col">
                    <div className="px-6 py-5 border-b border-white/[0.06] flex items-center gap-2">
                        <Activity className="w-4 h-4 text-indigo-400" />
                        <h3 className="text-sm font-semibold text-white">Recent Training</h3>
                    </div>
                    <div className="p-6 flex-1 flex flex-col">
                        {latestJob ? (
                            <div className="space-y-6">
                                <div className="flex items-start justify-between">
                                    <div>
                                        <p className="text-lg font-bold text-white mb-1">
                                            {latestJob.config?.model_name || "YOLOv8 Model"}
                                        </p>
                                        <div className="flex items-center gap-2 text-xs text-gray-400">
                                            <Clock className="w-3 h-3" />
                                            {new Date(latestJob.created_at).toLocaleString()}
                                        </div>
                                    </div>
                                    <Badge className={cn("capitalize border text-xs", 
                                        latestJob.status === "completed" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" :
                                        latestJob.status === "running" ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/30" :
                                        latestJob.status === "failed" ? "bg-red-500/10 text-red-400 border-red-500/30" :
                                        "bg-zinc-500/10 text-zinc-400 border-zinc-500/30"
                                    )}>
                                        {latestJob.status}
                                    </Badge>
                                </div>
                                
                                {latestJob.status === "completed" && latestJob.metrics?.metrics ? (
                                    <div className="grid grid-cols-3 gap-3">
                                        <div className="bg-white/5 rounded-xl p-3 text-center border border-white/10">
                                            <p className="text-xl font-bold text-white">
                                                {(latestJob.metrics.metrics["metrics/mAP50(B)"] * 100).toFixed(1)}%
                                            </p>
                                            <p className="text-[10px] text-gray-500 uppercase tracking-wider mt-1">mAP50</p>
                                        </div>
                                        <div className="bg-white/5 rounded-xl p-3 text-center border border-white/10">
                                            <p className="text-xl font-bold text-white">
                                                {(latestJob.metrics.metrics["metrics/precision(B)"] * 100).toFixed(1)}%
                                            </p>
                                            <p className="text-[10px] text-gray-500 uppercase tracking-wider mt-1">Precision</p>
                                        </div>
                                        <div className="bg-white/5 rounded-xl p-3 text-center border border-white/10">
                                            <p className="text-xl font-bold text-white">
                                                {(latestJob.metrics.metrics["metrics/recall(B)"] * 100).toFixed(1)}%
                                            </p>
                                            <p className="text-[10px] text-gray-500 uppercase tracking-wider mt-1">Recall</p>
                                        </div>
                                    </div>
                                ) : latestJob.status === "running" ? (
                                    <div className="flex flex-col items-center justify-center py-6">
                                        <div className="w-full bg-white/5 rounded-full h-2 mb-2 overflow-hidden">
                                            <div className="bg-indigo-500 h-2 rounded-full transition-all" style={{ width: `${latestJob.progress || 0}%` }} />
                                        </div>
                                        <p className="text-xs text-gray-400">Training in progress... {Math.round(latestJob.progress || 0)}%</p>
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center py-6 text-sm text-gray-500">
                                        No metrics available
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-gray-500 text-sm py-8">
                                <Activity className="w-8 h-8 opacity-20 mb-3" />
                                <p>No training jobs yet</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Workflow Guide ── */}
            <div className="pt-4">
                <h3 className="text-sm font-semibold text-white mb-4 px-2">Dataset Lifecycle</h3>
                <DatasetWorkflow dataset={dataset} onRefresh={onRefresh} />
            </div>

        </div>
    );
}
