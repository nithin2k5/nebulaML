"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { API_BASE_URL } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { toast } from "sonner";
import { Radio, Video, VideoOff } from "lucide-react";

// Frames are downscaled before sending: the model resizes to its own input
// size anyway, so shipping a full 1080p frame spends bandwidth and JPEG
// encoding time to no effect.
const SEND_WIDTH = 640;
const JPEG_QUALITY = 0.7;

// Capture cadence. The server drops whatever it cannot keep up with, so this
// is an upper bound rather than a promise — asking for more than the model can
// do just raises the drop count.
const CAPTURE_INTERVAL_MS = 100;

// Stable per-class colours, so a car is the same colour frame to frame.
const PALETTE = [
    "#a78bfa", "#34d399", "#fbbf24", "#f87171",
    "#60a5fa", "#f472b6", "#2dd4bf", "#fb923c",
];

const colourFor = (classId) => PALETTE[Math.abs(classId ?? 0) % PALETTE.length];

export default function LiveInference({ dataset, jobs = [] }) {
    const { token } = useAuth();

    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const captureRef = useRef(null);
    const socketRef = useRef(null);
    const streamRef = useRef(null);
    const timerRef = useRef(null);
    // The newest result, read by the draw loop. Kept in a ref rather than
    // state so a 10fps stream does not trigger 10 React renders a second.
    const latestRef = useRef({ detections: [], width: 0, height: 0 });
    const rafRef = useRef(null);

    const [running, setRunning] = useState(false);
    const [selectedJob, setSelectedJob] = useState(jobs[0]?.id || "");
    const [confidence, setConfidence] = useState(0.25);
    const [stats, setStats] = useState(null);
    const [status, setStatus] = useState("idle");

    useEffect(() => {
        if (!selectedJob && jobs.length) setSelectedJob(jobs[0].id);
    }, [jobs, selectedJob]);

    const stop = useCallback(() => {
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
        if (rafRef.current) {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = null;
        }
        if (socketRef.current) {
            const socket = socketRef.current;
            socketRef.current = null;
            try {
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({ type: "close" }));
                }
                socket.close();
            } catch {
                // Already closing; nothing to do.
            }
        }
        if (streamRef.current) {
            // Release the camera, or the browser keeps its indicator lit.
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        latestRef.current = { detections: [], width: 0, height: 0 };
        setRunning(false);
        setStatus("idle");
    }, []);

    // Stop on unmount, so navigating away always frees the camera.
    useEffect(() => stop, [stop]);

    const draw = useCallback(() => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas) return;

        const { videoWidth: vw, videoHeight: vh } = video;
        if (vw && vh && (canvas.width !== vw || canvas.height !== vh)) {
            canvas.width = vw;
            canvas.height = vh;
        }

        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const { detections, width } = latestRef.current;
        // Boxes come back in the coordinates of the downscaled frame that was
        // sent, so they scale up to the displayed video by that ratio.
        const scale = width ? canvas.width / width : 1;

        ctx.lineWidth = 2;
        ctx.font = "600 13px system-ui, sans-serif";
        ctx.textBaseline = "top";

        for (const d of detections) {
            const [x1, y1, x2, y2] = d.bbox || [];
            if (x2 === undefined) continue;

            const colour = colourFor(d.class_id);
            const left = x1 * scale;
            const top = y1 * scale;
            const boxWidth = (x2 - x1) * scale;
            const boxHeight = (y2 - y1) * scale;

            ctx.strokeStyle = colour;
            ctx.strokeRect(left, top, boxWidth, boxHeight);

            const label = `${d.class_name} ${Math.round(d.confidence * 100)}%`;
            const textWidth = ctx.measureText(label).width;
            ctx.fillStyle = colour;
            ctx.fillRect(left, Math.max(0, top - 18), textWidth + 8, 18);
            ctx.fillStyle = "#0a0a0a";
            ctx.fillText(label, left + 4, Math.max(0, top - 17));
        }

        rafRef.current = requestAnimationFrame(draw);
    }, []);

    const start = async () => {
        if (!selectedJob) {
            toast.error("Pick a trained run first");
            return;
        }

        setStatus("requesting camera");
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 1280 }, height: { ideal: 720 } },
                audio: false,
            });
        } catch {
            setStatus("idle");
            toast.error("Could not access the camera. Check the browser's permission.");
            return;
        }

        streamRef.current = stream;
        const video = videoRef.current;
        video.srcObject = stream;
        await video.play().catch(() => {});

        setStatus("connecting");
        // ws:// or wss:// mirroring however the API itself is reached, so this
        // works both in local development and behind TLS.
        const wsBase = API_BASE_URL.replace(/^http/, "ws");
        const params = new URLSearchParams({
            dataset_id: dataset.id,
            job_id: selectedJob,
            confidence: String(confidence),
            token: token || "",
        });
        const socket = new WebSocket(`${wsBase}/api/stream/live?${params}`);
        socketRef.current = socket;

        socket.onmessage = (event) => {
            let message;
            try {
                message = JSON.parse(event.data);
            } catch {
                return;
            }

            if (message.type === "ready") {
                setStatus(`live on ${message.device || "cpu"}`);
                return;
            }
            if (message.type === "detections") {
                latestRef.current = {
                    detections: message.detections || [],
                    width: message.width,
                    height: message.height,
                };
                setStats((prev) => ({ ...prev, inference_ms: message.inference_ms }));
                return;
            }
            if (message.type === "stats") {
                setStats((prev) => ({ ...prev, ...message }));
                return;
            }
            if (message.type === "error") {
                // Per-frame errors are expected noise on a live stream; a
                // toast per frame would be unusable.
                console.warn("live inference:", message.message);
            }
        };

        socket.onopen = () => {
            const capture = captureRef.current;
            timerRef.current = setInterval(() => {
                if (socket.readyState !== WebSocket.OPEN) return;
                const v = videoRef.current;
                if (!v || !v.videoWidth) return;

                // Don't queue frames the socket has not drained; without this
                // the buffer grows and latency climbs even though the server
                // drops frames at its end.
                if (socket.bufferedAmount > 0) return;

                const ratio = v.videoHeight / v.videoWidth;
                capture.width = SEND_WIDTH;
                capture.height = Math.round(SEND_WIDTH * ratio);
                capture
                    .getContext("2d")
                    .drawImage(v, 0, 0, capture.width, capture.height);

                socket.send(JSON.stringify({
                    type: "frame",
                    data: capture.toDataURL("image/jpeg", JPEG_QUALITY),
                }));
            }, CAPTURE_INTERVAL_MS);

            rafRef.current = requestAnimationFrame(draw);
            setRunning(true);
        };

        socket.onerror = () => {
            toast.error("Live inference connection failed");
            stop();
        };

        socket.onclose = (event) => {
            // 1008 is the server's "not authorised / no weights"; anything
            // else during a running session is an unexpected drop.
            if (event.code === 1008) {
                toast.error(event.reason || "Not authorised for live inference");
            }
            stop();
        };
    };

    if (jobs.length === 0) {
        return (
            <Card className="rounded-none">
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        <Radio className="w-4 h-4 text-violet-400" />
                        Live Camera
                    </CardTitle>
                    <CardDescription>
                        Train a model first, then point your camera at something and watch
                        it predict in real time.
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    return (
        <Card className="rounded-none">
            <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div>
                        <CardTitle className="text-base flex items-center gap-2">
                            <Radio className="w-4 h-4 text-violet-400" />
                            Live Camera
                        </CardTitle>
                        <CardDescription>
                            Streams frames to the model over a WebSocket. {status}
                        </CardDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <select
                            value={selectedJob}
                            onChange={(e) => setSelectedJob(e.target.value)}
                            disabled={running}
                            className="text-sm bg-background border border-input rounded-none px-2 py-1 disabled:opacity-60"
                        >
                            {jobs.map((job) => (
                                <option key={job.id} value={job.id}>
                                    {job.model_name || "run"} · {job.id.slice(0, 8)}
                                </option>
                            ))}
                        </select>
                        {running ? (
                            <Button variant="destructive" size="sm" onClick={stop}>
                                <VideoOff className="w-4 h-4 mr-2" />
                                Stop
                            </Button>
                        ) : (
                            <Button size="sm" onClick={start}>
                                <Video className="w-4 h-4 mr-2" />
                                Start camera
                            </Button>
                        )}
                    </div>
                </div>
            </CardHeader>

            <CardContent className="space-y-3">
                <div className="relative bg-black border border-white/10 aspect-video overflow-hidden">
                    <video
                        ref={videoRef}
                        playsInline
                        muted
                        className="absolute inset-0 w-full h-full object-contain"
                    />
                    <canvas
                        ref={canvasRef}
                        className="absolute inset-0 w-full h-full object-contain pointer-events-none"
                    />
                    {!running && (
                        <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
                            Camera is off
                        </div>
                    )}
                </div>

                {/* The frame the server actually sees; never displayed. */}
                <canvas ref={captureRef} className="hidden" />

                <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                    <label className="flex items-center gap-2">
                        Confidence
                        <input
                            type="range"
                            min="0.05"
                            max="0.95"
                            step="0.05"
                            value={confidence}
                            onChange={(e) => setConfidence(Number(e.target.value))}
                            disabled={running}
                            className="accent-primary"
                        />
                        <span className="text-foreground tabular-nums">
                            {confidence.toFixed(2)}
                        </span>
                    </label>

                    {stats?.inference_ms != null && (
                        <span>
                            {stats.inference_ms} ms/frame
                            {stats.inference_ms > 0 && (
                                <span className="text-foreground">
                                    {" "}
                                    (~{Math.round(1000 / stats.inference_ms)} fps)
                                </span>
                            )}
                        </span>
                    )}
                    {stats?.scored != null && (
                        <span>
                            {stats.scored} scored, {stats.dropped ?? 0} dropped
                        </span>
                    )}
                </div>

                {running && (stats?.dropped ?? 0) > (stats?.scored ?? 0) && (
                    <p className="text-xs text-yellow-500/80">
                        The model is slower than the camera, so most frames are being
                        skipped to keep the overlay current. Lowering the capture rate
                        would not make it faster — a smaller model or a GPU would.
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
