"use client";

import { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Upload } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectUpload({ dataset, onUploadComplete }) {
    const { token } = useAuth();
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);

    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleDrop = useCallback(async (e) => {
        e.preventDefault();
        setIsDragging(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) await uploadFiles(files);
    }, []);

    const uploadFiles = async (files) => {
        const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'];
        const invalidFiles = files.filter(file => !validTypes.includes(file.type));

        if (invalidFiles.length > 0) {
            toast.error(`Invalid file types: ${invalidFiles.map(f => f.name).join(', ')}`);
            return;
        }

        setUploading(true);
        const formData = new FormData();
        files.forEach(file => formData.append("files", file));

        try {
            const response = await fetch(API_ENDPOINTS.DATASETS.UPLOAD(dataset.id), {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`
                },
                body: formData,
            });

            const data = await response.json();

            if (data.success) {
                toast.success(`Uploaded ${data.uploaded} images successfully`);
                if (data.errors?.length > 0) {
                    toast.warning(`${data.error_count} files failed to upload`);
                }
                if (onUploadComplete) onUploadComplete();
            } else {
                toast.error(data.detail || "Upload failed");
            }
        } catch (error) {
            toast.error("Upload error: " + error.message);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Upload Data</h2>
                    <p className="text-muted-foreground text-sm">Add images to your dataset for annotation.</p>
                </div>
            </div>

            <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`flex-1 border-2 border-dashed rounded-xl flex flex-col items-center justify-center p-12 transition-all ${isDragging
                    ? "border-primary bg-primary/5 scale-[0.99]"
                    : "border-border hover:border-primary/50 hover:bg-muted/30"
                    }`}
            >
                <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center mb-6">
                    <Upload className={`text-3xl ${isDragging ? "text-primary" : "text-muted-foreground"}`} />
                </div>
                <h3 className="text-lg font-medium mb-2">
                    {uploading ? "Uploading..." : "Drag and drop images here"}
                </h3>
                <p className="text-muted-foreground mb-8 max-w-sm text-center">
                    Support for JPG, PNG, BMP. Images will be automatically deduped.
                </p>
                <Button
                    size="lg"
                    disabled={uploading}
                    onClick={() => {
                        const input = document.createElement('input');
                        input.type = 'file';
                        input.multiple = true;
                        input.accept = 'image/*';
                        input.onchange = (e) => {
                            if (e.target.files.length > 0) uploadFiles(Array.from(e.target.files));
                        };
                        input.click();
                    }}
                >
                    Select Images
                </Button>
            </div>
        </div>
    );
}
