"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Layers, RefreshCw, Check } from "lucide-react";
import { toast } from 'sonner';
import { API_ENDPOINTS } from "@/lib/config";
import { useAuth } from "@/context/AuthContext";

export default function ProjectGenerate({ dataset, stats, onGenerate }) {
    const { token } = useAuth();
    const [augmentations, setAugmentations] = useState({
        flipHorizontal: false,
        flipVertical: false,
        rotate: false,
        blur: false,
        noise: false
    });
    const [generating, setGenerating] = useState(false);

    const handleGenerate = async () => {
        setGenerating(true);
        try {
            // For MVP, we'll hit the export endpoint which "prepares" the dataset.
            // In a real augmentation system, this would trigger a job to generate new images.
            // We'll simulate this for the UI.

            // Send augmentation config to backend
            const response = await fetch(API_ENDPOINTS.DATASETS.EXPORT(dataset.id), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    split_ratio: 0.8,
                    config: augmentations
                })
            });

            if (response.ok) {
                toast.success("Version generated successfully!");
                if (onGenerate) onGenerate();
            } else {
                toast.error("Failed to generate version");
            }
        } catch (e) {
            toast.error("Error: " + e.message);
        } finally {
            setGenerating(false);
        }
    };

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Generate Version</h2>
                    <p className="text-muted-foreground text-sm">Apply augmentations and freeze your dataset for training.</p>
                </div>
                <Button onClick={handleGenerate} disabled={generating}>
                    {generating ? <RefreshCw className="mr-2 animate-spin" /> : <Layers className="mr-2" />}
                    {generating ? "Generating..." : "Generate Version"}
                </Button>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
                {/* Pre-processing */}
                <Card>
                    <CardHeader>
                        <CardTitle>Preprocessing</CardTitle>
                        <CardDescription>Applied to all images</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center justify-between">
                            <Label>Auto-Orient</Label>
                            <Badge variant="secondary">Applied</Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <Label>Resize</Label>
                            <Badge variant="outline">640x640 (Stretch)</Badge>
                        </div>
                    </CardContent>
                </Card>

                {/* Augmentations */}
                <Card>
                    <CardHeader>
                        <CardTitle>Augmentations</CardTitle>
                        <CardDescription>Creates new training examples</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Horizontal Flip</Label>
                                <p className="text-xs text-muted-foreground">Randomly flip images horizontally</p>
                            </div>
                            <Switch
                                checked={augmentations.flipHorizontal}
                                onCheckedChange={c => setAugmentations({ ...augmentations, flipHorizontal: c })}
                            />
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Vertical Flip</Label>
                                <p className="text-xs text-muted-foreground">Randomly flip images vertically</p>
                            </div>
                            <Switch
                                checked={augmentations.flipVertical}
                                onCheckedChange={c => setAugmentations({ ...augmentations, flipVertical: c })}
                            />
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Grayscale</Label>
                                <p className="text-xs text-muted-foreground">Convert to black and white</p>
                            </div>
                            <Switch
                                checked={augmentations.noise}
                                onCheckedChange={c => setAugmentations({ ...augmentations, noise: c })}
                            />
                        </div>
                    </CardContent>
                </Card>
            </div>

            <Card className="bg-muted/30 border-dashed">
                <CardContent className="p-6 text-center">
                    <h3 className="font-semibold mb-2"> Estimated Version Size</h3>
                    <p className="text-muted-foreground">
                        {stats?.train_images || 0} → ~{Math.round((stats?.train_images || 0) * (1 + Object.values(augmentations).filter(Boolean).length * 0.5))} images
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
