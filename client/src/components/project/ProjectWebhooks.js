"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Webhook, Trash2, Send, Copy, AlertTriangle, CheckCircle2 } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ui/confirm-dialog";

const EVENT_LABELS = {
    "training.completed": "Training finished",
    "training.failed": "Training failed",
    "drift.detected": "Drift detected",
    "autoretrain.triggered": "Auto-retrain started",
};

/**
 * Webhook subscriptions for a project.
 *
 * A training run lasts minutes to hours, drift is found by a poller and
 * auto-retrain fires from someone else's annotation save — so the status of
 * all three used to be visible only to whoever had the tab open. These are the
 * subscriptions that let something outside the app find out.
 */
export default function ProjectWebhooks({ dataset }) {
    const confirm = useConfirm();
    const { token } = useAuth();

    const [hooks, setHooks] = useState([]);
    const [events, setEvents] = useState(Object.keys(EVENT_LABELS));
    const [maxFailures, setMaxFailures] = useState(5);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    const [url, setUrl] = useState("");
    const [selected, setSelected] = useState(["training.completed", "training.failed"]);
    // Shown once, after creation: deliveries sign with the original key, so
    // the server cannot show it again later.
    const [newSecret, setNewSecret] = useState(null);

    const authHeaders = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
    };

    const fetchHooks = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.WEBHOOKS.LIST(dataset.id), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error("Request failed");
            const data = await res.json();
            setHooks(data.webhooks || []);
            if (data.events?.length) setEvents(data.events);
            if (data.max_consecutive_failures) setMaxFailures(data.max_consecutive_failures);
        } catch (e) {
            console.error(e);
            toast.error("Could not load webhooks");
        } finally {
            setLoading(false);
        }
    }, [dataset.id, token]);

    useEffect(() => {
        fetchHooks();
    }, [fetchHooks]);

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!url.trim() || selected.length === 0) return;

        setBusy(true);
        try {
            const res = await fetch(API_ENDPOINTS.WEBHOOKS.CREATE, {
                method: "POST",
                headers: authHeaders,
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    url: url.trim(),
                    events: selected,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                // The server explains a refused URL (non-public address, plain
                // http), which is the whole content of the error.
                toast.error(data.detail || "Could not add the webhook");
                return;
            }
            setNewSecret(data.secret);
            setUrl("");
            toast.success("Webhook added");
            fetchHooks();
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setBusy(false);
        }
    };

    const handleToggle = async (hook) => {
        try {
            const res = await fetch(API_ENDPOINTS.WEBHOOKS.UPDATE(hook.id), {
                method: "PATCH",
                headers: authHeaders,
                body: JSON.stringify({ enabled: !hook.enabled }),
            });
            if (!res.ok) throw new Error("Request failed");
            fetchHooks();
        } catch (e) {
            toast.error("Could not update the webhook: " + e.message);
        }
    };

    const handleTest = async (hook) => {
        setBusy(true);
        try {
            const res = await fetch(API_ENDPOINTS.WEBHOOKS.TEST(hook.id), {
                method: "POST",
                headers: authHeaders,
            });
            const data = await res.json().catch(() => ({}));
            if (data.success) {
                toast.success("Receiver accepted the test delivery");
            } else {
                const detail = data.webhook?.last_error || data.detail;
                toast.error(detail ? `Test failed: ${detail}` : "Test delivery failed");
            }
            fetchHooks();
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setBusy(false);
        }
    };

    const handleDelete = async (hook) => {
        if (
            !(await confirm({
                title: "Delete webhook",
                description:
                    "Its signing secret goes with it, so a replacement will need to be configured at the receiver.",
                confirmLabel: "Delete",
            }))
        )
            return;

        try {
            const res = await fetch(API_ENDPOINTS.WEBHOOKS.DELETE(hook.id), {
                method: "DELETE",
                headers: authHeaders,
            });
            if (!res.ok) throw new Error("Request failed");
            toast.success("Webhook deleted");
            fetchHooks();
        } catch (e) {
            toast.error("Could not delete: " + e.message);
        }
    };

    const toggleEvent = (event) => {
        setSelected((prev) =>
            prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
        );
    };

    if (loading) {
        return <div className="text-sm text-muted-foreground">Loading webhooks…</div>;
    }

    return (
        <div className="space-y-6">
            {newSecret && (
                <Card className="rounded-none border-primary/40 bg-primary/5">
                    <CardHeader>
                        <CardTitle className="text-base">Signing secret</CardTitle>
                        <CardDescription>
                            Copy this now — it is not shown again. Verify each delivery by
                            computing HMAC-SHA256 of the raw request body with this key and
                            comparing it to the <code>X-NebulaML-Signature</code> header.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-wrap items-center gap-2">
                        <code className="flex-1 min-w-0 break-all text-xs bg-background/60 border border-border p-2">
                            {newSecret}
                        </code>
                        <div className="flex gap-2">
                            <Button
                                size="sm"
                                variant="outline"
                                className="rounded-none"
                                onClick={() => {
                                    navigator.clipboard
                                        ?.writeText(newSecret)
                                        .then(() => toast.success("Secret copied"))
                                        .catch(() => toast.error("Could not copy"));
                                }}
                            >
                                <Copy className="w-4 h-4 mr-1" />
                                Copy
                            </Button>
                            <Button
                                size="sm"
                                className="rounded-none"
                                onClick={() => setNewSecret(null)}
                            >
                                Done
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            <Card className="rounded-none">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Webhook className="w-4 h-4 text-primary" />
                        Webhooks
                    </CardTitle>
                    <CardDescription>
                        A signed POST when something happens in this project. Deliveries retry
                        briefly; after {maxFailures} consecutive failures a hook switches itself
                        off rather than retrying every event forever.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {hooks.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                            No webhooks yet. Training finishing, drift and auto-retrain are
                            otherwise only visible with this tab open.
                        </p>
                    ) : (
                        <div className="border border-border divide-y divide-border">
                            {hooks.map((hook) => (
                                <div key={hook.id} className="p-3 space-y-2">
                                    <div className="flex items-start gap-3">
                                        <div className="min-w-0 flex-1">
                                            <div className="font-mono text-sm truncate" title={hook.url}>
                                                {hook.url}
                                            </div>
                                            <div className="flex flex-wrap gap-1 mt-1.5">
                                                {hook.events.map((e) => (
                                                    <Badge
                                                        key={e}
                                                        variant="outline"
                                                        className="rounded-none text-[10px]"
                                                    >
                                                        {EVENT_LABELS[e] || e}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            <Switch
                                                checked={hook.enabled}
                                                onCheckedChange={() => handleToggle(hook)}
                                                aria-label={
                                                    hook.enabled ? "Disable webhook" : "Enable webhook"
                                                }
                                            />
                                            <Button
                                                size="icon"
                                                variant="ghost"
                                                className="w-8 h-8 rounded-none"
                                                disabled={busy}
                                                onClick={() => handleTest(hook)}
                                                aria-label="Send a test delivery"
                                                title="Send a test delivery"
                                            >
                                                <Send className="w-4 h-4" />
                                            </Button>
                                            <Button
                                                size="icon"
                                                variant="ghost"
                                                className="w-8 h-8 rounded-none text-red-400 hover:text-red-300"
                                                onClick={() => handleDelete(hook)}
                                                aria-label="Delete webhook"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    </div>

                                    {/* The last attempt is the only way to tell a working
                                        receiver from one that has been silently rejecting
                                        every delivery. */}
                                    {hook.last_attempt_at && (
                                        <div className="text-xs flex items-start gap-1.5">
                                            {hook.last_error ? (
                                                <>
                                                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                                                    <span className="text-amber-400">
                                                        Last attempt failed: {hook.last_error}
                                                        {hook.consecutive_failures > 1 &&
                                                            ` (${hook.consecutive_failures} in a row)`}
                                                        {!hook.enabled &&
                                                            " — disabled automatically; re-enable to retry."}
                                                    </span>
                                                </>
                                            ) : (
                                                <>
                                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                                                    <span className="text-muted-foreground">
                                                        Last delivery accepted
                                                        {hook.last_status ? ` (HTTP ${hook.last_status})` : ""}
                                                        {" · "}
                                                        {new Date(hook.last_attempt_at).toLocaleString()}
                                                    </span>
                                                </>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <form onSubmit={handleCreate} className="space-y-4 pt-2 border-t border-border">
                        <div className="space-y-2">
                            <Label htmlFor="webhook-url">Endpoint URL</Label>
                            <Input
                                id="webhook-url"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder="https://example.com/hooks/nebulaml"
                                className="rounded-none font-mono text-sm"
                            />
                            <p className="text-xs text-muted-foreground">
                                Must be https and resolve to a public address.
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                                Events
                            </Label>
                            <div className="grid sm:grid-cols-2 gap-2">
                                {events.map((event) => (
                                    <label
                                        key={event}
                                        className="flex items-center gap-2 px-3 py-2 border border-border hover:border-primary/50 text-sm cursor-pointer"
                                    >
                                        <input
                                            type="checkbox"
                                            className="accent-primary w-4 h-4 shrink-0"
                                            checked={selected.includes(event)}
                                            onChange={() => toggleEvent(event)}
                                        />
                                        <span className="truncate">{EVENT_LABELS[event] || event}</span>
                                    </label>
                                ))}
                            </div>
                        </div>

                        <Button
                            type="submit"
                            disabled={busy || !url.trim() || selected.length === 0}
                            className="rounded-none"
                        >
                            Add webhook
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
