"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { API_ENDPOINTS, API_BASE_URL } from "@/lib/config";
import { Trash2, Image as ImageIcon, CheckSquare } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function ProjectImages({ dataset, onRefresh }) {
    const { token } = useAuth();
    const [deletingId, setDeletingId] = useState(null);
    const [isDeletingBulk, setIsDeletingBulk] = useState(false);
    const [selectedImages, setSelectedImages] = useState(new Set());

    const images = dataset?.images || [];

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
        if (selectedImages.size === images.length) {
            setSelectedImages(new Set());
        } else {
            setSelectedImages(new Set(images.map(img => img.id)));
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

    if (images.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center p-12 text-center border rounded-xl bg-card text-card-foreground">
                <ImageIcon className="w-12 h-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold">No Images Found</h3>
                <p className="text-muted-foreground mt-2">Upload images to get started.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-semibold">Dataset Images</h2>
                    <p className="text-sm text-muted-foreground">Manage and remove images from your dataset.</p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="text-sm font-medium mr-2">
                        Total: {images.length}
                    </div>
                    {images.length > 0 && (
                        <Button variant="outline" size="sm" onClick={toggleSelectAll}>
                            <CheckSquare className="w-4 h-4 mr-2" />
                            {selectedImages.size === images.length ? "Deselect All" : "Select All"}
                        </Button>
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

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {images.map((img) => {
                    const isSelected = selectedImages.has(img.id);
                    return (
                        <div 
                            key={img.id} 
                            className={`group relative border rounded-lg overflow-hidden bg-muted/20 aspect-square transition-all cursor-pointer ${
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
                                <div className="text-xs text-white truncate px-1 drop-shadow-md bg-black/50 py-1 rounded">
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
