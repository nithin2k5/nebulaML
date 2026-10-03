"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { usePolling } from "@/lib/usePolling";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { toast } from "sonner";
import { Check, RefreshCw, ScanSearch, X } from "lucide-react";

// Each kind implies a different fix, so the label and the hint travel together.
const KINDS = [
    {
        id: "wrong_class",
        label: "Wrong class",
        hint: "The box is right, the label is not.",
    },
    {
        id: "missing_label",
        label: "Missing label",
        hint: "An object nobody drew a box around.",
    },
    {
        id: "spurious_label",
        label: "Empty box",
        hint: "A box the model sees nothing in.",
    },
    {
        id: "loose_box",
        label: "Loose box",
        hint: "Right class, but the extent is off.",
    },
];

export default function LabelAuditPanel({ datasetId }) {
    const { token } = useAuth();

    const [jobs, setJobs] = useState([]);
    const [selectedJob, setSelectedJob] = useState("");
    const [summary, setSummary] = useState(null);
    const [findings, setFindings] = useState([]);
    const [kind, setKind] = useState("");
    const [auditId, setAuditId] = useState(null);
    const [progress, setProgress] = useState(null);
    const [resolving, setResolving] = useState(false);

    const authHeaders = useMemo(
        () => ({ Authorization: `Bearer ${token}` }),
        [token]
    );

    const fetchJobs = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, { headers: authHeaders });
            if (!res.ok) return;
            const data = await res.json();
            const completed = (data.jobs || data || []).filter(
                (job) => job.status === "completed" && job.dataset_id === datasetId
            );
            setJobs(completed);
            setSelectedJob((current) => current || completed[0]?.id || "");
        } catch {
            // No runs to audit with; the empty state below explains that.
        }
    }, [token, authHeaders, datasetId]);

    const fetchSummary = useCallback(async () => {
        if (!datasetId || !token) return;
        try {
            const res = await fetch(API_ENDPOINTS.LABEL_AUDIT.SUMMARY(datasetId), {
                headers: authHeaders,
            });
            if (res.ok) setSummary(await res.json());
        } catch {
            setSummary(null);
        }
    }, [datasetId, token, authHeaders]);

    const fetchFindings = useCallback(async () => {
        if (!datasetId || !token) return;
        const params = new URLSearchParams({ status: "open", limit: "30" });
        if (kind) params.set("kind", kind);
        try {
            const res = await fetch(
                API_ENDPOINTS.LABEL_AUDIT.FINDINGS(datasetId, `?${params}`),
                { headers: authHeaders }
            );
            if (res.ok) {
                const data = await res.json();
                setFindings(data.findings || []);
            }
        } catch {
            setFindings([]);
        }
    }, [datasetId, token, authHeaders, kind]);

    useEffect(() => {
        fetchJobs();
        fetchSummary();
    }, [fetchJobs, fetchSummary]);

    useEffect(() => {
        fetchFindings();
    }, [fetchFindings]);

    const runAudit = async () => {
        if (!selectedJob) return;
        try {
            const res = await fetch(API_ENDPOINTS.LABEL_AUDIT.RUN, {
                method: "POST",
                headers: { ...authHeaders, "Content-Type": "application/json" },
                body: JSON.stringify({ dataset_id: datasetId, job_id: selectedJob }),
            });
            const data = await res.json();
            if (!res.ok) {
                toast.error(data.detail || "Could not start the audit");
                return;
            }
            setAuditId(data.audit_id);
            setProgress({ progress: 0, total: 0 });
            toast.success("Auditing labels…");
        } catch {
            toast.error("Could not start the audit");
        }
    };

    usePolling(
        async () => {
            if (!auditId) return;
            try {
                const res = await fetch(API_ENDPOINTS.LABEL_AUDIT.STATUS(auditId), {
                    headers: authHeaders,
                });
                if (!res.ok) {
                    setAuditId(null);
                    return;
                }
                const job = await res.json();
                setProgress(job);
                if (job.status === "completed") {
                    setAuditId(null);
                    toast.success(
                        `${job.findings ?? 0} suspect label(s) across ${
                            job.images_scanned ?? 0
                        } image(s)`
                    );
                    fetchSummary();
                    fetchFindings();
                } else if (job.status === "failed") {
                    setAuditId(null);
                    toast.error(job.error || "The audit failed");
                }
            } catch {
                setAuditId(null);
            }
        },
        { intervalMs: 2500, idleIntervalMs: 0, active: !!auditId, enabled: !!auditId }
    );

    const resolve = async (findingId, status) => {
        setResolving(true);
        try {
            const res = await fetch(API_ENDPOINTS.LABEL_AUDIT.RESOLVE(datasetId), {
                method: "POST",
                headers: { ...authHeaders, "Content-Type": "application/json" },
                body: JSON.stringify({ finding_ids: [findingId], status }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                toast.error(data.detail || "Could not update that finding");
                return;
            }
            // Drop it locally rather than refetching the whole page, so a
            // reviewer working down the list does not lose their place.
            setFindings((prev) => prev.filter((f) => f.id !== findingId));
            fetchSummary();
        } catch {
            toast.error("Could not update that finding");
        } finally {
            setResolving(false);
        }
    };

    if (jobs.length === 0) {
        return (
            <Card className="rounded-none">
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        <ScanSearch className="w-4 h-4 text-violet-400" />
                        Label Audit
                    </CardTitle>
                    <CardDescription>
                        Once this project has a trained model, it can proofread its own
                        labels — flagging boxes the model confidently disagrees with.
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    const total = summary?.total ?? 0;

    return (
        <Card className="rounded-none">
            <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div>
                        <CardTitle className="text-base flex items-center gap-2">
                            <ScanSearch className="w-4 h-4 text-violet-400" />
                            Label Audit
                        </CardTitle>
                        <CardDescription>
                            Annotations a confident model disagrees with. {total} open
                            finding{total === 1 ? "" : "s"}.
                        </CardDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <select
                            value={selectedJob}
                            onChange={(e) => setSelectedJob(e.target.value)}
                            className="text-sm bg-background border border-input rounded-none px-2 py-1"
                        >
                            {jobs.map((job) => (
                                <option key={job.id} value={job.id}>
                                    {job.model_name || "run"} · {job.id.slice(0, 8)}
                                </option>
                            ))}
                        </select>
                        <Button size="sm" onClick={runAudit} disabled={!!auditId}>
                            <RefreshCw
                                className={`w-4 h-4 mr-2 ${auditId ? "animate-spin" : ""}`}
                            />
                            {auditId ? "Auditing..." : "Audit labels"}
                        </Button>
                    </div>
                </div>
            </CardHeader>

            <CardContent className="space-y-4">
                {auditId && (
                    <p className="text-xs text-violet-300/80">
                        {progress?.total
                            ? `${progress.progress ?? 0} of ${progress.total} images checked`
                            : "Loading the model…"}
                    </p>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {KINDS.map((entry) => {
                        const count = summary?.by_kind?.[entry.id] ?? 0;
                        const isActive = kind === entry.id;
                        return (
                            <button
                                key={entry.id}
                                type="button"
                                title={entry.hint}
                                onClick={() => setKind(isActive ? "" : entry.id)}
                                className={`text-left border rounded-none p-3 transition-colors ${
                                    isActive
                                        ? "border-primary bg-primary/10"
                                        : "border-white/10 hover:bg-white/5"
                                }`}
                            >
                                <div className="text-2xl font-semibold">{count}</div>
                                <div className="text-xs font-medium mt-1">{entry.label}</div>
                            </button>
                        );
                    })}
                </div>

                {summary?.confused_pairs?.length > 0 && (
                    <div className="text-xs text-muted-foreground space-y-1">
                        <p className="text-foreground">Most often mislabelled:</p>
                        {summary.confused_pairs.slice(0, 5).map((pair) => (
                            <div key={`${pair.labelled}->${pair.model_says}`}>
                                • {pair.count}× labelled{" "}
                                <span className="text-foreground">{pair.labelled}</span>, model
                                says <span className="text-orange-400">{pair.model_says}</span>
                            </div>
                        ))}
                    </div>
                )}

                {findings.length > 0 && (
                    <div className="space-y-2">
                        {findings.map((finding) => (
                            <div
                                key={finding.id}
                                className="flex items-start justify-between gap-3 border border-white/10 rounded-none p-3"
                            >
                                <div className="min-w-0">
                                    <div className="text-sm truncate">
                                        {finding.filename || finding.image_id}
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-0.5">
                                        {finding.detail?.note ||
                                            KINDS.find((k) => k.id === finding.kind)?.hint}
                                        {finding.confidence != null && (
                                            <span className="text-violet-300/70">
                                                {" "}
                                                ({Math.round(finding.confidence * 100)}% sure)
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-1 shrink-0">
                                    <Button
                                        variant="outline"
                                        size="icon"
                                        aria-label="Mark fixed"
                                        title="I fixed this label"
                                        className="h-8 w-8"
                                        disabled={resolving}
                                        onClick={() => resolve(finding.id, "fixed")}
                                    >
                                        <Check className="h-4 w-4" />
                                    </Button>
                                    <Button
                                        variant="outline"
                                        size="icon"
                                        aria-label="Dismiss"
                                        title="The label is fine — do not flag it again"
                                        className="h-8 w-8"
                                        disabled={resolving}
                                        onClick={() => resolve(finding.id, "dismissed")}
                                    >
                                        <X className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {total === 0 && !auditId && (
                    <p className="text-sm text-muted-foreground">
                        No open findings. Run an audit to check this project&apos;s labels
                        against one of its models.
                    </p>
                )}

                {summary?.caveat && total > 0 && (
                    <p className="text-xs text-muted-foreground border-t border-white/5 pt-3">
                        {summary.caveat}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
