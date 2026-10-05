"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
    CartesianGrid,
    Line,
    LineChart,
    Legend,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import {
    AlertTriangle,
    Boxes,
    CheckCircle,
    Copy,
    Crosshair,
    EyeOff,
    GitCompare,
    Loader,
    RefreshCw,
    Target,
    Trash2,
    XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { usePolling } from "@/lib/usePolling";
import { cn } from "@/lib/utils";

// ── Palette ──────────────────────────────────────────────────────────────────
// Validated with the dataviz validator against this page's black surface:
//   validate_palette.js "#059669,#8b5cf6,#d97706" --mode dark --surface "#000000"
// Declared in that order on purpose — violet sits between the green and the
// amber, which is what carries the adjacent-pair CVD separation. Swapping two
// entries round re-introduces a green/amber adjacency that only WARNs.
const SERIES = [
    { key: "precision", label: "Precision", color: "#059669" },
    { key: "recall", label: "Recall", color: "#8b5cf6" },
    { key: "f1", label: "F1", color: "#d97706" },
];

// Single-hue magnitude ramp, dim → bright. On a black surface a sequential
// ramp has to brighten with value; a conventional light→dark violet put its
// high end at 1.4:1 against the page and disappeared.
//   validate_palette.js "#6d28d9,#8b5cf6,#a78bfa,#c4b5fd,#ddd6fe" --ordinal
const HEAT = ["#6d28d9", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"];

// Reserved status colors, each shipped with a label or an icon rather than
// standing on hue alone.
const OUTCOME = {
    tp: { color: "#34d399", label: "Correct", icon: CheckCircle },
    fp: { color: "#f87171", label: "False positive", icon: XCircle },
    fn: { color: "#fbbf24", label: "Missed", icon: EyeOff },
};

// The diagnosis vocabulary, in the order the breakdown lists it: what the model
// got right, then the mistakes roughly from least to most serious.
const ERROR_TYPES = [
    { key: "correct", label: "Correct", hint: "Matched a same-class box at the IoU threshold." },
    { key: "duplicate", label: "Duplicate", hint: "A second box on an object already found.", icon: Copy },
    { key: "poor_localization", label: "Poor localisation", hint: "Right class, box too loose to count.", icon: Crosshair },
    { key: "wrong_class", label: "Wrong class", hint: "Found a real object and labelled it wrong.", icon: AlertTriangle },
    { key: "background", label: "Background", hint: "Invented where there was nothing.", icon: Boxes },
    { key: "missed", label: "Missed", hint: "A ground-truth box nothing claimed.", icon: EyeOff },
];

const pct = (value) => (value == null ? "—" : `${(value * 100).toFixed(1)}%`);
const num = (value) => (value == null ? "—" : Number(value).toLocaleString());

function signed(value) {
    if (value == null) return "—";
    const points = value * 100;
    if (Math.abs(points) < 0.05) return "0.0";
    return `${points > 0 ? "+" : ""}${points.toFixed(1)}`;
}

// ── Small pieces ─────────────────────────────────────────────────────────────

function RunStatus({ status, progress }) {
    const map = {
        pending: { cls: "bg-white/10 text-gray-400 border-white/10", label: "Queued" },
        running: { cls: "bg-blue-500/20 text-blue-400 border-blue-500/30", label: `Scoring ${progress || 0}%` },
        completed: { cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30", label: "Done" },
        failed: { cls: "bg-red-500/20 text-red-400 border-red-500/30", label: "Failed" },
    };
    const cfg = map[status] || map.pending;
    return <Badge className={cn("gap-1 border text-[10px]", cfg.cls)}>{cfg.label}</Badge>;
}

function MetricTile({ label, value, hint, accent = "text-white" }) {
    return (
        <div className="p-3 bg-white/[0.03] border border-white/5">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
            <p className={cn("text-xl font-mono font-semibold mt-1", accent)}>{value}</p>
            {hint && <p className="text-[10px] text-gray-600 mt-1">{hint}</p>}
        </div>
    );
}

// ── Threshold sweep ──────────────────────────────────────────────────────────

function SweepChart({ runId, confThreshold }) {
    const { token } = useAuth();
    const [sweep, setSweep] = useState([]);
    const [best, setBest] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            setLoading(true);
            try {
                const res = await fetch(API_ENDPOINTS.EVALUATION.SWEEP(runId), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (res.ok && !cancelled) {
                    const data = await res.json();
                    setSweep(data.sweep || []);
                    setBest(data.best_f1 || null);
                }
            } catch (e) {
                console.error(e);
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [runId, token]);

    if (loading) {
        return <p className="text-xs text-gray-500 py-8 text-center">Loading sweep…</p>;
    }
    if (!sweep.length) {
        return <p className="text-xs text-gray-500 py-8 text-center">No sweep recorded for this run.</p>;
    }

    return (
        <div>
            <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={sweep} margin={{ top: 8, right: 16, bottom: 4, left: -16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                        <XAxis
                            dataKey="conf"
                            stroke="#555"
                            fontSize={10}
                            tickFormatter={(v) => v.toFixed(2)}
                        />
                        {/* One axis: all three series are ratios on the same 0–1 scale. */}
                        <YAxis
                            stroke="#555"
                            fontSize={10}
                            domain={[0, 1]}
                            tickFormatter={(v) => `${Math.round(v * 100)}%`}
                        />
                        <Tooltip
                            contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 11 }}
                            labelFormatter={(v) => `Confidence ${Number(v).toFixed(2)}`}
                            formatter={(value, name) => [pct(value), name]}
                        />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        {SERIES.map((series) => (
                            <Line
                                key={series.key}
                                type="monotone"
                                dataKey={series.key}
                                name={series.label}
                                stroke={series.color}
                                strokeWidth={2}
                                dot={false}
                                activeDot={{ r: 4 }}
                            />
                        ))}
                    </LineChart>
                </ResponsiveContainer>
            </div>
            <p className="text-[11px] text-gray-500 mt-2">
                Every point re-counts the whole split with weaker predictions dropped, so these are
                the numbers the deployed model would produce.
                {best && (
                    <>
                        {" "}Best F1 is <span className="text-amber-400 font-mono">{pct(best.f1)}</span>{" "}
                        at confidence <span className="text-amber-400 font-mono">{best.conf.toFixed(2)}</span>
                        {Math.abs(best.conf - confThreshold) > 0.01 && (
                            <> — this run was scored at <span className="font-mono">{confThreshold.toFixed(2)}</span>.</>
                        )}
                    </>
                )}
            </p>
        </div>
    );
}

// ── Per-class table ──────────────────────────────────────────────────────────

function PerClassTable({ perClass }) {
    // Worst first: the point of the table is to find what to fix.
    const rows = useMemo(
        () => [...(perClass || [])].sort((a, b) => (a.mAP50 ?? 0) - (b.mAP50 ?? 0)),
        [perClass]
    );

    if (!rows.length) {
        return <p className="text-xs text-gray-500">No per-class metrics recorded.</p>;
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs">
                <thead>
                    <tr className="text-[10px] uppercase text-gray-500 border-b border-white/10">
                        <th className="text-left py-2 font-medium">Class</th>
                        <th className="text-right py-2 font-medium">mAP@50</th>
                        <th className="text-right py-2 font-medium">mAP@50-95</th>
                        <th className="text-right py-2 font-medium">Precision</th>
                        <th className="text-right py-2 font-medium">Recall</th>
                        <th className="text-right py-2 font-medium">TP</th>
                        <th className="text-right py-2 font-medium">FP</th>
                        <th className="text-right py-2 font-medium">FN</th>
                    </tr>
                </thead>
                <tbody className="font-mono">
                    {rows.map((row) => (
                        <tr key={row.class_id} className="border-b border-white/5">
                            <td className="py-2 font-sans text-gray-200">{row.class_name}</td>
                            <td className="text-right py-2">
                                <span className="inline-flex items-center gap-2 justify-end">
                                    {/* A bar as well as the number: magnitude is easier to scan. */}
                                    <span className="w-14 h-1 bg-white/10 hidden sm:inline-block">
                                        <span
                                            className="block h-full"
                                            style={{
                                                width: `${Math.max(0, Math.min(1, row.mAP50)) * 100}%`,
                                                background: HEAT[3],
                                            }}
                                        />
                                    </span>
                                    {pct(row.mAP50)}
                                </span>
                            </td>
                            <td className="text-right py-2 text-gray-400">{pct(row.mAP50_95)}</td>
                            <td className="text-right py-2 text-gray-400">{pct(row.precision)}</td>
                            <td className="text-right py-2 text-gray-400">{pct(row.recall)}</td>
                            <td className="text-right py-2 text-emerald-400">{num(row.tp)}</td>
                            <td className="text-right py-2 text-red-400">{num(row.fp)}</td>
                            <td className="text-right py-2 text-amber-400">{num(row.fn)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ── Confusion matrix ─────────────────────────────────────────────────────────

function ConfusionMatrix({ confusion, classNames }) {
    const matrix = confusion?.matrix;
    if (!matrix?.length) {
        return <p className="text-xs text-gray-500">No confusion matrix recorded.</p>;
    }

    const labels = [...(classNames || []), "background"];
    const max = Math.max(1, ...matrix.flat());

    // Value → one of five steps of a single hue. The number is printed in every
    // cell regardless, so the reading never depends on colour alone.
    const shade = (value) => {
        if (!value) return null;
        const step = Math.min(HEAT.length - 1, Math.floor((value / max) * HEAT.length));
        return HEAT[step];
    };

    return (
        <div className="overflow-x-auto">
            <table className="text-[10px] font-mono border-collapse">
                <thead>
                    <tr>
                        <th className="p-1.5 text-right text-gray-600 font-normal">actual ↓ / predicted →</th>
                        {labels.map((label) => (
                            <th key={label} className="p-1.5 text-gray-400 font-normal whitespace-nowrap">
                                {label}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {matrix.map((row, rowIndex) => (
                        <tr key={labels[rowIndex]}>
                            <th className="p-1.5 text-right text-gray-400 font-normal whitespace-nowrap">
                                {labels[rowIndex]}
                            </th>
                            {row.map((value, colIndex) => {
                                const background = shade(value);
                                return (
                                    <td
                                        key={colIndex}
                                        title={`${labels[rowIndex]} predicted as ${labels[colIndex]}: ${value}`}
                                        className={cn(
                                            "p-1.5 text-center border border-black min-w-[44px]",
                                            rowIndex === colIndex && "ring-1 ring-inset ring-white/25",
                                            background ? "text-black font-semibold" : "text-gray-700"
                                        )}
                                        style={background ? { background } : undefined}
                                    >
                                        {value || "·"}
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
            <p className="text-[11px] text-gray-500 mt-2">
                Boxes are paired ignoring their label here, so a dog called &ldquo;cat&rdquo; lands at
                dog → cat rather than as a missed dog plus an invented cat. Rows sum to the ground
                truth per class, columns to the predictions. The last row and column are background.
            </p>
        </div>
    );
}

// ── Error breakdown ──────────────────────────────────────────────────────────

function ErrorBreakdown({ errorTypes, activeFilter, onFilter }) {
    const total = Math.max(1, ...Object.values(errorTypes || {}));
    const present = ERROR_TYPES.filter((type) => (errorTypes || {})[type.key] != null);

    if (!present.length) {
        return <p className="text-xs text-gray-500">No per-box detail recorded.</p>;
    }

    return (
        <div className="space-y-1.5">
            {present.map((type) => {
                const count = errorTypes[type.key] || 0;
                const Icon = type.icon;
                const active = activeFilter === type.key;
                return (
                    <button
                        key={type.key}
                        onClick={() => onFilter(active ? null : type.key)}
                        title={type.hint}
                        className={cn(
                            "w-full flex items-center gap-3 px-2 py-1.5 text-left transition-colors",
                            "border", active ? "border-violet-500/50 bg-violet-500/10" : "border-transparent hover:bg-white/5"
                        )}
                    >
                        <span className="w-32 shrink-0 flex items-center gap-1.5 text-[11px] text-gray-300">
                            {Icon ? <Icon className="w-3 h-3 text-gray-500" /> : <span className="w-3" />}
                            {type.label}
                        </span>
                        {/* One hue: these bars all encode the same measure. */}
                        <span className="flex-1 h-2 bg-white/[0.06]">
                            <span
                                className="block h-full"
                                style={{
                                    width: `${(count / total) * 100}%`,
                                    background: type.key === "correct" ? OUTCOME.tp.color : HEAT[2],
                                }}
                            />
                        </span>
                        <span className="w-14 text-right text-[11px] font-mono text-gray-400">{num(count)}</span>
                    </button>
                );
            })}
            <p className="text-[11px] text-gray-500 pt-1">
                Click a kind to filter the images below. These are different bugs: wrong class and
                poor localisation are labelling and regression problems, and only background is
                purely a detection failure.
            </p>
        </div>
    );
}

// ── Failure explorer ─────────────────────────────────────────────────────────

function BoxOverlay({ runId, filename, width, height }) {
    const { token } = useAuth();
    const [detail, setDetail] = useState(null);
    const [hidden, setHidden] = useState({ tp: false, fp: false, fn: false });

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const res = await fetch(API_ENDPOINTS.EVALUATION.IMAGE_DETAIL(runId, filename), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (res.ok && !cancelled) setDetail(await res.json());
            } catch (e) {
                console.error(e);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [runId, filename, token]);

    const boxes = detail?.boxes || [];

    return (
        <div>
            <div className="flex items-center gap-3 mb-2 flex-wrap">
                {Object.entries(OUTCOME).map(([key, cfg]) => {
                    const Icon = cfg.icon;
                    const count = boxes.filter((b) => b.outcome === key).length;
                    return (
                        <button
                            key={key}
                            onClick={() => setHidden((h) => ({ ...h, [key]: !h[key] }))}
                            className={cn(
                                "flex items-center gap-1.5 px-2 py-1 border text-[10px] uppercase tracking-wider",
                                hidden[key]
                                    ? "border-white/10 text-gray-600"
                                    : "border-white/20 text-gray-200"
                            )}
                        >
                            <Icon className="w-3 h-3" style={{ color: hidden[key] ? undefined : cfg.color }} />
                            {cfg.label}
                            <span className="font-mono">{count}</span>
                        </button>
                    );
                })}
            </div>

            <div className="relative bg-black border border-white/10 inline-block max-w-full">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                    src={API_ENDPOINTS.EVALUATION.GET_IMAGE(runId, filename, token)}
                    alt={filename}
                    className="block max-w-full h-auto"
                />
                <svg
                    viewBox={`0 0 ${width} ${height}`}
                    className="absolute inset-0 w-full h-full"
                    preserveAspectRatio="none"
                >
                    {boxes.map((box, index) => {
                        const cfg = OUTCOME[box.outcome];
                        if (!cfg || hidden[box.outcome]) return null;
                        // A missed box has no prediction, so its own geometry is
                        // the ground-truth rectangle.
                        const rect = box.box || box.gt_box;
                        if (!rect) return null;
                        const [x1, y1, x2, y2] = rect;
                        return (
                            <g key={index}>
                                <rect
                                    x={x1}
                                    y={y1}
                                    width={Math.max(0, x2 - x1)}
                                    height={Math.max(0, y2 - y1)}
                                    fill="none"
                                    stroke={cfg.color}
                                    strokeWidth={2}
                                    strokeDasharray={box.outcome === "fn" ? "6 4" : undefined}
                                    vectorEffect="non-scaling-stroke"
                                />
                            </g>
                        );
                    })}
                </svg>
            </div>

            {boxes.length > 0 && (
                <div className="mt-3 overflow-x-auto max-h-56 overflow-y-auto">
                    <table className="w-full text-[11px] font-mono">
                        <thead className="sticky top-0 bg-black">
                            <tr className="text-[10px] uppercase text-gray-500 border-b border-white/10">
                                <th className="text-left py-1.5 font-medium">Outcome</th>
                                <th className="text-left py-1.5 font-medium">Diagnosis</th>
                                <th className="text-left py-1.5 font-medium">Predicted</th>
                                <th className="text-left py-1.5 font-medium">Actual</th>
                                <th className="text-right py-1.5 font-medium">Conf</th>
                                <th className="text-right py-1.5 font-medium">IoU</th>
                            </tr>
                        </thead>
                        <tbody>
                            {boxes.map((box, index) => {
                                const cfg = OUTCOME[box.outcome];
                                const diagnosis = ERROR_TYPES.find((t) => t.key === box.error_type);
                                return (
                                    <tr key={index} className="border-b border-white/5">
                                        <td className="py-1.5">
                                            <span className="inline-flex items-center gap-1.5 font-sans">
                                                <span
                                                    className="w-2 h-2 inline-block"
                                                    style={{ background: cfg?.color }}
                                                />
                                                {cfg?.label || box.outcome}
                                            </span>
                                        </td>
                                        <td className="py-1.5 font-sans text-gray-400" title={diagnosis?.hint}>
                                            {diagnosis?.label || box.error_type}
                                        </td>
                                        <td className="py-1.5 text-gray-300">{box.pred_class_name || "—"}</td>
                                        <td className="py-1.5 text-gray-300">{box.gt_class_name || "—"}</td>
                                        <td className="py-1.5 text-right text-gray-400">
                                            {box.confidence == null ? "—" : box.confidence.toFixed(3)}
                                        </td>
                                        <td className="py-1.5 text-right text-gray-400">
                                            {box.iou == null ? "—" : box.iou.toFixed(3)}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function FailureExplorer({ run, filter, onFilter }) {
    const { token } = useAuth();
    const [images, setImages] = useState([]);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(null);
    const pageSize = 24;

    useEffect(() => {
        setOffset(0);
    }, [filter, run.id]);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            setLoading(true);
            try {
                const res = await fetch(
                    API_ENDPOINTS.EVALUATION.ERRORS(run.id, {
                        errorType: filter,
                        limit: pageSize,
                        offset,
                    }),
                    { headers: { Authorization: `Bearer ${token}` } }
                );
                if (res.ok && !cancelled) {
                    const data = await res.json();
                    setImages(data.images || []);
                    setTotal(data.total || 0);
                }
            } catch (e) {
                console.error(e);
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [run.id, filter, offset, token]);

    const activeLabel = ERROR_TYPES.find((t) => t.key === filter)?.label;

    return (
        <div>
            <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
                <p className="text-[11px] text-gray-500">
                    {loading ? "Loading…" : `${num(total)} images`}
                    {activeLabel && <> showing <span className="text-violet-400">{activeLabel}</span></>}
                    {" · worst first"}
                </p>
                {filter && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onFilter(null)}
                        className="h-6 text-[10px] rounded-none"
                    >
                        Clear filter
                    </Button>
                )}
            </div>

            {!loading && !images.length && (
                <p className="text-xs text-gray-500 py-8 text-center">
                    Nothing to show — no image in this run matches.
                </p>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                {images.map((image) => (
                    <button
                        key={image.filename}
                        onClick={() => setOpen(image)}
                        className="group text-left border border-white/10 hover:border-violet-500/50 transition-colors"
                    >
                        <div className="relative aspect-square bg-white/[0.02] overflow-hidden">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={API_ENDPOINTS.EVALUATION.GET_IMAGE(run.id, image.filename, token)}
                                alt={image.filename}
                                loading="lazy"
                                className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                            />
                        </div>
                        <div className="p-1.5 flex items-center gap-2 text-[10px] font-mono">
                            <span className="text-red-400" title="False positives">{image.fp_count} FP</span>
                            <span className="text-amber-400" title="Missed">{image.fn_count} FN</span>
                            <span className="text-gray-600 ml-auto" title="Ground-truth boxes">
                                {image.gt_count} GT
                            </span>
                        </div>
                    </button>
                ))}
            </div>

            {total > pageSize && (
                <div className="flex items-center justify-center gap-2 mt-4">
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={offset === 0}
                        onClick={() => setOffset(Math.max(0, offset - pageSize))}
                        className="h-7 text-[10px] rounded-none"
                    >
                        Previous
                    </Button>
                    <span className="text-[10px] font-mono text-gray-500">
                        {offset + 1}–{Math.min(offset + pageSize, total)} of {num(total)}
                    </span>
                    <Button
                        variant="outline"
                        size="sm"
                        disabled={offset + pageSize >= total}
                        onClick={() => setOffset(offset + pageSize)}
                        className="h-7 text-[10px] rounded-none"
                    >
                        Next
                    </Button>
                </div>
            )}

            <Dialog open={!!open} onOpenChange={(value) => !value && setOpen(null)}>
                <DialogContent className="max-w-4xl bg-black border-white/20 rounded-none max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="text-sm font-mono break-all">{open?.filename}</DialogTitle>
                        <DialogDescription className="text-[11px]">
                            Solid boxes are predictions, dashed are ground truth nothing found.
                        </DialogDescription>
                    </DialogHeader>
                    {open && (
                        <BoxOverlay
                            runId={run.id}
                            filename={open.filename}
                            width={open.width}
                            height={open.height}
                        />
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}

// ── Compare ──────────────────────────────────────────────────────────────────

function CompareView({ runIds, onClose }) {
    const { token } = useAuth();
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const res = await fetch(API_ENDPOINTS.EVALUATION.COMPARE(runIds), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                const body = await res.json();
                if (cancelled) return;
                if (res.ok) setData(body);
                else setError(body.detail || "Could not compare these runs");
            } catch (e) {
                if (!cancelled) setError(String(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [runIds, token]);

    if (error) return <p className="text-xs text-red-400">{error}</p>;
    if (!data) return <p className="text-xs text-gray-500">Comparing…</p>;

    const classNames = [
        ...new Set(data.runs.flatMap((run) => run.per_class_metrics.map((c) => c.class_name))),
    ];

    return (
        <Card className="bg-black border-white/20 rounded-none">
            <CardHeader className="pb-3 flex-row items-start justify-between space-y-0">
                <div>
                    <CardTitle className="text-sm uppercase tracking-widest flex items-center gap-2">
                        <GitCompare className="w-4 h-4 text-violet-400" /> Comparison
                    </CardTitle>
                    <CardDescription className="text-[11px]">
                        Deltas are percentage points against the first run.
                    </CardDescription>
                </div>
                <Button variant="ghost" size="sm" onClick={onClose} className="h-7 text-[10px] rounded-none">
                    Close
                </Button>
            </CardHeader>
            <CardContent className="space-y-4">
                {!data.comparable && (
                    <div className="flex items-start gap-2 p-2 border border-amber-500/30 bg-amber-500/10 text-[11px] text-amber-300">
                        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                        <span>
                            These runs used different versions or splits, so the numbers answer
                            different questions. Ranking them would be misleading.
                        </span>
                    </div>
                )}

                <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                        <thead>
                            <tr className="text-[10px] uppercase text-gray-500 border-b border-white/10">
                                <th className="text-left py-2 font-medium">Run</th>
                                <th className="text-right py-2 font-medium">mAP@50</th>
                                <th className="text-right py-2 font-medium">Δ</th>
                                <th className="text-right py-2 font-medium">mAP@50-95</th>
                                <th className="text-right py-2 font-medium">Precision</th>
                                <th className="text-right py-2 font-medium">Recall</th>
                                <th className="text-right py-2 font-medium">Images</th>
                            </tr>
                        </thead>
                        <tbody className="font-mono">
                            {data.runs.map((run) => (
                                <tr
                                    key={run.run_id}
                                    className={cn(
                                        "border-b border-white/5",
                                        run.run_id === data.best_run_id && data.comparable && "bg-emerald-500/5"
                                    )}
                                >
                                    <td className="py-2 font-sans">
                                        <span className="text-gray-200">{run.job_id?.slice(0, 8)}</span>
                                        {run.is_baseline && (
                                            <Badge className="ml-2 text-[9px] bg-white/10 border-white/10">
                                                baseline
                                            </Badge>
                                        )}
                                        {run.run_id === data.best_run_id && data.comparable && (
                                            <Badge className="ml-2 text-[9px] bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                                                best
                                            </Badge>
                                        )}
                                    </td>
                                    <td className="text-right py-2">{pct(run.metrics.map50)}</td>
                                    <td
                                        className={cn(
                                            "text-right py-2",
                                            run.delta_map50 > 0 && "text-emerald-400",
                                            run.delta_map50 < 0 && "text-red-400"
                                        )}
                                    >
                                        {run.is_baseline ? "—" : signed(run.delta_map50)}
                                    </td>
                                    <td className="text-right py-2 text-gray-400">{pct(run.metrics.map50_95)}</td>
                                    <td className="text-right py-2 text-gray-400">{pct(run.metrics.precision)}</td>
                                    <td className="text-right py-2 text-gray-400">{pct(run.metrics.recall)}</td>
                                    <td className="text-right py-2 text-gray-500">{num(run.total_images)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {classNames.length > 0 && (
                    <div>
                        <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">
                            Per-class mAP@50
                        </p>
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-[10px] uppercase text-gray-500 border-b border-white/10">
                                        <th className="text-left py-2 font-medium">Class</th>
                                        {data.runs.map((run) => (
                                            <th key={run.run_id} className="text-right py-2 font-medium">
                                                {run.job_id?.slice(0, 8)}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="font-mono">
                                    {classNames.map((className) => (
                                        <tr key={className} className="border-b border-white/5">
                                            <td className="py-2 font-sans text-gray-200">{className}</td>
                                            {data.runs.map((run) => {
                                                const entry = run.per_class_metrics.find(
                                                    (c) => c.class_name === className
                                                );
                                                return (
                                                    <td key={run.run_id} className="text-right py-2">
                                                        {pct(entry?.mAP50)}
                                                        {entry?.delta_mAP50 != null && (
                                                            <span
                                                                className={cn(
                                                                    "ml-2 text-[10px]",
                                                                    entry.delta_mAP50 > 0 && "text-emerald-400",
                                                                    entry.delta_mAP50 < 0 && "text-red-400"
                                                                )}
                                                            >
                                                                {signed(entry.delta_mAP50)}
                                                            </span>
                                                        )}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

// ── Run detail ───────────────────────────────────────────────────────────────

function RunDetail({ runId }) {
    const { token } = useAuth();
    const [run, setRun] = useState(null);
    const [filter, setFilter] = useState(null);

    const fetchRun = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.GET(runId), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) setRun(await res.json());
        } catch (e) {
            console.error(e);
        }
    }, [runId, token]);

    useEffect(() => {
        setRun(null);
        setFilter(null);
    }, [runId]);

    // Poll only while the run is still being scored.
    usePolling(fetchRun, {
        intervalMs: 2000,
        idleIntervalMs: 0,
        active: !run || run.status === "pending" || run.status === "running",
        enabled: !!token,
    });

    if (!run) return <p className="text-xs text-gray-500 py-8 text-center">Loading run…</p>;

    if (run.status === "failed") {
        return (
            <div className="flex items-start gap-2 p-3 border border-red-500/30 bg-red-500/10 text-xs text-red-300">
                <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <div>
                    <p className="font-medium">This evaluation failed.</p>
                    <p className="font-mono text-[11px] mt-1 text-red-400/80">{run.error_message}</p>
                </div>
            </div>
        );
    }

    if (run.status !== "completed") {
        return (
            <div className="p-4 border border-white/10 bg-white/[0.02]">
                <div className="flex items-center gap-2 text-xs text-blue-400 mb-2">
                    <Loader className="w-3.5 h-3.5 animate-spin" />
                    Scoring {run.total_images || ""} images…
                </div>
                <Progress value={run.progress || 0} className="h-1" />
            </div>
        );
    }

    const metrics = run.metrics || {};

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                <MetricTile
                    label="mAP@50"
                    value={pct(metrics.map50)}
                    accent="text-violet-300"
                    hint="Threshold-free"
                />
                <MetricTile label="mAP@50-95" value={pct(metrics.map50_95)} accent="text-violet-300" />
                <MetricTile
                    label="Precision"
                    value={pct(metrics.precision)}
                    hint={`At conf ${run.conf_threshold}`}
                />
                <MetricTile
                    label="Recall"
                    value={pct(metrics.recall)}
                    hint={`At conf ${run.conf_threshold}`}
                />
                <MetricTile label="F1" value={pct(metrics.f1)} />
                <MetricTile
                    label="TP / FP / FN"
                    value={`${num(metrics.tp)} / ${num(metrics.fp)} / ${num(metrics.fn)}`}
                />
            </div>

            <p className="text-[11px] text-gray-500">
                {num(run.total_images)} images in the <span className="font-mono">{run.split}</span>{" "}
                split, {num(run.gt_count)} ground-truth boxes, {num(run.pred_count)} predictions kept
                at confidence <span className="font-mono">{run.conf_threshold}</span> and IoU{" "}
                <span className="font-mono">{run.iou_threshold}</span>. mAP is measured across the
                whole curve, so it does not move with the confidence setting; precision, recall and
                the error mix below do.
            </p>

            <div className="grid lg:grid-cols-2 gap-4">
                <Card className="bg-black border-white/20 rounded-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm uppercase tracking-widest">
                            Confidence sweep
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <SweepChart runId={run.id} confThreshold={run.conf_threshold} />
                    </CardContent>
                </Card>

                <Card className="bg-black border-white/20 rounded-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm uppercase tracking-widest">
                            What went wrong
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ErrorBreakdown
                            errorTypes={run.error_types}
                            activeFilter={filter}
                            onFilter={setFilter}
                        />
                    </CardContent>
                </Card>
            </div>

            <Card className="bg-black border-white/20 rounded-none">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm uppercase tracking-widest">
                        Per class, worst first
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <PerClassTable perClass={run.per_class_metrics} />
                </CardContent>
            </Card>

            <Card className="bg-black border-white/20 rounded-none">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm uppercase tracking-widest">Confusion matrix</CardTitle>
                </CardHeader>
                <CardContent>
                    <ConfusionMatrix confusion={run.confusion_matrix} classNames={run.class_names} />
                </CardContent>
            </Card>

            <Card className="bg-black border-white/20 rounded-none">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm uppercase tracking-widest">Failure explorer</CardTitle>
                    <CardDescription className="text-[11px]">
                        The images the model did worst on. Open one to see every box and its diagnosis.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <FailureExplorer run={run} filter={filter} onFilter={setFilter} />
                </CardContent>
            </Card>
        </div>
    );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function ProjectEvaluate({ dataset, onNavigate }) {
    const { token } = useAuth();
    const [jobs, setJobs] = useState([]);
    const [versions, setVersions] = useState([]);
    const [runs, setRuns] = useState([]);
    const [jobId, setJobId] = useState("");
    const [versionId, setVersionId] = useState("");
    const [split, setSplit] = useState("test");
    const [confThreshold, setConfThreshold] = useState(0.25);
    const [iouThreshold, setIouThreshold] = useState(0.5);
    const [starting, setStarting] = useState(false);
    const [selectedRun, setSelectedRun] = useState(null);
    const [compareIds, setCompareIds] = useState([]);
    const [comparing, setComparing] = useState(false);

    const fetchJobs = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) return;
            const data = await res.json();
            const completed = (data.jobs || []).filter(
                (job) =>
                    job.dataset_id === dataset.id &&
                    (job.status === "completed" || job.status === "success")
            );
            setJobs(completed);
            setJobId((current) => current || completed[0]?.job_id || "");
        } catch (e) {
            console.error(e);
        }
    }, [dataset.id, token]);

    const fetchVersions = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_LIST(dataset.id), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) return;
            const data = await res.json();
            const list = data.versions || [];
            setVersions(list);
            setVersionId((current) => current || list[0]?.id || "");
        } catch (e) {
            console.error(e);
        }
    }, [dataset.id, token]);

    const fetchRuns = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.RUNS(dataset.id), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setRuns(data.runs || []);
            }
        } catch (e) {
            console.error(e);
        }
    }, [dataset.id, token]);

    useEffect(() => {
        if (!token) return;
        fetchJobs();
        fetchVersions();
    }, [token, fetchJobs, fetchVersions]);

    const anyInFlight = runs.some((run) => run.status === "pending" || run.status === "running");
    usePolling(fetchRuns, {
        intervalMs: 3000,
        idleIntervalMs: 30000,
        active: anyInFlight,
        enabled: !!token,
    });

    const startRun = async () => {
        if (!jobId || !versionId) {
            toast.error("Pick a model and a version first");
            return;
        }
        setStarting(true);
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.RUN, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    version_id: versionId,
                    job_id: jobId,
                    split,
                    conf_threshold: confThreshold,
                    iou_threshold: iouThreshold,
                }),
            });
            const body = await res.json();
            if (res.ok) {
                toast.success(body.message || "Evaluation started");
                setSelectedRun(body.run_id);
                fetchRuns();
            } else {
                toast.error(body.detail || "Could not start the evaluation");
            }
        } catch (e) {
            toast.error(String(e));
        } finally {
            setStarting(false);
        }
    };

    const removeRun = async (runId) => {
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.DELETE(runId), {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                toast.success("Run deleted");
                if (selectedRun === runId) setSelectedRun(null);
                setCompareIds((ids) => ids.filter((id) => id !== runId));
                fetchRuns();
            } else {
                toast.error("Could not delete that run");
            }
        } catch (e) {
            toast.error(String(e));
        }
    };

    const toggleCompare = (runId) => {
        setCompareIds((ids) =>
            ids.includes(runId)
                ? ids.filter((id) => id !== runId)
                : ids.length >= 5
                  ? (toast.error("Compare at most five runs"), ids)
                  : [...ids, runId]
        );
    };

    if (!jobs.length) {
        return (
            <Card className="bg-black border-white/20 rounded-none">
                <CardContent className="py-12 text-center">
                    <Target className="w-8 h-8 text-gray-700 mx-auto mb-3" />
                    <p className="text-sm text-gray-300">Nothing to evaluate yet.</p>
                    <p className="text-xs text-gray-500 mt-1 max-w-md mx-auto">
                        Evaluation scores a finished model against a version&apos;s held-out split.
                        Train one first.
                    </p>
                    {onNavigate && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onNavigate("train")}
                            className="mt-4 rounded-none text-xs"
                        >
                            Go to Train
                        </Button>
                    )}
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-4 pb-8">
            <Card className="bg-black border-white/20 rounded-none">
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm uppercase tracking-widest flex items-center gap-2">
                        <Target className="w-4 h-4 text-violet-400" /> New evaluation
                    </CardTitle>
                    <CardDescription className="text-[11px]">
                        Scores a trained model against a frozen version&apos;s split, through the same
                        metric path for every backend — which is what makes two runs comparable.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid md:grid-cols-3 gap-3">
                        <div>
                            <Label className="text-[10px] uppercase text-gray-500">Model</Label>
                            <Select value={jobId} onValueChange={setJobId}>
                                <SelectTrigger className="rounded-none mt-1 h-9 text-xs">
                                    <SelectValue placeholder="Pick a trained model" />
                                </SelectTrigger>
                                <SelectContent>
                                    {jobs.map((job) => (
                                        <SelectItem key={job.job_id} value={job.job_id} className="text-xs">
                                            {job.model_name} · {job.job_id.slice(0, 8)}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label className="text-[10px] uppercase text-gray-500">Version</Label>
                            <Select value={versionId} onValueChange={setVersionId}>
                                <SelectTrigger className="rounded-none mt-1 h-9 text-xs">
                                    <SelectValue placeholder="Pick a version" />
                                </SelectTrigger>
                                <SelectContent>
                                    {versions.map((version) => (
                                        <SelectItem key={version.id} value={version.id} className="text-xs">
                                            v{version.version_number}
                                            {version.name ? ` · ${version.name}` : ""}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label className="text-[10px] uppercase text-gray-500">Split</Label>
                            <Select value={split} onValueChange={setSplit}>
                                <SelectTrigger className="rounded-none mt-1 h-9 text-xs">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="test" className="text-xs">
                                        test — held out from training
                                    </SelectItem>
                                    <SelectItem value="val" className="text-xs">
                                        val — training watched this
                                    </SelectItem>
                                    <SelectItem value="train" className="text-xs">
                                        train — a sanity check only
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-6">
                        <div>
                            <div className="flex items-center justify-between">
                                <Label className="text-[10px] uppercase text-gray-500">
                                    Confidence threshold
                                </Label>
                                <span className="text-xs font-mono text-violet-300">
                                    {confThreshold.toFixed(2)}
                                </span>
                            </div>
                            <Slider
                                value={[confThreshold]}
                                onValueChange={([value]) => setConfThreshold(value)}
                                min={0.01}
                                max={0.95}
                                step={0.01}
                                className="mt-2"
                            />
                            <p className="text-[10px] text-gray-600 mt-1">
                                The operating point for precision, recall and the error breakdown.
                                mAP is measured across the whole curve either way.
                            </p>
                        </div>
                        <div>
                            <div className="flex items-center justify-between">
                                <Label className="text-[10px] uppercase text-gray-500">
                                    IoU threshold
                                </Label>
                                <span className="text-xs font-mono text-violet-300">
                                    {iouThreshold.toFixed(2)}
                                </span>
                            </div>
                            <Slider
                                value={[iouThreshold]}
                                onValueChange={([value]) => setIouThreshold(value)}
                                min={0.05}
                                max={0.95}
                                step={0.05}
                                className="mt-2"
                            />
                            <p className="text-[10px] text-gray-600 mt-1">
                                How much overlap counts as finding the object.
                            </p>
                        </div>
                    </div>

                    <Button
                        onClick={startRun}
                        disabled={starting || !jobId || !versionId}
                        className="rounded-none bg-violet-600 hover:bg-violet-500 text-xs h-9"
                    >
                        {starting ? (
                            <>
                                <Loader className="w-3.5 h-3.5 mr-2 animate-spin" /> Starting…
                            </>
                        ) : (
                            <>
                                <Target className="w-3.5 h-3.5 mr-2" /> Run evaluation
                            </>
                        )}
                    </Button>
                </CardContent>
            </Card>

            {comparing && compareIds.length >= 2 && (
                <CompareView runIds={compareIds} onClose={() => setComparing(false)} />
            )}

            <Card className="bg-black border-white/20 rounded-none">
                <CardHeader className="pb-3 flex-row items-start justify-between space-y-0">
                    <div>
                        <CardTitle className="text-sm uppercase tracking-widest">Runs</CardTitle>
                        <CardDescription className="text-[11px]">
                            Tick two or more to compare them.
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={fetchRuns}
                            className="h-7 rounded-none text-[10px]"
                        >
                            <RefreshCw className="w-3 h-3 mr-1.5" /> Refresh
                        </Button>
                        <Button
                            size="sm"
                            disabled={compareIds.length < 2}
                            onClick={() => setComparing(true)}
                            className="h-7 rounded-none text-[10px] bg-violet-600 hover:bg-violet-500"
                        >
                            <GitCompare className="w-3 h-3 mr-1.5" />
                            Compare {compareIds.length > 0 ? `(${compareIds.length})` : ""}
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    {!runs.length ? (
                        <p className="text-xs text-gray-500 py-6 text-center">
                            No evaluation runs yet. Score a model above to get the first one.
                        </p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-[10px] uppercase text-gray-500 border-b border-white/10">
                                        <th className="w-8 py-2" />
                                        <th className="text-left py-2 font-medium">Model</th>
                                        <th className="text-left py-2 font-medium">Version</th>
                                        <th className="text-left py-2 font-medium">Split</th>
                                        <th className="text-right py-2 font-medium">mAP@50</th>
                                        <th className="text-right py-2 font-medium">Precision</th>
                                        <th className="text-right py-2 font-medium">Recall</th>
                                        <th className="text-left py-2 font-medium">Status</th>
                                        <th className="w-8 py-2" />
                                    </tr>
                                </thead>
                                <tbody>
                                    {runs.map((run) => (
                                        <tr
                                            key={run.id}
                                            onClick={() => setSelectedRun(run.id)}
                                            className={cn(
                                                "border-b border-white/5 cursor-pointer hover:bg-white/[0.03]",
                                                selectedRun === run.id && "bg-violet-500/10"
                                            )}
                                        >
                                            <td className="py-2" onClick={(event) => event.stopPropagation()}>
                                                <input
                                                    type="checkbox"
                                                    checked={compareIds.includes(run.id)}
                                                    disabled={run.status !== "completed"}
                                                    onChange={() => toggleCompare(run.id)}
                                                    aria-label={`Compare run ${run.id.slice(0, 8)}`}
                                                    className="accent-violet-500"
                                                />
                                            </td>
                                            <td className="py-2 font-mono text-gray-300">
                                                {run.job_id?.slice(0, 8) || "—"}
                                            </td>
                                            <td className="py-2 text-gray-400">
                                                v{run.version_number ?? "?"}
                                            </td>
                                            <td className="py-2 font-mono text-gray-500">{run.split}</td>
                                            <td className="py-2 text-right font-mono text-violet-300">
                                                {pct(run.metrics?.map50)}
                                            </td>
                                            <td className="py-2 text-right font-mono text-gray-400">
                                                {pct(run.metrics?.precision)}
                                            </td>
                                            <td className="py-2 text-right font-mono text-gray-400">
                                                {pct(run.metrics?.recall)}
                                            </td>
                                            <td className="py-2">
                                                <RunStatus status={run.status} progress={run.progress} />
                                            </td>
                                            <td className="py-2" onClick={(event) => event.stopPropagation()}>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    onClick={() => removeRun(run.id)}
                                                    aria-label="Delete run"
                                                    className="h-6 w-6 rounded-none text-gray-600 hover:text-red-400"
                                                >
                                                    <Trash2 className="w-3 h-3" />
                                                </Button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>

            {selectedRun && <RunDetail runId={selectedRun} />}
        </div>
    );
}
