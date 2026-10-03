"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { API_ENDPOINTS, API_BASE_URL } from "@/lib/config";
import { usePolling } from "@/lib/usePolling";
import {
    Trash2,
    Image as ImageIcon,
    CheckSquare,
    Download,
    Search,
    Sparkles,
    X,
    Copy,
} from "lucide-react";
import JSZip from "jszip";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ui/confirm-dialog";

export default function ProjectImages({ dataset, onRefresh }) {
    const confirm = useConfirm();
    const { token } = useAuth();
    const [deletingId, setDeletingId] = useState(null);
    const [isDeletingBulk, setIsDeletingBulk] = useState(false);
    const [selectedImages, setSelectedImages] = useState(new Set());
    const [filterStatus, setFilterStatus] = useState("all"); // 'all', 'annotated', 'unannotated'
    const [filterSplit, setFilterSplit] = useState("all"); // 'all', 'train', 'val', 'test'
    const [isExporting, setIsExporting] = useState(false);

    // Semantic search. `searchHits` is null until a search has run, which is
    // what distinguishes "no search" from "a search that matched nothing".
    const [query, setQuery] = useState("");
    const [searchHits, setSearchHits] = useState(null);
    const [searchLabel, setSearchLabel] = useState("");
    const [isSearching, setIsSearching] = useState(false);
    const [coverage, setCoverage] = useState(null);
    const [indexJobId, setIndexJobId] = useState(null);

    const images = dataset?.images || [];

    const refreshCoverage = useCallback(async () => {
        if (!dataset?.id || !token) return;
        try {
            const res = await fetch(API_ENDPOINTS.SEARCH.COVERAGE(dataset.id), {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) setCoverage(await res.json());
        } catch {
            // Search is an enhancement; a failed status probe must not surface
            // as an error on a tab whose main job is browsing images.
        }
    }, [dataset?.id, token]);

    useEffect(() => {
        refreshCoverage();
    }, [refreshCoverage]);

    // Follow an index job until it finishes, then refresh the coverage badge.
    usePolling(
        async () => {
            if (!indexJobId) return;
            try {
                const res = await fetch(API_ENDPOINTS.SEARCH.INDEX_STATUS(indexJobId), {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) {
                    setIndexJobId(null);
                    return;
                }
                const job = await res.json();
                if (job.status === "completed") {
                    setIndexJobId(null);
                    toast.success(`Indexed ${job.indexed ?? 0} image(s)`);
                    refreshCoverage();
                } else if (job.status === "failed") {
                    setIndexJobId(null);
                    toast.error(job.error || "Indexing failed");
                }
            } catch {
                setIndexJobId(null);
            }
        },
        { intervalMs: 2000, idleIntervalMs: 0, active: !!indexJobId, enabled: !!indexJobId }
    );

    const handleBuildIndex = async () => {
        try {
            const res = await fetch(API_ENDPOINTS.SEARCH.BUILD_INDEX(dataset.id), {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await res.json();
            if (!res.ok) {
                toast.error(data.detail || "Could not start indexing");
                return;
            }
            if (!data.job_id) {
                toast.info(data.message || "Already indexed");
                refreshCoverage();
                return;
            }
            setIndexJobId(data.job_id);
            toast.success(`Indexing ${data.total} image(s)…`);
        } catch {
            toast.error("Could not start indexing");
        }
    };

    const runTextSearch = async (e) => {
        e?.preventDefault?.();
        const text = query.trim();
        if (!text) return;

        setIsSearching(true);
        try {
            const res = await fetch(API_ENDPOINTS.SEARCH.TEXT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ dataset_id: dataset.id, query: text, limit: 200 }),
            });
            const data = await res.json();
            if (!res.ok) {
                toast.error(data.detail || "Search failed");
                return;
            }
            setSearchHits(data.results || []);
            setSearchLabel(`"${text}"`);
            setSelectedImages(new Set());
        } catch {
            toast.error("Search failed");
        } finally {
            setIsSearching(false);
        }
    };

    const findSimilar = async (imageId) => {
        setIsSearching(true);
        try {
            const res = await fetch(API_ENDPOINTS.SEARCH.SIMILAR, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ dataset_id: dataset.id, image_id: imageId, limit: 60 }),
            });
            const data = await res.json();
            if (!res.ok) {
                toast.error(data.detail || "Similarity search failed");
                return;
            }
            setSearchHits(data.results || []);
            setSearchLabel("images like the one you picked");
            setQuery("");
            setSelectedImages(new Set());
        } catch {
            toast.error("Similarity search failed");
        } finally {
            setIsSearching(false);
        }
    };

    const clearSearch = () => {
        setSearchHits(null);
        setSearchLabel("");
        setQuery("");
    };

    // Scores, by image id, so the grid can show a relevance badge.
    const hitScores = useMemo(() => {
        if (!searchHits) return null;
        return new Map(searchHits.map((hit) => [hit.image_id, hit.score]));
    }, [searchHits]);

    const filteredImages = images.filter((img) => {
        const matchesStatus = 
            filterStatus === "all" || 
            (filterStatus === "annotated" && img.annotated) || 
            (filterStatus === "unannotated" && !img.annotated);
            
        const matchesSplit = 
            filterSplit === "all" || 
            (img.split === filterSplit) || 
            (filterSplit === "val" && img.split === "valid"); // In case 'valid' is used instead of 'val'
            
        // A search narrows the grid to its hits; the status and split filters
        // still apply on top, so "unannotated images of a red truck" works.
        const matchesSearch = !hitScores || hitScores.has(img.id);

        return matchesStatus && matchesSplit && matchesSearch;
    });

    // Relevance order only matters while a search is active; otherwise keep
    // the upload order the rest of the tab assumes.
    const orderedImages = hitScores
        ? [...filteredImages].sort(
              (a, b) => (hitScores.get(b.id) ?? 0) - (hitScores.get(a.id) ?? 0)
          )
        : filteredImages;

    const toggleSelection = (imageId) => {
        const newSelection = new Set(selectedImages);
        if (newSelection.has(imageId)) {
            newSelection.delete(imageId);
        } else {
            newSelection.add(imageId);
        }
        setSelectedImages(newSelection);
    };

    const toggleSelectAll = () => {
        if (selectedImages.size === orderedImages.length) {
            setSelectedImages(new Set());
        } else {
            setSelectedImages(new Set(orderedImages.map(img => img.id)));
        }
    };

    const handleDelete = async (imageId) => {
        if (!(await confirm({
          title: "Delete image",
          description: "The image and its annotations will be permanently removed.",
          confirmLabel: "Delete",
        }))) return;
        
        setDeletingId(imageId);
        try {
            const res = await fetch(API_ENDPOINTS.DATASETS.DELETE_IMAGE(dataset.id, imageId), {
                method: 'DELETE',
                headers: { "Authorization": `Bearer ${token}` }
            });
            
            if (res.ok) {
                toast.success("Image deleted successfully");
                setSelectedImages(prev => {
                    const newSet = new Set(prev);
                    newSet.delete(imageId);
                    return newSet;
                });
                if (onRefresh) onRefresh();
            } else {
                const data = await res.json();
                toast.error(data.detail || "Failed to delete image");
            }
        } catch (err) {
            toast.error("Error deleting image");
        } finally {
            setDeletingId(null);
        }
    };

    const handleBulkDelete = async () => {
        if (selectedImages.size === 0) return;
        if (!(await confirm({
          title: "Delete images",
          description: `${selectedImages.size} images and their annotations will be permanently removed.`,
          confirmLabel: "Delete",
        }))) return;

        setIsDeletingBulk(true);
        let successCount = 0;
        let failCount = 0;

        for (const imageId of selectedImages) {
            try {
                const res = await fetch(API_ENDPOINTS.DATASETS.DELETE_IMAGE(dataset.id, imageId), {
                    method: 'DELETE',
                    headers: { "Authorization": `Bearer ${token}` }
                });
                if (res.ok) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (err) {
                failCount++;
            }
        }

        if (successCount > 0) {
            toast.success(`Successfully deleted ${successCount} images`);
        }
        if (failCount > 0) {
            toast.error(`Failed to delete ${failCount} images`);
        }

        setSelectedImages(new Set());
        setIsDeletingBulk(false);
        if (onRefresh) onRefresh();
    };

    const handleExportFiltered = async () => {
        if (orderedImages.length === 0) {
            toast.error("No images to export with current filters.");
            return;
        }

        setIsExporting(true);
        try {
            const zip = new JSZip();
            const imgFolder = zip.folder("images");
            
            // Limit to max 500 images to prevent browser crash, or just export all filtered
            const imagesToExport = orderedImages;
            
            let loaded = 0;
            toast.info(`Exporting ${imagesToExport.length} images... Please wait.`);
            
            for (const img of imagesToExport) {
                try {
                    const res = await fetch(`${API_BASE_URL}/api/annotations/image/${dataset.id}/${img.filename}?token=${token}`);
                    if (res.ok) {
                        const blob = await res.blob();
                        imgFolder.file(img.filename, blob);
                        loaded++;
                    }
                } catch (e) {
                    console.error("Failed to fetch image", img.filename);
                }
            }
            
            const content = await zip.generateAsync({ type: "blob" });
            const url = URL.createObjectURL(content);
            const a = document.createElement("a");
            a.href = url;
            a.download = `export_${dataset.name || "dataset"}_images.zip`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            if (loaded > 0) {
                toast.success(`Successfully exported ${loaded} images!`);
            } else {
                toast.error("Failed to export any images.");
            }
        } catch (error) {
            console.error("Export error:", error);
            toast.error("Failed to export images.");
        } finally {
            setIsExporting(false);
        }
    };

    if (images.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center p-12 text-center border rounded-none bg-card text-card-foreground">
                <ImageIcon className="w-12 h-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold">No Images Found</h3>
                <p className="text-muted-foreground mt-2">Upload images to get started.</p>
            </div>
        );
    }

    const indexedCount = coverage?.indexed_images ?? 0;
    const isFullyIndexed = coverage ? indexedCount >= images.length : false;
    const searchReady = indexedCount > 0;

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-semibold">Dataset Images</h2>
                    <p className="text-sm text-muted-foreground">Manage and remove images from your dataset.</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <select 
                        value={filterStatus}
                        onChange={(e) => setFilterStatus(e.target.value)}
                        className="text-sm bg-background border border-input rounded-none px-2 py-1"
                    >
                        <option value="all">All Status</option>
                        <option value="annotated">Annotated</option>
                        <option value="unannotated">Unannotated</option>
                    </select>

                    <select 
                        value={filterSplit}
                        onChange={(e) => setFilterSplit(e.target.value)}
                        className="text-sm bg-background border border-input rounded-none px-2 py-1"
                    >
                        <option value="all">All Splits</option>
                        <option value="train">Train</option>
                        <option value="val">Valid</option>
                        <option value="test">Test</option>
                    </select>

                    <div className="text-sm font-medium mr-2">
                        Total: {orderedImages.length}
                    </div>
                    {orderedImages.length > 0 && (
                        <>
                            <Button variant="outline" size="sm" onClick={handleExportFiltered} disabled={isExporting}>
                                <Download className="w-4 h-4 mr-2" />
                                {isExporting ? "Exporting..." : "Export Filtered"}
                            </Button>
                            <Button variant="outline" size="sm" onClick={toggleSelectAll}>
                                <CheckSquare className="w-4 h-4 mr-2" />
                                {selectedImages.size === orderedImages.length ? "Deselect All" : "Select All"}
                            </Button>
                        </>
                    )}
                    {selectedImages.size > 0 && (
                        <Button 
                            variant="destructive" 
                            size="sm" 
                            onClick={handleBulkDelete}
                            disabled={isDeletingBulk}
                        >
                            <Trash2 className="w-4 h-4 mr-2" />
                            Delete Selected ({selectedImages.size})
                        </Button>
                    )}
                </div>
            </div>

            <div className="border rounded-none bg-card text-card-foreground p-4 space-y-3">
                <form onSubmit={runTextSearch} className="flex flex-col sm:flex-row gap-2">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder={
                                searchReady
                                    ? "Describe what you are looking for — e.g. a red truck at night"
                                    : "Build the search index to search by description"
                            }
                            disabled={!searchReady || isSearching}
                            className="w-full text-sm bg-background border border-input rounded-none pl-9 pr-3 py-2 disabled:opacity-60"
                        />
                    </div>
                    <div className="flex items-center gap-2">
                        <Button type="submit" size="sm" disabled={!searchReady || isSearching || !query.trim()}>
                            <Sparkles className="w-4 h-4 mr-2" />
                            {isSearching ? "Searching..." : "Search"}
                        </Button>
                        {searchHits && (
                            <Button type="button" variant="outline" size="sm" onClick={clearSearch}>
                                <X className="w-4 h-4 mr-2" />
                                Clear
                            </Button>
                        )}
                    </div>
                </form>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {coverage?.available === false ? (
                        <span>
                            Semantic search is unavailable on this server — it needs numpy and torch.
                        </span>
                    ) : (
                        <>
                            <span>
                                Indexed {indexedCount} of {images.length} image(s)
                            </span>
                            {!isFullyIndexed && (
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={handleBuildIndex}
                                    disabled={!!indexJobId}
                                >
                                    {indexJobId ? "Indexing..." : "Build index"}
                                </Button>
                            )}
                        </>
                    )}
                    {searchHits && (
                        <span className="text-foreground">
                            Showing {orderedImages.length} result(s) for {searchLabel}, best match first
                        </span>
                    )}
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mt-6">
                {orderedImages.map((img) => {
                    const isSelected = selectedImages.has(img.id);
                    return (
                        <div 
                            key={img.id} 
                            className={`group relative border rounded-none overflow-hidden bg-muted/20 aspect-square transition-all cursor-pointer ${
                                isSelected ? "ring-2 ring-primary ring-offset-2" : ""
                            }`}
                            onClick={() => toggleSelection(img.id)}
                        >
                            <img 
                                src={API_ENDPOINTS.ANNOTATIONS.GET_THUMBNAIL(dataset.id, img.filename, token, 320)}
                                alt={img.original_name || img.filename} 
                                className={`w-full h-full object-cover transition-transform ${isSelected ? "scale-95" : ""}`} 
                                onError={(e) => { e.target.src = 'https://via.placeholder.com/300?text=Image+Not+Found' }}
                            />
                            
                            <div className="absolute inset-0 bg-black/10 transition-opacity flex flex-col justify-between p-2">
                                <div className="flex justify-between items-start">
                                    <input 
                                        type="checkbox"
                                        checked={isSelected}
                                        onChange={() => toggleSelection(img.id)}
                                        className="w-5 h-5 rounded cursor-pointer accent-primary"
                                        onClick={(e) => e.stopPropagation()}
                                    />
                                    <div className="flex items-center gap-1">
                                        {searchReady && (
                                            <Button
                                                variant="secondary"
                                                size="icon"
                                                aria-label="Find similar images"
                                                title="Find similar images"
                                                className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                                                disabled={isSearching}
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    findSimilar(img.id);
                                                }}
                                            >
                                                <Copy className="h-4 w-4" />
                                            </Button>
                                        )}
                                        <Button 
                                            variant="destructive" 
                                            size="icon"
                                            aria-label="Delete image"
                                            className={`h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity ${isSelected ? "opacity-100" : ""}`}
                                            disabled={deletingId === img.id}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDelete(img.id);
                                            }}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                                <div className="flex items-center justify-between gap-1">
                                    <div className="text-xs text-white truncate px-1 drop-shadow-none bg-black/50 py-1 rounded">
                                        {img.original_name || img.filename}
                                    </div>
                                    {hitScores?.has(img.id) && (
                                        <span
                                            className="text-xs text-white bg-primary/80 px-1.5 py-1 rounded shrink-0"
                                            title="Cosine similarity to your query"
                                        >
                                            {hitScores.get(img.id).toFixed(2)}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
