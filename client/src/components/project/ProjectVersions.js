"use client";

import { useState, useEffect, Fragment } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
    Cpu, Clock, RefreshCw, CheckCircle2, AlertCircle, Trash2, Layers,
    Download, ArrowLeft, ChevronRight, BarChart2, Settings2, Box, ImageIcon, Zap
} from "lucide-react";
import { API_BASE_URL, API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";
import { formatMetricValue } from "@/lib/utils";

// ─── helpers ────────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
    if (status === "running")
        return <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20 flex items-center gap-1.5 shrink-0"><RefreshCw className="h-3 w-3 animate-spin" /> Running</Badge>;
    if (status === "completed" || status === "success")
        return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 flex items-center gap-1.5 shrink-0"><CheckCircle2 className="h-3 w-3" /> Completed</Badge>;
    if (status === "failed")
        return <Badge className="bg-red-500/10 text-red-500 border-red-500/20 flex items-center gap-1.5 shrink-0"><AlertCircle className="h-3 w-3" /> Failed</Badge>;
    if (status === "cancelled")
        return <Badge className="bg-amber-500/10 text-amber-600 border-amber-500/20 shrink-0">Stopped</Badge>;
    return <Badge variant="outline" className="text-muted-foreground flex items-center gap-1.5 shrink-0"><Clock className="h-3 w-3" /> Pending</Badge>;
}

// Key-value row used in config + model-info tables
function KVRow({ label, value }) {
    if (value == null) return null;
    return (
        <div className="grid grid-cols-[1fr_auto] gap-4 px-3 py-2 items-center">
            <span className="text-sm text-muted-foreground truncate">{label}</span>
            <span className="text-sm font-medium font-mono text-right tabular-nums">{String(value)}</span>
        </div>
    );
}

function SectionHeader({ icon: Icon, title }) {
    return (
        <div className="flex items-center gap-2 mb-3">
            <Icon className="h-4 w-4 text-primary shrink-0" />
            <span className="text-sm font-semibold">{title}</span>
        </div>
    );
}

// ─── Detail panel ────────────────────────────────────────────────────────────

function JobDetail({ job, token, dataset, versions, onBack, onDeploy, onCancel, onDelete }) {
    const [perClass, setPerClass] = useState(null);
    const [modelInfo, setModelInfo] = useState(null);
    const [cmError, setCmError] = useState(false);
    const isCompleted = job.status === "completed" || job.status === "success";
    const isRunning = job.status === "running" || job.status === "pending";
    const modelName = `job_${job.job_id}`;
    const cmUrl = `${API_BASE_URL}/api/training/job/${job.job_id}/confusion-matrix`;

    useEffect(() => {
        if (!isCompleted) return;

        fetch(API_ENDPOINTS.TRAINING.PER_CLASS_METRICS(job.job_id), {
            headers: { Authorization: `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null).then(d => {
            if (d?.per_class_metrics?.length) setPerClass(d.per_class_metrics);
        }).catch(() => {});

        fetch(API_ENDPOINTS.MODELS.INFO(modelName), {
            headers: { Authorization: `Bearer ${token}` }
        }).then(r => r.ok ? r.json() : null).then(d => {
            if (d) setModelInfo(d);
        }).catch(() => {});
    }, [job.job_id, isCompleted]);

    const downloadPt = () => {
        fetch(API_ENDPOINTS.MODELS.DOWNLOAD(modelName), {
            headers: { Authorization: `Bearer ${token}` }
        }).then(r => {
            if (!r.ok) throw new Error("Download failed");
            return r.blob();
        }).then(blob => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${job.config?.model_name?.replace(".pt", "") || "model"}_${job.job_id.substring(0, 8)}.pt`;
            a.click();
            URL.revokeObjectURL(url);
            toast.success("Model downloaded");
        }).catch(err => toast.error(err.message));
    };

    const usedVersion = versions.find(v => v.id?.toString() === job.version_id?.toString());

    const finalMetrics = [
        ["mAP50",    job.metrics?.map50    ?? job.metrics?.["map50"]],
        ["mAP50-95", job.metrics?.["map50-95"] ?? job.metrics?.["map50_95"]],
        ["Precision", job.metrics?.precision],
        ["Recall",   job.metrics?.recall],
    ].filter(([, v]) => v != null);

    return (
        <div className="space-y-5">

            {/* ── Hero header card ── */}
            <div className="rounded-xl border border-border bg-card overflow-hidden">
                {/* top accent line */}
                <div className="h-0.5 w-full bg-gradient-to-r from-primary/60 via-primary to-primary/20" />

                <div className="px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-4">
                    {/* back + title */}
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                        <Button variant="ghost" size="icon" onClick={onBack}
                            className="shrink-0 h-8 w-8 rounded-lg hover:bg-muted">
                            <ArrowLeft className="h-4 w-4" />
                        </Button>
                        <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-bold text-xl leading-tight tracking-tight">
                                    {job.config?.model_name || "Model"}
                                </h3>
                                <StatusBadge status={job.status} />
                                {job.strict_mode && (
                                    <Badge variant="outline" className="text-xs border-primary/30 text-primary">Strict</Badge>
                                )}
                            </div>
                            <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                                <span className="text-xs text-muted-foreground font-mono">
                                    Job {job.job_id.substring(0, 8)}
                                </span>
                                {job.created_at && (
                                    <span className="text-xs text-muted-foreground">
                                        {new Date(job.created_at).toLocaleString()}
                                    </span>
                                )}
                                {(usedVersion || job.version_id) && (
                                    <span className="flex items-center gap-1 text-xs text-primary/80">
                                        <Layers className="h-3 w-3" />
                                        {usedVersion?.name || `Version ${job.version_id}`}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* actions */}
                    <div className="flex items-center gap-2 shrink-0 ml-11 sm:ml-0">
                        {isCompleted && (
                            <>
                                <Button size="sm" variant="outline" onClick={downloadPt}
                                    className="gap-1.5 text-emerald-500 border-emerald-500/30 hover:bg-emerald-500/10">
                                    <Download className="h-3.5 w-3.5" /> Download .pt
                                </Button>
                                <Button size="sm" onClick={onDeploy} className="gap-1.5">
                                    <Zap className="h-3.5 w-3.5" /> Deploy
                                </Button>
                            </>
                        )}
                        {isRunning && (
                            <Button size="sm" variant="outline" onClick={onCancel}
                                className="text-amber-600 border-amber-500/30 hover:bg-amber-500/10">
                                Stop Training
                            </Button>
                        )}
                        {!isRunning && (
                            <Button size="sm" variant="ghost" onClick={onDelete}
                                className="text-muted-foreground hover:text-red-400 hover:bg-red-500/10">
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        )}
                    </div>
                </div>
            </div>

            {/* ── Metrics banner (always at top when completed) ── */}
            {isCompleted && finalMetrics.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {finalMetrics.map(([label, val]) => (
                        <div key={label}
                            className="rounded-xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 px-4 py-3.5 flex flex-col gap-1.5">
                            <span className="text-xs font-medium text-emerald-400/70 uppercase tracking-wide">{label}</span>
                            <span className="text-2xl font-bold font-mono tabular-nums text-emerald-400 leading-none">
                                {formatMetricValue(val)}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {/* ── Running progress ── */}
            {isRunning && (
                <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 space-y-3">
                    <div className="flex items-center justify-between text-sm font-medium">
                        <span className="text-muted-foreground">
                            Epoch <span className="text-foreground font-bold">{job.current_epoch || 0}</span> / {job.config?.epochs || "?"}
                        </span>
                        <span className="text-primary font-bold tabular-nums text-base">{Math.round(job.progress || 0)}%</span>
                    </div>
                    <div className="w-full bg-muted-foreground/20 rounded-full h-2.5 overflow-hidden">
                        <div
                            className="bg-primary h-2.5 rounded-full transition-all duration-500"
                            style={{ width: `${Math.max(3, job.progress || 0)}%` }}
                        />
                    </div>
                    {job.metrics && Object.keys(job.metrics).length > 0 && (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                            {Object.entries(job.metrics)
                                .filter(([k]) => k.includes("mAP") || k.includes("loss"))
                                .slice(0, 4)
                                .map(([k, v]) => (
                                    <div key={k} className="rounded-lg bg-muted/40 border border-border px-3 py-2 flex flex-col gap-0.5">
                                        <span className="text-[11px] text-muted-foreground truncate">{k.split("/").pop()}</span>
                                        <span className="text-sm font-semibold font-mono tabular-nums">{formatMetricValue(v)}</span>
                                    </div>
                                ))}
                        </div>
                    )}
                </div>
            )}

            {/* ── Failed error ── */}
            {job.status === "failed" && (
                <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4">
                    <div className="flex items-center gap-1.5 text-red-400 font-semibold text-sm mb-1.5">
                        <AlertCircle className="h-4 w-4 shrink-0" /> Training Failed
                    </div>
                    <p className="font-mono text-xs text-red-300/80 break-words">{job.error || "Unknown error"}</p>
                </div>
            )}

            {/* ── Config + Model file side by side ── */}
            <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-5 items-start">

                {/* Training config */}
                <div>
                    <SectionHeader icon={Settings2} title="Training Configuration" />
                    <div className="rounded-xl border border-border overflow-hidden divide-y divide-border bg-card">
                        <KVRow label="Base model"    value={job.config?.model_name} />
                        <KVRow label="Epochs"        value={job.config?.epochs} />
                        <KVRow label="Batch size"    value={job.config?.batch_size} />
                        <KVRow label="Image size"    value={job.config?.img_size ? `${job.config.img_size}px` : null} />
                        <KVRow label="Learning rate" value={job.config?.learning_rate} />
                        <KVRow label="Patience"      value={job.config?.patience} />
                        <KVRow label="Device"        value={job.config?.device || "auto"} />
                        <KVRow label="Strict epochs" value={job.config?.strict_epochs ? "Yes" : "No"} />
                        <KVRow label="Mode"          value={job.strict_mode ? "Strict" : "Standard"} />
                        {job.filtered_classes?.length > 0 && (
                            <div className="px-4 py-3">
                                <p className="text-xs text-muted-foreground mb-2 uppercase tracking-wide">Classes filtered</p>
                                <div className="flex flex-wrap gap-1.5">
                                    {job.filtered_classes.map(c => (
                                        <Badge key={c} variant="outline" className="text-xs">{c}</Badge>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Model file info */}
                {modelInfo && (
                    <div>
                        <SectionHeader icon={Box} title="Model File" />
                        <div className="rounded-xl border border-border overflow-hidden divide-y divide-border bg-card">
                            <KVRow label="File size" value={modelInfo.size_mb ? `${modelInfo.size_mb} MB` : null} />
                            <KVRow label="Created"   value={modelInfo.created ? new Date(modelInfo.created * 1000).toLocaleString() : null} />
                            {modelInfo.training_config?.model && (
                                <KVRow label="Architecture" value={modelInfo.training_config.model} />
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* ── Per-class metrics ── */}
            {perClass?.length > 0 && (
                <div>
                    <SectionHeader icon={ImageIcon} title="Per-Class Metrics" />
                    <div className="rounded-xl border border-border overflow-hidden bg-card">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-muted/50 border-b border-border">
                                    <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-[40%]">Class</th>
                                    <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-[15%]">Precision</th>
                                    <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-[15%]">Recall</th>
                                    <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-[15%]">mAP50</th>
                                    <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-[15%]">mAP50-95</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {perClass.map((cls) => (
                                    <tr key={cls.class_id} className="hover:bg-muted/20 transition-colors">
                                        <td className="px-4 py-3 font-medium">{cls.class_name}</td>
                                        <td className="px-4 py-3 font-mono text-xs text-right tabular-nums text-foreground/70">{formatMetricValue(cls.precision)}</td>
                                        <td className="px-4 py-3 font-mono text-xs text-right tabular-nums text-foreground/70">{formatMetricValue(cls.recall)}</td>
                                        <td className="px-4 py-3 font-mono text-xs text-right tabular-nums font-semibold text-emerald-400">{formatMetricValue(cls.mAP50)}</td>
                                        <td className="px-4 py-3 font-mono text-xs text-right tabular-nums font-semibold text-emerald-400">{formatMetricValue(cls.mAP50_95)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── Confusion matrix ── */}
            {isCompleted && !cmError && (
                <div>
                    <SectionHeader icon={BarChart2} title="Confusion Matrix" />
                    <div className="rounded-xl border border-border bg-card flex items-center justify-center p-6">
                        <img
                            src={cmUrl}
                            alt="Confusion matrix"
                            className="max-w-full max-h-[460px] rounded-lg object-contain"
                            onError={() => setCmError(true)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function ProjectVersions({ dataset, onDeploy }) {
    const [jobs, setJobs] = useState([]);
    const [versions, setVersions] = useState([]);
    const [selectedJob, setSelectedJob] = useState(null);
    const { token } = useAuth();

    const fetchJobs = async () => {
        if (!token) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/training/jobs`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                const datasetJobs = (data.jobs || []).filter(j => j.dataset_id === dataset?.id);
                setJobs(datasetJobs);
                if (selectedJob) {
                    const updated = datasetJobs.find(j => j.job_id === selectedJob.job_id);
                    if (updated) setSelectedJob(updated);
                }
            } else {
                toast.error("Failed to load training jobs");
            }
        } catch (e) {
            toast.error("Error loading jobs: " + e.message);
        }
    };

    const fetchVersions = async () => {
        if (!token || !dataset?.id) return;
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_LIST(dataset.id), {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setVersions(data.versions || []);
            }
        } catch {}
    };

    useEffect(() => {
        fetchJobs();
        fetchVersions();
        const interval = setInterval(fetchJobs, 12000);
        return () => clearInterval(interval);
    }, [token, dataset?.id]);

    const cancelJob = async (jobId) => {
        if (!window.confirm("Stop training? The run ends after the current epoch.")) return;
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.CANCEL(jobId), {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` }
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                toast.success(data.message || "Cancellation requested");
                fetchJobs();
            } else {
                toast.error(data.detail || "Failed to cancel");
            }
        } catch (e) {
            toast.error(e.message || "Cancel failed");
        }
    };

    const deleteJob = async (jobId) => {
        if (!window.confirm("Delete this training job record? This cannot be undone.")) return;
        try {
            const res = await fetch(`${API_BASE_URL}/api/training/job/${jobId}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.ok) {
                toast.success("Job deleted");
                if (selectedJob?.job_id === jobId) setSelectedJob(null);
                fetchJobs();
            } else {
                const err = await res.json().catch(() => ({}));
                toast.error(err.detail || "Failed to delete job");
            }
        } catch (e) {
            toast.error("Failed to delete job: " + e.message);
        }
    };

    // ── detail view ───────────────────────────────────────────────────────────
    if (selectedJob) {
        return (
            <div className="h-full overflow-y-auto pb-10 custom-scrollbar pr-2">
                <JobDetail
                    job={selectedJob}
                    token={token}
                    dataset={dataset}
                    versions={versions}
                    onBack={() => setSelectedJob(null)}
                    onDeploy={onDeploy}
                    onCancel={() => cancelJob(selectedJob.job_id)}
                    onDelete={() => deleteJob(selectedJob.job_id)}
                />
            </div>
        );
    }

    // ── grid view ─────────────────────────────────────────────────────────────
    const sortedJobs = jobs
        .slice()
        .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

    return (
        <div className="h-full flex flex-col gap-6 overflow-y-auto pb-10 custom-scrollbar pr-2">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Model Registry</h2>
                    <p className="text-muted-foreground text-sm mt-0.5">Click a run to inspect details, metrics, and download weights.</p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchJobs} className="gap-2">
                    <RefreshCw className="h-4 w-4" /> Refresh
                </Button>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Layers className="h-5 w-5 text-primary" />
                        Version History
                    </CardTitle>
                    <CardDescription>All training runs for this dataset — click a card to view full details</CardDescription>
                </CardHeader>
                <CardContent>
                    {sortedJobs.length === 0 ? (
                        <div className="text-center py-14 text-muted-foreground bg-muted/20 rounded-lg border border-dashed">
                            <Cpu className="mx-auto h-12 w-12 mb-4 opacity-40" />
                            <h3 className="text-base font-medium text-foreground mb-1">No Versions Yet</h3>
                            <p className="text-sm">Head over to the Train tab to start your first model training.</p>
                        </div>
                    ) : (
                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                            {sortedJobs.map((job, jobIdx) => {
                                const isCompleted = job.status === "completed" || job.status === "success";
                                const isActive = job.status === "running" || job.status === "pending";
                                const usedVersion = versions.find(v => v.id?.toString() === job.version_id?.toString());

                                const quickMetrics = [
                                    ["mAP50",    job.metrics?.map50    ?? job.metrics?.["map50"]],
                                    ["mAP50-95", job.metrics?.["map50-95"] ?? job.metrics?.["map50_95"]],
                                ].filter(([, v]) => v != null);

                                return (
                                    <button
                                        key={job.job_id || `job-${jobIdx}`}
                                        type="button"
                                        onClick={() => setSelectedJob(job)}
                                        className="group border rounded-xl p-5 bg-card/50 text-left hover:border-primary/50 hover:shadow-md transition-all flex flex-col min-h-[160px]"
                                    >
                                        {/* title row */}
                                        <div className="flex items-start justify-between gap-2 mb-3">
                                            <div className="min-w-0 flex-1">
                                                <p className="font-semibold text-base truncate leading-tight">
                                                    {job.config?.model_name || "Model"}
                                                </p>
                                                <p className="text-xs text-muted-foreground font-mono mt-0.5">
                                                    {job.job_id.substring(0, 8)}
                                                </p>
                                                {usedVersion && (
                                                    <p className="text-xs text-primary/70 mt-0.5 truncate">{usedVersion.name}</p>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-1.5 shrink-0">
                                                <StatusBadge status={job.status} />
                                                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                                            </div>
                                        </div>

                                        {/* quick config: 2-col grid for alignment */}
                                        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs mb-3">
                                            {[
                                                ["Epochs",     job.config?.epochs],
                                                ["Batch",      job.config?.batch_size],
                                                ["Image size", job.config?.img_size ? `${job.config.img_size}px` : null],
                                            ].filter(([, v]) => v != null).map(([label, val]) => (
                                                <Fragment key={label}>
                                                    <span className="text-muted-foreground">{label}</span>
                                                    <span className="font-medium text-foreground text-right tabular-nums">{val}</span>
                                                </Fragment>
                                            ))}
                                        </div>

                                        {/* running progress */}
                                        {isActive && (
                                            <div className="mt-auto pt-1">
                                                <div className="flex justify-between text-xs mb-1.5">
                                                    <span className="text-muted-foreground">
                                                        Epoch {job.current_epoch || 0}/{job.config?.epochs || "?"}
                                                    </span>
                                                    <span className="text-primary font-bold tabular-nums">
                                                        {Math.round(job.progress || 0)}%
                                                    </span>
                                                </div>
                                                <div className="w-full bg-muted-foreground/20 rounded-full h-1.5 overflow-hidden">
                                                    <div
                                                        className="bg-primary h-1.5 rounded-full transition-all duration-500"
                                                        style={{ width: `${Math.max(3, job.progress || 0)}%` }}
                                                    />
                                                </div>
                                            </div>
                                        )}

                                        {/* completed mAP chips */}
                                        {isCompleted && quickMetrics.length > 0 && (
                                            <div className="mt-auto flex gap-2">
                                                {quickMetrics.map(([label, val]) => (
                                                    <div key={label}
                                                        className="flex-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-2 py-1.5 flex flex-col items-center">
                                                        <span className="text-[10px] text-emerald-500/60 leading-none mb-0.5">{label}</span>
                                                        <span className="text-sm font-bold font-mono tabular-nums text-emerald-400">
                                                            {formatMetricValue(val)}
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {/* failed snippet */}
                                        {job.status === "failed" && (
                                            <div className="mt-auto text-xs text-red-400 px-2.5 py-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-1.5">
                                                <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                                                <span className="line-clamp-2">
                                                    {job.error ? job.error.substring(0, 80) + (job.error.length > 80 ? "…" : "") : "Training failed"}
                                                </span>
                                            </div>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
