"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { API_ENDPOINTS, API_BASE_URL } from "@/lib/config";
import { Trash2, Image as ImageIcon, CheckSquare, Download } from "lucide-react";
import JSZip from "jszip";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function ProjectImages({ dataset, onRefresh }) {
    const { token } = useAuth();
    const [deletingId, setDeletingId] = useState(null);
    const [isDeletingBulk, setIsDeletingBulk] = useState(false);
    const [selectedImages, setSelectedImages] = useState(new Set());
    const [filterStatus, setFilterStatus] = useState("all"); // 'all', 'annotated', 'unannotated'
    const [filterSplit, setFilterSplit] = useState("all"); // 'all', 'train', 'val', 'test'
    const [isExporting, setIsExporting] = useState(false);

    const images = dataset?.images || [];
    const filteredImages = images.filter((img) => {
        const matchesStatus = 
            filterStatus === "all" || 
            (filterStatus === "annotated" && img.annotated) || 
            (filterStatus === "unannotated" && !img.annotated);
            
        const matchesSplit = 
            filterSplit === "all" || 
            (img.split === filterSplit) || 
            (filterSplit === "val" && img.split === "valid"); // In case 'valid' is used instead of 'val'
            
        return matchesStatus && matchesSplit;
    });

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
        if (selectedImages.size === filteredImages.length) {
            setSelectedImages(new Set());
        } else {
            setSelectedImages(new Set(filteredImages.map(img => img.id)));
        }
    };

    const handleDelete = async (imageId) => {
        if (!confirm("Are you sure you want to delete this image?")) return;
        
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
        if (!confirm(`Are you sure you want to delete ${selectedImages.size} images?`)) return;

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
        if (filteredImages.length === 0) {
            toast.error("No images to export with current filters.");
            return;
        }

        setIsExporting(true);
        try {
            const zip = new JSZip();
            const imgFolder = zip.folder("images");
            
            // Limit to max 500 images to prevent browser crash, or just export all filtered
            const imagesToExport = filteredImages;
            
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
                        Total: {filteredImages.length}
                    </div>
                    {filteredImages.length > 0 && (
                        <>
                            <Button variant="outline" size="sm" onClick={handleExportFiltered} disabled={isExporting}>
                                <Download className="w-4 h-4 mr-2" />
                                {isExporting ? "Exporting..." : "Export Filtered"}
                            </Button>
                            <Button variant="outline" size="sm" onClick={toggleSelectAll}>
                                <CheckSquare className="w-4 h-4 mr-2" />
                                {selectedImages.size === filteredImages.length ? "Deselect All" : "Select All"}
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

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mt-6">
                {filteredImages.map((img) => {
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
                                src={`${API_BASE_URL}/api/annotations/image/${dataset.id}/${img.filename}?token=${token}`}
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
                                    <Button 
                                        variant="destructive" 
                                        size="icon"
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
                                <div className="text-xs text-white truncate px-1 drop-shadow-none bg-black/50 py-1 rounded">
                                    {img.original_name || img.filename}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
