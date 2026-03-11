"use client";

import { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Upload, Film, Image as ImageIcon } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectUpload({ dataset, onUploadComplete }) {
    const { token } = useAuth();
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [frameInterval, setFrameInterval] = useState(30);
    const [videoDetected, setVideoDetected] = useState(false);
    const [uploadProgress, setUploadProgress] = useState("");

    const videoExtensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"];
    const imageTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'];

    const isVideoFile = (file) => {
        const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
        return videoExtensions.includes(ext) || file.type.startsWith('video/');
    };

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
        if (files.length > 0) await handleFiles(files);
    }, [frameInterval]);

    const handleFiles = async (files) => {
        const videos = files.filter(isVideoFile);
        const images = files.filter(f => !isVideoFile(f));

        // Upload images normally
        if (images.length > 0) {
            const validImages = images.filter(f => imageTypes.includes(f.type));
            if (validImages.length > 0) await uploadImages(validImages);
            if (validImages.length < images.length) {
                toast.warning(`${images.length - validImages.length} files had invalid image formats`);
            }
        }

        // Extract frames from videos
        for (const video of videos) {
            await extractFrames(video);
        }
    };

    const uploadImages = async (files) => {
        setUploading(true);
        setUploadProgress(`Uploading ${files.length} images...`);
        const formData = new FormData();
        files.forEach(file => formData.append("files", file));

        try {
            const response = await fetch(API_ENDPOINTS.DATASETS.UPLOAD(dataset.id), {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` },
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
            setUploadProgress("");
        }
    };

    const extractFrames = async (videoFile) => {
        setUploading(true);
        setUploadProgress(`Extracting frames from ${videoFile.name}...`);

        const formData = new FormData();
        formData.append("file", videoFile);
        formData.append("dataset_id", dataset.id);
        formData.append("frame_interval", frameInterval.toString());
        formData.append("max_frames", "500");

        try {
            const response = await fetch(API_ENDPOINTS.VIDEO.EXTRACT_FRAMES, {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` },
                body: formData,
            });

            const data = await response.json();

            if (data.success) {
                const info = data.video_info;
                toast.success(
                    `Extracted ${data.extraction.frames_extracted} frames from ${info.filename} ` +
                    `(${info.duration_seconds}s @ ${info.fps}fps)`
                );
                if (onUploadComplete) onUploadComplete();
            } else {
                toast.error(data.detail || "Frame extraction failed");
            }
        } catch (error) {
            toast.error("Video extraction error: " + error.message);
        } finally {
            setUploading(false);
            setUploadProgress("");
        }
    };

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Upload Data</h2>
                    <p className="text-muted-foreground text-sm">Add images or videos to your dataset for annotation.</p>
                </div>
            </div>

            {/* Video Settings */}
            <Card className="border-border">
                <CardContent className="p-4">
                    <div className="flex items-center gap-4">
                        <Film className="w-5 h-5 text-primary shrink-0" />
                        <div className="flex-1 space-y-1">
                            <Label className="text-sm font-medium">Video Frame Extraction Interval: Every {frameInterval} frames</Label>
                            <Slider
                                min={1}
                                max={120}
                                step={1}
                                value={[frameInterval]}
                                onValueChange={([v]) => setFrameInterval(v)}
                                className="w-full"
                            />
                            <p className="text-xs text-muted-foreground">
                                At 30fps: extracts ~{Math.max(1, Math.round(30 / frameInterval))} frame/sec.
                                Lower = more frames, higher = fewer but more varied.
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>

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
                    {uploading ? uploadProgress || "Processing..." : "Drag and drop files here"}
                </h3>
                <p className="text-muted-foreground mb-4 max-w-sm text-center">
                    Support for <strong>JPG, PNG, BMP</strong> images and <strong>MP4, MOV, AVI, MKV</strong> videos.
                </p>
                <p className="text-xs text-muted-foreground mb-6">
                    Videos are automatically split into individual frames for annotation.
                </p>
                <div className="flex gap-3">
                    <Button
                        size="lg"
                        disabled={uploading}
                        onClick={() => {
                            const input = document.createElement('input');
                            input.type = 'file';
                            input.multiple = true;
                            input.accept = 'image/*';
                            input.onchange = (e) => {
                                if (e.target.files.length > 0) handleFiles(Array.from(e.target.files));
                            };
                            input.click();
                        }}
                    >
                        <ImageIcon className="mr-2 w-4 h-4" />
                        Select Images
                    </Button>
                    <Button
                        size="lg"
                        variant="outline"
                        disabled={uploading}
                        onClick={() => {
                            const input = document.createElement('input');
                            input.type = 'file';
                            input.accept = '.mp4,.mov,.avi,.mkv,.webm';
                            input.onchange = (e) => {
                                if (e.target.files.length > 0) handleFiles(Array.from(e.target.files));
                            };
                            input.click();
                        }}
                    >
                        <Film className="mr-2 w-4 h-4" />
                        Select Video
                    </Button>
                </div>
            </div>
        </div>
    );
}
