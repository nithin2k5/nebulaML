"use client";

import { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Upload, Film, Image as ImageIcon } from "lucide-react";
import { API_ENDPOINTS } from "@/lib/config";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

export default function ProjectUpload({ dataset, onUploadComplete, onNavigate }) {
    const { token } = useAuth();
    const [isDragging, setIsDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [frameInterval, setFrameInterval] = useState(30);
    const [videoDetected, setVideoDetected] = useState(false);
    const [uploadProgress, setUploadProgress] = useState("");
    const [importFormat, setImportFormat] = useState("yolo");

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

    const handleDrop = useCallback(async (e, isImport = false) => {
        e.preventDefault();
        setIsDragging(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) {
            if (isImport) await handleImportZip(files[0]);
            else await handleFiles(files);
        }
    }, [frameInterval, importFormat]);

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

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || `Server error ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                toast.success(`Uploaded ${data.uploaded} images successfully`, {
                    action: onNavigate ? {
                        label: "Check Health",
                        onClick: () => onNavigate("health"),
                    } : undefined,
                    duration: 6000,
                });
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
                    `(${info.duration_seconds}s @ ${info.fps}fps)`,
                    {
                        action: onNavigate ? {
                            label: "Check Health",
                            onClick: () => onNavigate("health"),
                        } : undefined,
                        duration: 6000,
                    }
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

    const handleImportZip = async (file) => {
        if (!file.name.toLowerCase().endsWith(".zip")) {
            toast.error("Please upload a .zip file containing your dataset.");
            return;
        }

        setUploading(true);
        setUploadProgress(`Importing ${importFormat.toUpperCase()} dataset...`);
        
        const formData = new FormData();
        formData.append("file", file);
        formData.append("format_type", importFormat);

        try {
            const response = await fetch(`${API_ENDPOINTS.DATASETS.BASE || (API_ENDPOINTS.BASE_URL + "/datasets")}/${dataset.id}/import`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` },
                body: formData,
            });

            const data = await response.json();

            if (response.ok && data.success) {
                toast.success(`Imported ${data.images_imported} images and ${data.annotations_imported} annotations successfully!`, {
                    action: onNavigate ? {
                        label: "View Data",
                        onClick: () => onNavigate("annotate"),
                    } : undefined,
                    duration: 6000,
                });
                if (onUploadComplete) onUploadComplete();
            } else {
                toast.error(data.detail || "Import failed");
            }
        } catch (error) {
            toast.error("Import error: " + error.message);
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

            <Tabs defaultValue="upload" className="w-full h-full flex flex-col">
                <TabsList className="mb-4 w-full grid grid-cols-2 max-w-[400px]">
                    <TabsTrigger value="upload">Raw Upload</TabsTrigger>
                    <TabsTrigger value="import">Import Dataset (ZIP)</TabsTrigger>
                </TabsList>

                <TabsContent value="upload" className="flex-1 flex flex-col gap-4 m-0 h-full">
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
                        onDrop={(e) => handleDrop(e, false)}
                        className={`flex-1 min-h-[300px] border-2 border-dashed rounded-xl flex flex-col items-center justify-center p-12 transition-all ${isDragging
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
                            Support for images (JPG, PNG) and videos (MP4, MOV). Videos will be automatically converted to frames.
                        </p>
                        <div className="flex gap-4">
                            <Button variant="outline" className="relative cursor-pointer" disabled={uploading}>
                                <ImageIcon className="w-4 h-4 mr-2" />
                                Browse Images & Videos
                                <input
                                    type="file"
                                    multiple
                                    accept={[...imageTypes, ...videoExtensions].join(",")}
                                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                                    onChange={(e) => handleFiles(Array.from(e.target.files))}
                                    disabled={uploading}
                                />
                            </Button>
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="import" className="flex-1 flex flex-col gap-4 m-0 h-full">
                    <Card className="border-border">
                        <CardContent className="p-4">
                            <div className="flex items-center gap-4">
                                <div className="flex-1 space-y-2">
                                    <Label className="text-sm font-medium">Dataset Format</Label>
                                    <Select value={importFormat} onValueChange={setImportFormat}>
                                        <SelectTrigger className="w-full max-w-[300px]">
                                            <SelectValue placeholder="Select format" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="yolo">YOLO (TXT files)</SelectItem>
                                            <SelectItem value="coco">COCO (JSON file)</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    <p className="text-xs text-muted-foreground">
                                        Ensure your project classes exactly match the dataset classes before importing. 
                                        ZIP should contain images and annotations.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={(e) => handleDrop(e, true)}
                        className={`flex-1 min-h-[300px] border-2 border-dashed rounded-xl flex flex-col items-center justify-center p-12 transition-all ${isDragging
                            ? "border-primary bg-primary/5 scale-[0.99]"
                            : "border-border hover:border-primary/50 hover:bg-muted/30"
                            }`}
                    >
                        <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center mb-6">
                            <Upload className={`text-3xl ${isDragging ? "text-primary" : "text-muted-foreground"}`} />
                        </div>
                        <h3 className="text-lg font-medium mb-2">
                            {uploading ? uploadProgress || "Importing dataset..." : "Drag and drop ZIP here"}
                        </h3>
                        <p className="text-muted-foreground mb-4 max-w-sm text-center">
                            Upload a .zip file containing your {importFormat.toUpperCase()} dataset structure.
                        </p>
                        <div className="flex gap-4">
                            <Button variant="outline" className="relative cursor-pointer" disabled={uploading}>
                                Browse ZIP
                                <input
                                    type="file"
                                    accept=".zip"
                                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                                    onChange={(e) => {
                                        if (e.target.files.length > 0) handleImportZip(e.target.files[0]);
                                    }}
                                    disabled={uploading}
                                />
                            </Button>
                        </div>
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    );
}
