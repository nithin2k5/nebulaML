"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { usePolling } from "@/lib/usePolling";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import {
    AlertTriangle,
    Crosshair,
    Microscope,
    RefreshCw,
    Target,
    TrendingDown,
    TrendingUp,
} from "lucide-react";

// The five failure kinds the server reports, with the reading each one implies.
// Keeping the explanation next to the label is the difference between a
// histogram and something a person can act on.
const ERROR_KINDS = [
    {
        id: "background",
        label: "Hallucinated",
        hint: "Predicted an object where there is nothing. Often wants hard negatives.",
    },
    {
        id: "wrong_class",
        label: "Wrong class",
        hint: "Found the object, named it wrong. These two classes need disambiguating.",
    },
    {
        id: "poor_localisation",
        label: "Loose box",
        hint: "Right class, box too loose to count. Box regression is weak.",
    },
    {
        id: "duplicate",
        label: "Duplicate",
        hint: "A second box on an object already found. Usually NMS is too permissive.",
    },
    {
        id: "missed",
        label: "Missed",
        hint: "A labelled object no prediction covered.",
    },
];

const SORTS = [
    { id: "precision", label: "Worst precision" },
    { id: "recall", label: "Worst recall" },
    { id: "errors", label: "Most errors" },
    { id: "false_positives", label: "Most false positives" },
    { id: "false_negatives", label: "Most misses" },
];

const pct = (value) =>
    value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;

export default function ProjectEvaluate({ dataset }) {
    const { token } = useAuth();

    const [jobs, setJobs] = useState([]);
    const [selectedJob, setSelectedJob] = useState("");
    const [versions, setVersions] = useState([]);
    // "" means the live annotations table; otherwise a frozen version's id.
    const [source, setSource] = useState("");
    const [evaluation, setEvaluation] = useState(null);
    const [runningId, setRunningId] = useState(null);
    const [progress, setProgress] = useState(null);
    const [loading, setLoading] = useState(false);

    // Error browser
    const [kind, setKind] = useState("");
    const [sort, setSort] = useState("precision");
    const [images, setImages] = useState([]);
    const [imagesTotal, setImagesTotal] = useState(0);

    // Comparison
    const [history, setHistory] = useState([]);
    const [compareWith, setCompareWith] = useState("");
    const [comparison, setComparison] = useState(null);

    const authHeaders = useMemo(
        () => ({ Authorization: `Bearer ${token}` }),
        [token]
    );

    // --- completed training runs for this dataset -------------------------
    const fetchJobs = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, { headers: authHeaders });
            if (!res.ok) return;
            const data = await res.json();
            const completed = (data.jobs || data || []).filter(
                (job) =>
                    job.status === "completed" &&
                    (!dataset?.id || job.dataset_id === dataset.id)
            );
            setJobs(completed);
            setSelectedJob((current) => current || completed[0]?.id || "");
        } catch {
            // The run picker is empty rather than broken; the panel below says so.
        }
    }, [token, authHeaders, dataset?.id]);

    // --- frozen versions available to score against -----------------------
    const fetchVersions = useCallback(async () => {
        if (!token || !dataset?.id) return;
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_LIST(dataset.id), {
                headers: authHeaders,
            });
            if (!res.ok) return;
            const data = await res.json();
            setVersions(data.versions || []);
        } catch {
            // Without versions the picker offers live labels only, which works.
        }
    }, [token, authHeaders, dataset?.id]);

    useEffect(() => {
        fetchJobs();
        fetchVersions();
    }, [fetchJobs, fetchVersions]);

    // --- the latest evaluation for the selected run -----------------------
    const fetchLatest = useCallback(async () => {
        if (!selectedJob || !token) return;
        setLoading(true);
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.LATEST(selectedJob), {
                headers: authHeaders,
            });
            if (!res.ok) {
                setEvaluation(null);
                return;
            }
            const data = await res.json();
            setEvaluation(data.evaluation || null);
        } catch {
            setEvaluation(null);
        } finally {
            setLoading(false);
        }
    }, [selectedJob, token, authHeaders]);

    const fetchHistory = useCallback(async () => {
        if (!selectedJob || !token) return;
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.HISTORY(selectedJob), {
                headers: authHeaders,
            });
            if (res.ok) {
                const data = await res.json();
                setHistory(data.evaluations || []);
            }
        } catch {
            setHistory([]);
        }
    }, [selectedJob, token, authHeaders]);

    useEffect(() => {
        setEvaluation(null);
        setImages([]);
        setComparison(null);
        setCompareWith("");
        fetchLatest();
        fetchHistory();
    }, [fetchLatest, fetchHistory]);

    // --- run an evaluation ------------------------------------------------
    const runEvaluation = async () => {
        if (!selectedJob) return;
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.RUN, {
                method: "POST",
                headers: { ...authHeaders, "Content-Type": "application/json" },
                body: JSON.stringify({
                    job_id: selectedJob,
                    split: "test",
                    // Omitted entirely when scoring live labels, so the server
                    // keeps its own default rather than being sent an empty id.
                    ...(source ? { version_id: source } : {}),
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                toast.error(data.detail || "Could not start evaluation");
                return;
            }
            setRunningId(data.evaluation_id);
            setProgress({ progress: 0, total: 0 });
            toast.success("Evaluation started");
        } catch {
            toast.error("Could not start evaluation");
        }
    };

    usePolling(
        async () => {
            if (!runningId) return;
            try {
                const res = await fetch(API_ENDPOINTS.EVALUATION.STATUS(runningId), {
                    headers: authHeaders,
                });
                if (!res.ok) {
                    setRunningId(null);
                    return;
                }
                const job = await res.json();
                setProgress(job);
                if (job.status === "completed") {
                    setRunningId(null);
                    toast.success("Evaluation complete");
                    fetchLatest();
                    fetchHistory();
                } else if (job.status === "failed") {
                    setRunningId(null);
                    toast.error(job.error || "Evaluation failed");
                }
            } catch {
                setRunningId(null);
            }
        },
        { intervalMs: 2500, idleIntervalMs: 0, active: !!runningId, enabled: !!runningId }
    );

    // --- error browser ----------------------------------------------------
    const fetchImages = useCallback(async () => {
        if (!evaluation?.id || !token) return;
        const params = new URLSearchParams({ sort, limit: "40" });
        if (kind) params.set("kind", kind);
        try {
            const res = await fetch(
                API_ENDPOINTS.EVALUATION.IMAGES(evaluation.id, `?${params}`),
                { headers: authHeaders }
            );
            if (!res.ok) return;
            const data = await res.json();
            setImages(data.images || []);
            setImagesTotal(data.total || 0);
        } catch {
            setImages([]);
        }
    }, [evaluation?.id, token, authHeaders, sort, kind]);

    useEffect(() => {
        fetchImages();
    }, [fetchImages]);

    // --- comparison -------------------------------------------------------
    const runComparison = async (otherId) => {
        setCompareWith(otherId);
        if (!otherId || !evaluation?.id) {
            setComparison(null);
            return;
        }
        try {
            const res = await fetch(
                API_ENDPOINTS.EVALUATION.COMPARE(otherId, evaluation.id),
                { headers: authHeaders }
            );
            const data = await res.json();
            if (!res.ok) {
                toast.error(data.detail || "Could not compare");
                return;
            }
            setComparison(data);
        } catch {
            toast.error("Could not compare");
        }
    };

    // --- render -----------------------------------------------------------
    if (jobs.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center p-12 text-center border rounded-none bg-card text-card-foreground">
                <Microscope className="w-12 h-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold">No trained runs yet</h3>
                <p className="text-muted-foreground mt-2 max-w-md">
                    Train a model first. Evaluation scores a finished run against a
                    held-out split and shows you which images it gets wrong.
                </p>
            </div>
        );
    }

    const metrics = evaluation?.metrics || {};
    const errorKinds = evaluation?.error_kinds || {};
    const sweep = evaluation?.confidence_sweep || [];
    const best = evaluation?.best_operating_point || null;
    const confusion = evaluation?.class_confusion || [];
    const matrix = evaluation?.confusion_matrix?.matrix || [];
    const matrixLabels = [...(dataset?.classes || []), "background"];
    const matrixMax = Math.max(1, ...matrix.flat());
    const perClass = evaluation?.per_class_metrics || [];
    const maxSweepF1 = Math.max(...sweep.map((p) => p.f1 || 0), 0.0001);

    return (
        <div className="space-y-6 h-full overflow-y-auto pb-10">
            {/* Run picker + trigger */}
            <div className="flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4">
                <div>
                    <h2 className="text-xl font-semibold">Evaluation</h2>
                    <p className="text-sm text-muted-foreground">
                        Score a run against a held-out split, then browse what it got
                        wrong and why.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <select
                        value={selectedJob}
                        onChange={(e) => setSelectedJob(e.target.value)}
                        className="text-sm bg-background border border-input rounded-none px-2 py-1.5"
                    >
                        {jobs.map((job) => (
                            <option key={job.id} value={job.id}>
                                {job.model_name || "run"} · {job.id.slice(0, 8)}
                            </option>
                        ))}
                    </select>
                    {versions.length > 0 && (
                        <select
                            value={source}
                            onChange={(e) => setSource(e.target.value)}
                            title="Which ground truth to score against"
                            className="text-sm bg-background border border-input rounded-none px-2 py-1.5"
                        >
                            <option value="">Live labels</option>
                            {versions.map((version) => (
                                <option key={version.id} value={version.id}>
                                    v{version.version_number} snapshot
                                    {version.name ? ` · ${version.name}` : ""}
                                </option>
                            ))}
                        </select>
                    )}
                    <Button size="sm" onClick={runEvaluation} disabled={!!runningId}>
                        <RefreshCw
                            className={`w-4 h-4 mr-2 ${runningId ? "animate-spin" : ""}`}
                        />
                        {runningId ? "Evaluating..." : "Run evaluation"}
                    </Button>
                </div>
            </div>

            {runningId && (
                <Alert className="bg-violet-950/20 border-violet-900/50">
                    <RefreshCw className="h-4 w-4 text-violet-400 animate-spin" />
                    <AlertTitle className="text-violet-300">Evaluation running</AlertTitle>
                    <AlertDescription className="text-violet-200/80">
                        {progress?.total
                            ? `${progress.progress ?? 0} of ${progress.total} images scored`
                            : "Loading the model and the split…"}
                    </AlertDescription>
                </Alert>
            )}

            {!evaluation && !loading && !runningId && (
                <div className="border rounded-none bg-card text-card-foreground p-8 text-center">
                    <Target className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                    <h3 className="font-semibold">This run has not been evaluated</h3>
                    <p className="text-sm text-muted-foreground mt-1 max-w-lg mx-auto">
                        Training reports a single mAP number. Running an evaluation adds
                        the per-image breakdown: which objects were missed, which boxes
                        were hallucinated, and where the confidence threshold should sit.
                    </p>
                </div>
            )}

            {evaluation && (
                <>
                    {/* Headline metrics */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        {[
                            ["mAP@50", metrics.map50],
                            ["mAP@50-95", metrics["map50-95"]],
                            ["Precision", metrics.precision],
                            ["Recall", metrics.recall],
                        ].map(([label, value]) => (
                            <Card key={label} className="rounded-none">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium text-muted-foreground">
                                        {label}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-semibold">{pct(value)}</div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    <p className="text-xs text-muted-foreground">
                        Scored on {evaluation.images_evaluated} image(s) of the{" "}
                        <span className="text-foreground">{evaluation.split}</span> split
                        at IoU {evaluation.iou_threshold} and confidence{" "}
                        {evaluation.conf_threshold}
                        {evaluation.version_id ? (
                            <>
                                , against a <span className="text-foreground">frozen
                                snapshot</span> — the data training actually consumed.
                            </>
                        ) : (
                            <>, against the current labels.</>
                        )}
                        {evaluation.split === "all-annotated" && (
                            <span className="text-yellow-500">
                                {" "}
                                This project has no test or val split, so these numbers
                                include images the model trained on — treat them as
                                optimistic.
                            </span>
                        )}
                    </p>

                    {/* Error kinds */}
                    <Card className="rounded-none">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                                <AlertTriangle className="w-4 h-4 text-orange-400" />
                                How it fails
                            </CardTitle>
                            <CardDescription>
                                Every mistake, sorted into the kind of fix it implies.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                                {ERROR_KINDS.map((entry) => {
                                    const count = errorKinds[entry.id] || 0;
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
                                            <div className="text-xs font-medium mt-1">
                                                {entry.label}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                            <p className="text-xs text-muted-foreground mt-3">
                                {kind
                                    ? ERROR_KINDS.find((e) => e.id === kind)?.hint
                                    : "Click a kind to filter the image list below."}
                            </p>
                        </CardContent>
                    </Card>

                    {/* Confidence sweep */}
                    {sweep.length > 0 && (
                        <Card className="rounded-none">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Crosshair className="w-4 h-4 text-violet-400" />
                                    Where to set the confidence threshold
                                </CardTitle>
                                <CardDescription>
                                    {best
                                        ? `F1 peaks at ${best.threshold} — precision ${pct(
                                              best.precision
                                          )}, recall ${pct(best.recall)}.`
                                        : "Precision and recall across thresholds."}
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-end gap-1 h-32">
                                    {sweep.map((point) => (
                                        <div
                                            key={point.threshold}
                                            className="flex-1 flex flex-col justify-end h-full group relative"
                                            title={`conf ${point.threshold} · P ${pct(
                                                point.precision
                                            )} · R ${pct(point.recall)} · F1 ${pct(point.f1)}`}
                                        >
                                            <div
                                                className={`w-full transition-colors ${
                                                    best && point.threshold === best.threshold
                                                        ? "bg-violet-400"
                                                        : "bg-violet-500/40 group-hover:bg-violet-500/70"
                                                }`}
                                                style={{
                                                    height: `${((point.f1 || 0) / maxSweepF1) * 100}%`,
                                                }}
                                            />
                                        </div>
                                    ))}
                                </div>
                                <div className="flex justify-between text-xs text-muted-foreground mt-2">
                                    <span>{sweep[0]?.threshold}</span>
                                    <span>F1 by confidence threshold</span>
                                    <span>{sweep[sweep.length - 1]?.threshold}</span>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Class confusion */}
                    {confusion.length > 0 && (
                        <Card className="rounded-none">
                            <CardHeader>
                                <CardTitle className="text-base">
                                    Classes it actually confuses
                                </CardTitle>
                                <CardDescription>
                                    Only pairs that genuinely collide, named in both
                                    directions.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-1">
                                {confusion.slice(0, 8).map((row) => (
                                    <div
                                        key={`${row.actual}->${row.predicted}`}
                                        className="flex items-center justify-between text-sm border-b border-white/5 py-1.5 last:border-0"
                                    >
                                        <span>
                                            <span className="text-foreground">{row.actual}</span>
                                            <span className="text-muted-foreground"> called </span>
                                            <span className="text-orange-400">{row.predicted}</span>
                                        </span>
                                        <span className="text-muted-foreground">
                                            {row.count}×
                                        </span>
                                    </div>
                                ))}
                            </CardContent>
                        </Card>
                    )}

                    {/* Full confusion matrix */}
                    {matrix.length > 0 && (
                        <Card className="rounded-none">
                            <CardHeader>
                                <CardTitle className="text-base">
                                    Confusion matrix
                                </CardTitle>
                                <CardDescription>
                                    The whole picture, including what was missed outright
                                    versus invented. Rows sum to the labelled boxes per
                                    class, columns to the predictions.
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="overflow-x-auto">
                                    <table className="text-xs font-mono border-collapse">
                                        <thead>
                                            <tr>
                                                <th className="p-1.5 text-right font-normal text-muted-foreground">
                                                    actual ↓ / predicted →
                                                </th>
                                                {matrixLabels.map((label) => (
                                                    <th
                                                        key={label}
                                                        className="p-1.5 font-normal text-muted-foreground whitespace-nowrap"
                                                    >
                                                        {label}
                                                    </th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {matrix.map((row, rowIndex) => (
                                                <tr key={matrixLabels[rowIndex] || rowIndex}>
                                                    <th className="p-1.5 text-right font-normal text-muted-foreground whitespace-nowrap">
                                                        {matrixLabels[rowIndex]}
                                                    </th>
                                                    {row.map((value, colIndex) => (
                                                        <td
                                                            key={colIndex}
                                                            title={`${matrixLabels[rowIndex]} predicted as ${matrixLabels[colIndex]}: ${value}`}
                                                            className={`p-1.5 text-center border border-background min-w-[44px] ${
                                                                rowIndex === colIndex
                                                                    ? "ring-1 ring-inset ring-foreground/20"
                                                                    : ""
                                                            }`}
                                                            style={{
                                                                // One hue, intensity by magnitude. The
                                                                // count is printed in every cell, so the
                                                                // reading never rests on colour alone.
                                                                background: value
                                                                    ? `rgba(139, 92, 246, ${
                                                                          0.12 + (value / matrixMax) * 0.68
                                                                      })`
                                                                    : "transparent",
                                                            }}
                                                        >
                                                            {value || "·"}
                                                        </td>
                                                    ))}
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                                <p className="text-xs text-muted-foreground mt-2">
                                    Boxes are paired ignoring their label here, so a dog
                                    called a cat lands at dog → cat rather than as a missed
                                    dog plus an invented cat.
                                </p>
                            </CardContent>
                        </Card>
                    )}

                    {/* Per-class table */}
                    {perClass.length > 0 && (
                        <Card className="rounded-none">
                            <CardHeader>
                                <CardTitle className="text-base">Per class</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="text-left text-muted-foreground border-b border-white/10">
                                                <th className="py-2 pr-4 font-medium">Class</th>
                                                <th className="py-2 pr-4 font-medium">mAP@50</th>
                                                <th className="py-2 pr-4 font-medium">Precision</th>
                                                <th className="py-2 font-medium">Recall</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {[...perClass]
                                                .sort((a, b) => (a.mAP50 || 0) - (b.mAP50 || 0))
                                                .map((row) => (
                                                    <tr
                                                        key={row.class_name}
                                                        className="border-b border-white/5 last:border-0"
                                                    >
                                                        <td className="py-2 pr-4">{row.class_name}</td>
                                                        <td className="py-2 pr-4">{pct(row.mAP50)}</td>
                                                        <td className="py-2 pr-4">{pct(row.precision)}</td>
                                                        <td className="py-2">{pct(row.recall)}</td>
                                                    </tr>
                                                ))}
                                        </tbody>
                                    </table>
                                </div>
                                <p className="text-xs text-muted-foreground mt-2">
                                    Weakest class first — that is where the next batch of
                                    labels pays off most.
                                </p>
                            </CardContent>
                        </Card>
                    )}

                    {/* Error browser */}
                    <Card className="rounded-none">
                        <CardHeader>
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                                <div>
                                    <CardTitle className="text-base">
                                        Images, worst first
                                    </CardTitle>
                                    <CardDescription>
                                        {imagesTotal} image(s) match
                                        {kind
                                            ? ` the "${
                                                  ERROR_KINDS.find((e) => e.id === kind)?.label
                                              }" filter`
                                            : ""}
                                        .
                                    </CardDescription>
                                </div>
                                <select
                                    value={sort}
                                    onChange={(e) => setSort(e.target.value)}
                                    className="text-sm bg-background border border-input rounded-none px-2 py-1"
                                >
                                    {SORTS.map((option) => (
                                        <option key={option.id} value={option.id}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {images.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                    Nothing matches this filter.
                                </p>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="text-left text-muted-foreground border-b border-white/10">
                                                <th className="py-2 pr-4 font-medium">Image</th>
                                                <th className="py-2 pr-4 font-medium">Hits</th>
                                                <th className="py-2 pr-4 font-medium">False +</th>
                                                <th className="py-2 pr-4 font-medium">Missed</th>
                                                <th className="py-2 pr-4 font-medium">Precision</th>
                                                <th className="py-2 font-medium">Recall</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {images.map((row) => (
                                                <tr
                                                    key={row.image_id}
                                                    className="border-b border-white/5 last:border-0"
                                                >
                                                    <td className="py-2 pr-4 truncate max-w-[16rem]">
                                                        {row.filename}
                                                    </td>
                                                    <td className="py-2 pr-4">{row.tp}</td>
                                                    <td className="py-2 pr-4 text-orange-400">
                                                        {row.fp}
                                                    </td>
                                                    <td className="py-2 pr-4 text-red-400">
                                                        {row.fn}
                                                    </td>
                                                    <td className="py-2 pr-4">
                                                        {pct(row.precision_score)}
                                                    </td>
                                                    <td className="py-2">{pct(row.recall_score)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Compare runs */}
                    {history.length > 1 && (
                        <Card className="rounded-none">
                            <CardHeader>
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                                    <div>
                                        <CardTitle className="text-base">
                                            Compare with an earlier evaluation
                                        </CardTitle>
                                        <CardDescription>
                                            Per-class deltas, worst regression first.
                                        </CardDescription>
                                    </div>
                                    <select
                                        value={compareWith}
                                        onChange={(e) => runComparison(e.target.value)}
                                        className="text-sm bg-background border border-input rounded-none px-2 py-1"
                                    >
                                        <option value="">Pick a baseline…</option>
                                        {history
                                            .filter((row) => row.id !== evaluation.id)
                                            .map((row) => (
                                                <option key={row.id} value={row.id}>
                                                    {row.split} · {row.id.slice(0, 8)}
                                                </option>
                                            ))}
                                    </select>
                                </div>
                            </CardHeader>
                            {comparison && (
                                <CardContent>
                                    {comparison.summary?.worst_regression ? (
                                        <Alert className="bg-red-950/20 border-red-900/50 mb-4">
                                            <TrendingDown className="h-4 w-4 text-red-400" />
                                            <AlertTitle className="text-red-300">
                                                Worst regression
                                            </AlertTitle>
                                            <AlertDescription className="text-red-200/80">
                                                {comparison.summary.worst_regression.class_name} lost{" "}
                                                {Math.abs(
                                                    comparison.summary.worst_regression.delta * 100
                                                ).toFixed(1)}{" "}
                                                points of {comparison.metric}, while overall mAP@50
                                                went from {pct(comparison.a.metrics?.map50)} to{" "}
                                                {pct(comparison.b.metrics?.map50)}.
                                            </AlertDescription>
                                        </Alert>
                                    ) : (
                                        <Alert className="bg-emerald-950/20 border-emerald-900/50 mb-4">
                                            <TrendingUp className="h-4 w-4 text-emerald-400" />
                                            <AlertTitle className="text-emerald-300">
                                                No class regressed
                                            </AlertTitle>
                                            <AlertDescription className="text-emerald-200/80">
                                                {comparison.summary?.improved || 0} class(es)
                                                improved.
                                            </AlertDescription>
                                        </Alert>
                                    )}

                                    <div className="space-y-1">
                                        {(comparison.per_class || []).map((row) => (
                                            <div
                                                key={row.class_name}
                                                className="flex items-center justify-between text-sm border-b border-white/5 py-1.5 last:border-0"
                                            >
                                                <span>{row.class_name}</span>
                                                <span className="flex items-center gap-3">
                                                    <span className="text-muted-foreground">
                                                        {pct(row.a)} → {pct(row.b)}
                                                    </span>
                                                    <span
                                                        className={
                                                            row.delta === null
                                                                ? "text-muted-foreground"
                                                                : row.delta < 0
                                                                  ? "text-red-400"
                                                                  : row.delta > 0
                                                                    ? "text-emerald-400"
                                                                    : "text-muted-foreground"
                                                        }
                                                    >
                                                        {row.delta === null
                                                            ? row.status
                                                            : `${row.delta > 0 ? "+" : ""}${(
                                                                  row.delta * 100
                                                              ).toFixed(1)}`}
                                                    </span>
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            )}
                        </Card>
                    )}
                </>
            )}
        </div>
    );
}
