"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Cpu, Clock, RefreshCw, CheckCircle2, AlertCircle, Trash2, Layers } from "lucide-react";
import { API_BASE_URL } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectVersions({ dataset }) {
    const [jobs, setJobs] = useState([]);
    const { token } = useAuth();

    const fetchJobs = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/training/jobs`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setJobs(data.jobs || []);
            }
        } catch (e) {
            console.error("Failed to fetch jobs:", e);
        }
    };

    useEffect(() => {
        fetchJobs();
        const interval = setInterval(() => {
            fetchJobs();
        }, 12000); // Increased from 3s to 12s to reduce server load
        return () => clearInterval(interval);
    }, []);

    const deleteJob = async (jobId) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/training/job/${jobId}`, {
                method: 'DELETE',
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                toast.success("Job deleted");
                fetchJobs();
            }
        } catch (e) {
            toast.error("Failed to delete job");
        }
    };

    return (
        <div className="h-full flex flex-col gap-6 overflow-y-auto pb-10 custom-scrollbar pr-2">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Training Versions</h2>
                    <p className="text-muted-foreground text-sm">Monitor your current and previous training runs.</p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchJobs}>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                </Button>
            </div>

            <div className="space-y-6">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Layers className="h-5 w-5 text-primary" />
                            Version History
                        </CardTitle>
                        <CardDescription>History of all models trained on this project dataset</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {jobs.length === 0 ? (
                            <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed">
                                <Cpu className="mx-auto h-12 w-12 mb-4 opacity-50 text-muted-foreground" />
                                <h3 className="text-lg font-medium text-foreground mb-1">No Versions Yet</h3>
                                <p>Head over to the Train tab to start your first model training.</p>
                            </div>
                        ) : (
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {jobs.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)).map((job) => (
                                    <div key={job.job_id} className="border rounded-xl p-5 bg-card/50 shadow-sm flex flex-col hover:border-primary/50 transition-colors relative group">
                                        <div className="flex justify-between items-start mb-3">
                                            <div>
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <h4 className="font-semibold text-base">
                                                        {job.config?.model_name || 'Model'}
                                                    </h4>
                                                    {job.strict_mode && <Badge variant="outline" className="text-[10px] h-4 leading-none border-primary/30 text-primary">Strict Mode</Badge>}

                                                    {job.status === "running" && (
                                                        <Badge variant="secondary" className="bg-blue-500/10 text-blue-500 border-blue-500/20 flex items-center gap-1 w-fit">
                                                            <RefreshCw className="h-3 w-3 animate-spin" /> Running
                                                        </Badge>
                                                    )}
                                                    {(job.status === "completed" || job.status === "success") && (
                                                        <Badge variant="secondary" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 flex items-center gap-1 w-fit">
                                                            <CheckCircle2 className="h-3 w-3" /> Completed
                                                        </Badge>
                                                    )}
                                                    {job.status === "failed" && (
                                                        <Badge variant="secondary" className="bg-red-500/10 text-red-500 border-red-500/20 flex items-center gap-1 w-fit">
                                                            <AlertCircle className="h-3 w-3" /> Failed
                                                        </Badge>
                                                    )}
                                                    {job.status === "pending" && (
                                                        <Badge variant="outline" className="text-muted-foreground flex items-center gap-1 w-fit">
                                                            <Clock className="h-3 w-3" /> Pending
                                                        </Badge>
                                                    )}
                                                </div>
                                                <p className="text-xs text-muted-foreground mt-1.5 font-mono">ID: {job.job_id.substring(0, 8)}</p>
                                            </div>
                                            <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity -mr-2 -mt-2">
                                                {(job.status === "completed" || job.status === "success") && (
                                                    <Button variant="ghost" size="sm" className="h-8 text-primary hover:text-primary/80" onClick={() => toast.info("Head to the Deploy tab to try this model.")}>
                                                        Deploy
                                                    </Button>
                                                )}
                                                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-red-400" onClick={() => deleteJob(job.job_id)}>
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>

                                        <div className="text-sm text-muted-foreground mb-4 flex-1">
                                            <div className="flex items-center justify-between py-1 border-b border-white/5">
                                                <span>Epochs configured</span>
                                                <span className="font-medium text-foreground">{job.config?.epochs || '?'}</span>
                                            </div>
                                            <div className="flex items-center justify-between py-1 border-b border-white/5">
                                                <span>Batch size</span>
                                                <span className="font-medium text-foreground">{job.config?.batch_size || '?'}</span>
                                            </div>
                                            <div className="flex items-center justify-between py-1 border-b border-white/5">
                                                <span>Image size</span>
                                                <span className="font-medium text-foreground">{job.config?.img_size || '?'}</span>
                                            </div>
                                        </div>

                                        {job.status === "running" && (
                                            <div className="mt-auto bg-muted/30 p-3 rounded-lg border border-white/5">
                                                <div className="flex justify-between text-xs mb-2">
                                                    <span className="font-medium">Epoch {job.current_epoch || 0} / {job.config?.epochs || '?'}</span>
                                                    <span className="text-primary font-bold">{Math.round(job.progress || 0)}%</span>
                                                </div>
                                                <div className="w-full bg-muted-foreground/20 rounded-full h-1.5 mb-3 overflow-hidden">
                                                    <div
                                                        className="bg-primary h-1.5 rounded-full transition-all duration-500"
                                                        style={{ width: `${Math.max(5, job.progress || 0)}%` }}
                                                    />
                                                </div>

                                                {job.metrics && Object.keys(job.metrics).length > 0 && (
                                                    <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
                                                        {Object.entries(job.metrics).filter(([k]) => k.includes('mAP') || k.includes('loss')).slice(0, 4).map(([key, value]) => (
                                                            <div key={key} className="flex justify-between items-center bg-background/50 px-2 py-1.5 rounded">
                                                                <span className="text-muted-foreground truncate max-w-[60px]" title={key}>{key.split('/').pop()}</span>
                                                                <span className="font-mono font-medium">{typeof value === 'number' ? value.toFixed(3) : value}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {(job.status === "completed" || job.status === "success") && job.metrics && (
                                            <div className="mt-auto grid grid-cols-2 gap-2 text-xs">
                                                {Object.entries(job.metrics).filter(([k]) => k.includes('mAP')).map(([key, value]) => (
                                                    <div key={key} className="bg-emerald-500/10 border border-emerald-500/20 p-2 rounded flex flex-col items-center justify-center text-center">
                                                        <span className="text-emerald-500/80 mb-0.5 truncate w-full" title={key}>{key.split('/').pop()}</span>
                                                        <span className="font-semibold text-emerald-400 text-sm">{typeof value === 'number' ? value.toFixed(3) : value}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {job.status === "failed" && (
                                            <div className="mt-auto text-xs text-red-400 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                                                <div className="font-semibold flex items-center mb-1"><AlertCircle className="h-3 w-3 mr-1" /> Error</div>
                                                <p className="line-clamp-3">{job.error || "Unknown error occurred"}</p>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
