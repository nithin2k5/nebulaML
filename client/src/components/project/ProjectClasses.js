"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tags, Plus, Pencil, Trash2, Merge, Check, X, AlertTriangle } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ui/confirm-dialog";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * Class list editing for a project.
 *
 * Every annotation stores its class as an index into this list, so the server
 * rewrites all of them on a delete or merge. That is why each destructive
 * action here states the box count it is about to move or discard: the
 * instance counts are the only thing that makes "is this class a mistake?"
 * answerable, and they are what the confirmation is really asking about.
 */
export default function ProjectClasses({ dataset, onRefresh }) {
    const confirm = useConfirm();
    const { token } = useAuth();

    const [classes, setClasses] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    const [newClass, setNewClass] = useState("");
    const [editingIndex, setEditingIndex] = useState(null);
    const [editingName, setEditingName] = useState("");

    const [mergeSources, setMergeSources] = useState([]);
    const [mergeTarget, setMergeTarget] = useState("");

    const [projectName, setProjectName] = useState(dataset.name || "");
    const [projectDescription, setProjectDescription] = useState(dataset.description || "");

    const authHeaders = {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
    };

    const fetchClasses = useCallback(async () => {
        try {
            const res = await fetch(API_ENDPOINTS.DATASETS.CLASSES(dataset.id), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error("Request failed");
            const data = await res.json();
            setClasses(data.classes || []);
        } catch (e) {
            console.error(e);
            toast.error("Could not load the class list");
        } finally {
            setLoading(false);
        }
    }, [dataset.id, token]);

    useEffect(() => {
        fetchClasses();
    }, [fetchClasses]);

    useEffect(() => {
        setProjectName(dataset.name || "");
        setProjectDescription(dataset.description || "");
    }, [dataset.name, dataset.description]);

    /**
     * Run one class mutation and report what the server actually moved.
     *
     * The response carries the rewrite counts, so the toast can say "412 boxes
     * retargeted" rather than a bare "saved" — with an index rewrite that is
     * the only confirmation worth reading.
     */
    const mutate = async (url, method, body, describe) => {
        setBusy(true);
        try {
            const res = await fetch(url, {
                method,
                headers: authHeaders,
                ...(body ? { body: JSON.stringify(body) } : {}),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                toast.error(data.detail || "The change was rejected");
                return false;
            }
            toast.success(describe(data));
            await fetchClasses();
            // The class list lives on the dataset the rest of the page reads.
            onRefresh?.();
            return true;
        } catch (e) {
            toast.error("Error: " + e.message);
            return false;
        } finally {
            setBusy(false);
        }
    };

    const summarise = (data, lead) => {
        const parts = [lead];
        if (data.annotations_rewritten) {
            parts.push(`${plural(data.annotations_rewritten, "image")} rewritten`);
        }
        if (data.boxes_dropped) parts.push(`${plural(data.boxes_dropped, "box")} removed`);
        if (data.images_unlabelled) {
            parts.push(`${plural(data.images_unlabelled, "image")} now unlabelled`);
        }
        return parts.join(" · ");
    };

    const handleAdd = async (e) => {
        e.preventDefault();
        const name = newClass.trim();
        if (!name) return;
        const ok = await mutate(
            API_ENDPOINTS.DATASETS.CLASSES(dataset.id),
            "POST",
            { name },
            () => `Added "${name}"`
        );
        if (ok) setNewClass("");
    };

    const handleRename = async (index) => {
        const name = editingName.trim();
        if (!name || name === classes.find((c) => c.index === index)?.name) {
            setEditingIndex(null);
            return;
        }
        const ok = await mutate(
            API_ENDPOINTS.DATASETS.CLASS(dataset.id, index),
            "PATCH",
            { name },
            (data) => summarise(data, `Renamed to "${name}"`)
        );
        if (ok) setEditingIndex(null);
    };

    const handleDelete = async (cls) => {
        const confirmed = await confirm({
            title: `Delete "${cls.name}"?`,
            description: cls.instances
                ? `This also deletes ${plural(cls.instances, "box")} using it. Frozen versions keep their copy, so finished training runs are unaffected. This cannot be undone.`
                : "Nothing is annotated with this class, so no boxes are affected.",
            confirmLabel: "Delete class",
        });
        if (!confirmed) return;
        await mutate(
            API_ENDPOINTS.DATASETS.CLASS(dataset.id, cls.index),
            "DELETE",
            null,
            (data) => summarise(data, `Deleted "${cls.name}"`)
        );
    };

    const handleMerge = async () => {
        const target = Number(mergeTarget);
        const sources = mergeSources.filter((i) => i !== target);
        if (!sources.length || Number.isNaN(target)) return;

        const targetName = classes.find((c) => c.index === target)?.name;
        const moving = classes
            .filter((c) => sources.includes(c.index))
            .reduce((sum, c) => sum + c.instances, 0);

        const confirmed = await confirm({
            title: `Merge into "${targetName}"?`,
            description: `${plural(moving, "box")} move to "${targetName}" and ${plural(sources.length, "class")} disappear. No boxes are deleted, but the merge cannot be undone.`,
            confirmLabel: "Merge",
            // Nothing is discarded by a merge, so this is not a destructive prompt.
            variant: "default",
        });
        if (!confirmed) return;

        const ok = await mutate(
            API_ENDPOINTS.DATASETS.CLASSES_MERGE(dataset.id),
            "POST",
            { sources, target },
            (data) => summarise(data, `Merged into "${targetName}"`)
        );
        if (ok) {
            setMergeSources([]);
            setMergeTarget("");
        }
    };

    const handleSaveProject = async (e) => {
        e.preventDefault();
        const name = projectName.trim();
        if (!name) return;
        await mutate(
            API_ENDPOINTS.DATASETS.UPDATE(dataset.id),
            "PATCH",
            { name, description: projectDescription },
            () => "Project details saved"
        );
    };

    const toggleSource = (index) => {
        setMergeSources((prev) =>
            prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
        );
    };

    const totalInstances = classes.reduce((sum, c) => sum + c.instances, 0);
    const unused = classes.filter((c) => c.instances === 0);
    const mergeTargetChosen = mergeTarget !== "" && !Number.isNaN(Number(mergeTarget));
    const effectiveSources = mergeSources.filter((i) => i !== Number(mergeTarget));

    if (loading) {
        return <div className="text-sm text-muted-foreground">Loading classes…</div>;
    }

    return (
        <div className="space-y-6">
            <Card className="rounded-none">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Tags className="w-4 h-4 text-primary" />
                        Classes
                    </CardTitle>
                    <CardDescription>
                        {plural(classes.length, "class")} across {plural(totalInstances, "box")}.
                        Renaming is safe at any time; a frozen version keeps the names it was
                        created with, so an old training run is never rewritten.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {unused.length > 0 && (
                        <div className="flex items-start gap-2 p-3 border border-amber-500/30 bg-amber-500/10 text-amber-400 text-sm">
                            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                            <span>
                                {plural(unused.length, "class")} with no boxes at all
                                ({unused.map((c) => c.name).join(", ")}). An unused class still
                                becomes an output the model has to learn to never predict.
                            </span>
                        </div>
                    )}

                    <div className="border border-border divide-y divide-border">
                        {classes.map((cls) => (
                            <div
                                key={cls.index}
                                className="flex items-center gap-3 px-3 py-2 text-sm"
                            >
                                <Badge variant="outline" className="rounded-none font-mono shrink-0">
                                    {cls.index}
                                </Badge>

                                {editingIndex === cls.index ? (
                                    <>
                                        <Input
                                            value={editingName}
                                            onChange={(e) => setEditingName(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter") handleRename(cls.index);
                                                if (e.key === "Escape") setEditingIndex(null);
                                            }}
                                            autoFocus
                                            className="h-8 rounded-none flex-1"
                                            aria-label={`New name for ${cls.name}`}
                                        />
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="w-8 h-8 rounded-none"
                                            disabled={busy}
                                            onClick={() => handleRename(cls.index)}
                                            aria-label="Save name"
                                        >
                                            <Check className="w-4 h-4" />
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="w-8 h-8 rounded-none"
                                            onClick={() => setEditingIndex(null)}
                                            aria-label="Cancel rename"
                                        >
                                            <X className="w-4 h-4" />
                                        </Button>
                                    </>
                                ) : (
                                    <>
                                        <span className="flex-1 font-medium truncate">{cls.name}</span>
                                        <span className="text-muted-foreground tabular-nums shrink-0">
                                            {cls.instances === 0
                                                ? "unused"
                                                : plural(cls.instances, "box")}
                                        </span>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="w-8 h-8 rounded-none"
                                            onClick={() => {
                                                setEditingIndex(cls.index);
                                                setEditingName(cls.name);
                                            }}
                                            aria-label={`Rename ${cls.name}`}
                                        >
                                            <Pencil className="w-4 h-4" />
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            className="w-8 h-8 rounded-none text-red-400 hover:text-red-300"
                                            disabled={busy || classes.length === 1}
                                            onClick={() => handleDelete(cls)}
                                            aria-label={`Delete ${cls.name}`}
                                            title={
                                                classes.length === 1
                                                    ? "A dataset must keep at least one class"
                                                    : undefined
                                            }
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </>
                                )}
                            </div>
                        ))}
                    </div>

                    <form onSubmit={handleAdd} className="flex gap-2">
                        <Input
                            value={newClass}
                            onChange={(e) => setNewClass(e.target.value)}
                            placeholder="Add a class…"
                            className="rounded-none"
                            aria-label="New class name"
                        />
                        <Button
                            type="submit"
                            disabled={busy || !newClass.trim()}
                            className="rounded-none shrink-0"
                        >
                            <Plus className="w-4 h-4 mr-1" />
                            Add
                        </Button>
                    </form>
                </CardContent>
            </Card>

            {classes.length > 1 && (
                <Card className="rounded-none">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Merge className="w-4 h-4 text-primary" />
                            Merge classes
                        </CardTitle>
                        <CardDescription>
                            For when two labels turned out to mean the same thing. Every box of the
                            classes you pick is retargeted — nothing is deleted.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                                Classes to fold in
                            </Label>
                            <div className="grid sm:grid-cols-2 gap-2">
                                {classes.map((cls) => (
                                    <label
                                        key={cls.index}
                                        className={`flex items-center gap-2 px-3 py-2 border text-sm cursor-pointer ${
                                            cls.index === Number(mergeTarget)
                                                ? "border-border/40 text-muted-foreground cursor-not-allowed"
                                                : "border-border hover:border-primary/50"
                                        }`}
                                    >
                                        <input
                                            type="checkbox"
                                            className="accent-primary w-4 h-4 shrink-0"
                                            checked={mergeSources.includes(cls.index)}
                                            disabled={cls.index === Number(mergeTarget)}
                                            onChange={() => toggleSource(cls.index)}
                                        />
                                        <span className="truncate flex-1">{cls.name}</span>
                                        <span className="text-xs text-muted-foreground tabular-nums">
                                            {cls.instances}
                                        </span>
                                    </label>
                                ))}
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                                Keep as
                            </Label>
                            <Select value={mergeTarget} onValueChange={setMergeTarget}>
                                <SelectTrigger className="rounded-none">
                                    <SelectValue placeholder="Pick the surviving class" />
                                </SelectTrigger>
                                <SelectContent>
                                    {classes.map((cls) => (
                                        <SelectItem key={cls.index} value={String(cls.index)}>
                                            {cls.name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <Button
                            onClick={handleMerge}
                            disabled={busy || !mergeTargetChosen || effectiveSources.length === 0}
                            className="rounded-none"
                        >
                            <Merge className="w-4 h-4 mr-1" />
                            {effectiveSources.length > 0 && mergeTargetChosen
                                ? `Merge ${plural(effectiveSources.length, "class")}`
                                : "Merge"}
                        </Button>
                    </CardContent>
                </Card>
            )}

            <Card className="rounded-none">
                <CardHeader>
                    <CardTitle>Project details</CardTitle>
                    <CardDescription>
                        The name is used when naming exports and downloads.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSaveProject} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="project-name">Name</Label>
                            <Input
                                id="project-name"
                                value={projectName}
                                onChange={(e) => setProjectName(e.target.value)}
                                className="rounded-none"
                                maxLength={100}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="project-description">Description</Label>
                            <Input
                                id="project-description"
                                value={projectDescription}
                                onChange={(e) => setProjectDescription(e.target.value)}
                                className="rounded-none"
                                placeholder="What this project is for"
                            />
                        </div>
                        <Button
                            type="submit"
                            disabled={
                                busy ||
                                !projectName.trim() ||
                                (projectName === (dataset.name || "") &&
                                    projectDescription === (dataset.description || ""))
                            }
                            className="rounded-none"
                        >
                            Save
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
