"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { API_ENDPOINTS, API_BASE_URL } from "@/lib/config";
import { Trash2, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function ProjectImages({ dataset, onRefresh }) {
    const { token } = useAuth();
    const [deletingId, setDeletingId] = useState(null);

    const images = dataset?.images || [];

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
                <div className="text-sm font-medium">
                    Total: {images.length}
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {images.map((img) => (
                    <div key={img.id} className="group relative border rounded-lg overflow-hidden bg-muted/20 aspect-square">
                        <img 
                            src={`${API_BASE_URL}/api/annotations/image/${dataset.id}/${img.filename}?token=${token}`}
                            alt={img.original_name || img.filename} 
                            className="w-full h-full object-cover" 
                            onError={(e) => { e.target.src = 'https://via.placeholder.com/300?text=Image+Not+Found' }}
                        />
                        
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-between p-2">
                            <div className="flex justify-end">
                                <Button 
                                    variant="destructive" 
                                    size="icon"
                                    className="h-8 w-8"
                                    disabled={deletingId === img.id}
                                    onClick={() => handleDelete(img.id)}
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                            <div className="text-xs text-white truncate px-1 drop-shadow-md">
                                {img.original_name || img.filename}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
