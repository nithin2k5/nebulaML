"use client";

import { useCallback, useEffect, useState } from "react";
import {
    AlertTriangle,
    Check,
    Copy,
    Download,
    ExternalLink,
    Eye,
    Globe,
    Loader,
    Share2,
    Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { cn } from "@/lib/utils";

// Offered to the publisher; the server keeps the authoritative allowlist.
const FORMATS = [
    { id: "yolo", label: "YOLO", hint: "The snapshot exactly as training consumed it." },
    { id: "coco", label: "COCO", hint: "A single JSON of images, boxes and categories." },
];

const LICENSES = [
    "CC BY 4.0",
    "CC BY-SA 4.0",
    "CC BY-NC 4.0",
    "CC0 1.0",
    "MIT",
    "Apache-2.0",
    "All rights reserved",
];

const num = (value) => (value == null ? "—" : Number(value).toLocaleString());

export default function ProjectPublish({ dataset, onNavigate }) {
    const { token } = useAuth();
    const confirm = useConfirm();

    const [versions, setVersions] = useState([]);
    const [publications, setPublications] = useState([]);
    const [loading, setLoading] = useState(true);
    const [publishing, setPublishing] = useState(false);
    const [copied, setCopied] = useState(null);

    const [versionId, setVersionId] = useState("");
    const [title, setTitle] = useState(dataset?.name || "");
    const [description, setDescription] = useState("");
    const [license, setLicense] = useState(LICENSES[0]);
    const [allowDownloads, setAllowDownloads] = useState(true);
    const [formats, setFormats] = useState(FORMATS.map((f) => f.id));

    const headers = { Authorization: `Bearer ${token}` };

    const fetchVersions = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_LIST(dataset.id), { headers });
            if (!res.ok) return;
            const data = await res.json();
            const list = data.versions || [];
            setVersions(list);
            setVersionId((current) => current || list[0]?.id || "");
        } catch (e) {
            console.error(e);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dataset.id, token]);

    const fetchPublications = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.PUBLISH.LIST(dataset.id), { headers });
            if (res.ok) {
                const data = await res.json();
                setPublications(data.publications || []);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dataset.id, token]);

    useEffect(() => {
        if (!token) return;
        fetchVersions();
        fetchPublications();
    }, [token, fetchVersions, fetchPublications]);

    const publicUrl = (slug) =>
        typeof window === "undefined" ? `/d/${slug}` : `${window.location.origin}/d/${slug}`;

    const copyLink = async (slug) => {
        try {
            await navigator.clipboard.writeText(publicUrl(slug));
            setCopied(slug);
            setTimeout(() => setCopied(null), 2000);
        } catch {
            toast.error("Could not copy — the link is in the row below.");
        }
    };

    const publish = async () => {
        if (!versionId) {
            toast.error("Pick a version to publish");
            return;
        }
        if (!title.trim()) {
            toast.error("Give the published dataset a title");
            return;
        }
        // Publishing puts project data on the open internet under a link that
        // needs no account, so it is confirmed rather than one click away.
        const ok = await confirm({
            title: "Publish this dataset publicly?",
            description:
                "Anyone with the link will be able to view the dataset card and, if " +
                "downloads are on, download every image and label in this version — " +
                "no account needed. You can revoke the link at any time.",
            confirmLabel: "Publish",
            cancelLabel: "Cancel",
            variant: "default",
        });
        if (!ok) return;

        setPublishing(true);
        try {
            const res = await fetch(API_ENDPOINTS.PUBLISH.CREATE, {
                method: "POST",
                headers: { ...headers, "Content-Type": "application/json" },
                body: JSON.stringify({
                    dataset_id: dataset.id,
                    version_id: versionId,
                    title: title.trim(),
                    description: description.trim(),
                    license,
                    allow_downloads: allowDownloads,
                    formats,
                }),
            });
            const body = await res.json();
            if (res.ok) {
                toast.success("Published");
                setDescription("");
                fetchPublications();
                copyLink(body.slug);
            } else {
                toast.error(body.detail || "Could not publish");
            }
        } catch (e) {
            toast.error(String(e));
        } finally {
            setPublishing(false);
        }
    };

    const revoke = async (publication) => {
        const ok = await confirm({
            title: "Revoke this public link?",
            description:
                `"${publication.title}" will stop resolving for everyone immediately, and ` +
                "the prepared downloads are deleted. The link can never be reissued, so " +
                "anyone who saved it gets nothing. Copies already downloaded stay downloaded.",
            confirmLabel: "Revoke",
            cancelLabel: "Keep it live",
            variant: "destructive",
        });
        if (!ok) return;

        try {
            const res = await fetch(API_ENDPOINTS.PUBLISH.REVOKE(publication.id), {
                method: "DELETE",
                headers,
            });
            if (res.ok) {
                toast.success("Link revoked");
                fetchPublications();
            } else {
                toast.error("Could not revoke that link");
            }
        } catch (e) {
            toast.error(String(e));
        }
    };

    const toggleDownloads = async (publication) => {
        try {
            const res = await fetch(API_ENDPOINTS.PUBLISH.UPDATE(publication.id), {
                method: "PATCH",
                headers: { ...headers, "Content-Type": "application/json" },
                body: JSON.stringify({ allow_downloads: !publication.allow_downloads }),
            });
            if (res.ok) {
                fetchPublications();
            } else {
                toast.error("Could not change that setting");
            }
        } catch (e) {
            toast.error(String(e));
        }
    };

    const toggleFormat = (id) => {
        setFormats((current) =>
            current.includes(id)
                ? current.filter((f) => f !== id)
                : [...current, id]
        );
    };

    if (!versions.length && !loading) {
        return (
            <Card className="bg-black border-white/20 rounded-none">
                <CardContent className="py-12 text-center">
                    <Share2 className="w-8 h-8 text-gray-700 mx-auto mb-3" />
                    <p className="text-sm text-gray-300">Nothing to publish yet.</p>
                    <p className="text-xs text-gray-500 mt-1 max-w-md mx-auto">
                        Publishing shares a frozen version, not the live dataset — a public
                        link to a dataset that keeps changing would stop being true. Freeze
                        one first.
                    </p>
                    {onNavigate && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onNavigate("generate")}
                            className="mt-4 rounded-none text-xs"
                        >
                            Go to Version
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
                        <Globe className="w-4 h-4 text-violet-400" /> Publish a version
                    </CardTitle>
                    <CardDescription className="text-[11px]">
                        Creates a public link that needs no account. The link points at a
                        frozen snapshot, so what someone downloads today is what they
                        download next year.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid md:grid-cols-2 gap-3">
                        <div>
                            <Label className="text-[10px] uppercase text-gray-500">Version</Label>
                            <Select value={versionId} onValueChange={setVersionId}>
                                <SelectTrigger className="rounded-none mt-1 h-9 text-xs">
                                    <SelectValue placeholder="Pick a frozen version" />
                                </SelectTrigger>
                                <SelectContent>
                                    {versions.map((version) => (
                                        <SelectItem key={version.id} value={version.id} className="text-xs">
                                            v{version.version_number}
                                            {version.name ? ` · ${version.name}` : ""}
                                            {version.total_images ? ` · ${version.total_images} images` : ""}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label className="text-[10px] uppercase text-gray-500">Licence</Label>
                            <Select value={license} onValueChange={setLicense}>
                                <SelectTrigger className="rounded-none mt-1 h-9 text-xs">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {LICENSES.map((name) => (
                                        <SelectItem key={name} value={name} className="text-xs">
                                            {name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div>
                        <Label className="text-[10px] uppercase text-gray-500">
                            Public title
                        </Label>
                        <Input
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            maxLength={200}
                            placeholder="What this dataset is called publicly"
                            className="rounded-none mt-1 h-9 text-xs"
                        />
                        <p className="text-[10px] text-gray-600 mt-1">
                            The only name that goes out. The project&apos;s own name stays private.
                        </p>
                    </div>

                    <div>
                        <Label className="text-[10px] uppercase text-gray-500">Description</Label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            maxLength={4000}
                            rows={3}
                            placeholder="What is in it, how it was collected, how it should be used."
                            className="w-full mt-1 bg-background border border-input rounded-none px-3 py-2 text-xs"
                        />
                    </div>

                    <div className="flex flex-wrap items-center gap-6">
                        <div className="flex items-center gap-2">
                            <Switch
                                id="allow-downloads"
                                checked={allowDownloads}
                                onCheckedChange={setAllowDownloads}
                            />
                            <Label htmlFor="allow-downloads" className="text-xs">
                                Allow downloads
                            </Label>
                        </div>
                        <div className="flex items-center gap-3">
                            {FORMATS.map((format) => (
                                <button
                                    key={format.id}
                                    type="button"
                                    disabled={!allowDownloads}
                                    onClick={() => toggleFormat(format.id)}
                                    title={format.hint}
                                    className={cn(
                                        "px-2 py-1 border text-[10px] uppercase tracking-wider transition-colors",
                                        !allowDownloads && "opacity-40 cursor-not-allowed",
                                        formats.includes(format.id)
                                            ? "border-violet-500/60 text-violet-300 bg-violet-500/10"
                                            : "border-white/15 text-gray-500"
                                    )}
                                >
                                    {format.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {!allowDownloads && (
                        <p className="text-[11px] text-amber-400/90 flex items-start gap-2">
                            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                            With downloads off the card still shows the class list, the counts
                            and a few preview images. Turn the whole link off by revoking it.
                        </p>
                    )}

                    <Button
                        onClick={publish}
                        disabled={publishing || !versionId || !title.trim()}
                        className="rounded-none bg-violet-600 hover:bg-violet-500 text-xs h-9"
                    >
                        {publishing ? (
                            <>
                                <Loader className="w-3.5 h-3.5 mr-2 animate-spin" /> Publishing…
                            </>
                        ) : (
                            <>
                                <Globe className="w-3.5 h-3.5 mr-2" /> Publish
                            </>
                        )}
                    </Button>
                </CardContent>
            </Card>

            <Card className="bg-black border-white/20 rounded-none">
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm uppercase tracking-widest">
                        Public links
                    </CardTitle>
                    <CardDescription className="text-[11px]">
                        A revoked link never resolves again and cannot be reissued.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <p className="text-xs text-gray-500 py-6 text-center">Loading…</p>
                    ) : !publications.length ? (
                        <p className="text-xs text-gray-500 py-6 text-center">
                            Nothing published yet. This dataset is private.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {publications.map((publication) => {
                                const live = publication.status === "live";
                                return (
                                    <div
                                        key={publication.id}
                                        className={cn(
                                            "border p-3",
                                            live ? "border-white/15" : "border-white/5 opacity-60"
                                        )}
                                    >
                                        <div className="flex items-start justify-between gap-3 flex-wrap">
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="text-sm text-gray-100">
                                                        {publication.title}
                                                    </span>
                                                    <Badge
                                                        className={cn(
                                                            "text-[9px] border",
                                                            live
                                                                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                                                : "bg-white/10 text-gray-400 border-white/10"
                                                        )}
                                                    >
                                                        {live ? "Live" : "Revoked"}
                                                    </Badge>
                                                    <span className="text-[10px] font-mono text-gray-600">
                                                        v{publication.version_number ?? "?"} · {publication.license}
                                                    </span>
                                                </div>
                                                {live && (
                                                    <code className="block text-[10px] font-mono text-violet-300/80 mt-1 break-all">
                                                        {publicUrl(publication.slug)}
                                                    </code>
                                                )}
                                                <div className="flex items-center gap-4 mt-2 text-[10px] font-mono text-gray-500">
                                                    <span className="flex items-center gap-1">
                                                        <Eye className="w-3 h-3" /> {num(publication.view_count)}
                                                    </span>
                                                    <span className="flex items-center gap-1">
                                                        <Download className="w-3 h-3" />{" "}
                                                        {num(publication.download_count)}
                                                    </span>
                                                    <span>
                                                        {publication.allow_downloads
                                                            ? (publication.formats || []).join(", ") || "no formats"
                                                            : "downloads off"}
                                                    </span>
                                                </div>
                                            </div>

                                            {live && (
                                                <div className="flex items-center gap-1 shrink-0">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => copyLink(publication.slug)}
                                                        className="h-7 rounded-none text-[10px]"
                                                    >
                                                        {copied === publication.slug ? (
                                                            <>
                                                                <Check className="w-3 h-3 mr-1 text-emerald-400" /> Copied
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Copy className="w-3 h-3 mr-1" /> Copy
                                                            </>
                                                        )}
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        asChild
                                                        className="h-7 rounded-none text-[10px]"
                                                    >
                                                        <a
                                                            href={`/d/${publication.slug}`}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                        >
                                                            <ExternalLink className="w-3 h-3 mr-1" /> Open
                                                        </a>
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => toggleDownloads(publication)}
                                                        className="h-7 rounded-none text-[10px]"
                                                    >
                                                        {publication.allow_downloads
                                                            ? "Downloads off"
                                                            : "Downloads on"}
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={() => revoke(publication)}
                                                        aria-label="Revoke link"
                                                        className="h-7 w-7 rounded-none text-gray-600 hover:text-red-400"
                                                    >
                                                        <Trash2 className="w-3 h-3" />
                                                    </Button>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
