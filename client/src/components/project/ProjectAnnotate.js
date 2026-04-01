"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, Image, Settings, CheckCircle, ArrowRight, Layers } from "lucide-react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ProjectAnnotate({ dataset, stats, onNavigate }) {
    const router = useRouter();

    const total = stats?.total_images || 0;
    const annotated = stats?.annotated_images || 0;
    const unannotated = total - annotated;
    const progress = total > 0 ? (annotated / total) * 100 : 0;
    const isComplete = total > 0 && unannotated === 0;

    const progressColor = progress >= 80 ? "bg-emerald-500" : progress >= 30 ? "bg-amber-500" : "bg-red-500";
    const progressBorder = progress >= 80 ? "border-emerald-500/30 bg-emerald-500/5" : progress >= 30 ? "border-amber-500/30 bg-amber-500/5" : "border-red-500/30 bg-red-500/5";

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold">Annotate</h2>
                    <p className="text-muted-foreground text-sm">Label objects in your images to prepare for training.</p>
                </div>
                <Button onClick={() => router.push(`/annotate?dataset=${dataset.id}`)}>
                    Open Annotation Tool <ExternalLink className="ml-2 w-4 h-4" />
                </Button>
            </div>

            {/* Progress Bar */}
            {total > 0 && (
                <div className={`p-4 rounded-lg border ${progressBorder}`}>
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-sm font-medium">Annotation Progress</span>
                        <span className="text-sm font-semibold tabular-nums">{annotated} / {total} images</span>
                    </div>
                    <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                        <div
                            className={`h-full rounded-full transition-all duration-500 ${progressColor}`}
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                    <div className="flex justify-between mt-1.5">
                        <span className="text-xs text-muted-foreground">{Math.round(progress)}% annotated</span>
                        {unannotated > 0 && (
                            <span className="text-xs text-muted-foreground">{unannotated} remaining</span>
                        )}
                    </div>
                </div>
            )}

            {/* Ready to Generate CTA */}
            {isComplete && (
                <div className="flex items-center justify-between p-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10">
                    <div className="flex items-center gap-3">
                        <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
                        <div>
                            <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">All images annotated!</p>
                            <p className="text-xs text-muted-foreground">Your dataset is ready. Generate a version to start training.</p>
                        </div>
                    </div>
                    <Button size="sm" onClick={() => onNavigate?.("generate")}>
                        <Layers className="w-4 h-4 mr-1.5" />
                        Generate Version
                        <ArrowRight className="w-4 h-4 ml-1.5" />
                    </Button>
                </div>
            )}

            <div className="grid md:grid-cols-3 gap-6">
                {/* Unannotated */}
                <Card>
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4 mb-4">
                            <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center text-primary">
                                <Image className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-semibold">Unannotated</h3>
                                <p className="text-2xl font-bold tabular-nums">{unannotated}</p>
                            </div>
                        </div>
                        <Button
                            variant="secondary"
                            className="w-full"
                            onClick={() => router.push(`/annotate?dataset=${dataset.id}`)}
                            disabled={unannotated === 0}
                        >
                            {unannotated > 0 ? "Start Labeling" : "All Done"}
                        </Button>
                    </CardContent>
                </Card>

                {/* Annotated */}
                <Card>
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4 mb-4">
                            <div className="w-12 h-12 bg-emerald-500/10 rounded-lg flex items-center justify-center text-emerald-500">
                                <CheckCircle className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-semibold">Annotated</h3>
                                <p className="text-2xl font-bold tabular-nums">{annotated}</p>
                            </div>
                        </div>
                        <Button
                            variant="outline"
                            className="w-full"
                            onClick={() => router.push(`/annotate?dataset=${dataset.id}`)}
                            disabled={annotated === 0}
                        >
                            Review Annotations
                        </Button>
                    </CardContent>
                </Card>

                {/* Classes */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base flex items-center gap-2">
                            <Settings className="w-4 h-4" /> Classes
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold tabular-nums mb-3">{dataset.classes?.length || 0}</p>
                        <div className="flex flex-wrap gap-1.5">
                            {dataset.classes?.map((c, i) => (
                                <Badge key={i} variant="outline" className="text-xs">{c}</Badge>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {total === 0 && (
                <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
                    <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mb-4">
                        <Image className="w-7 h-7 text-muted-foreground" />
                    </div>
                    <h3 className="font-semibold mb-1">No images yet</h3>
                    <p className="text-sm text-muted-foreground max-w-sm mb-4">Upload images first, then come back to annotate them.</p>
                    <Button variant="outline" onClick={() => onNavigate?.("upload")}>
                        Go to Upload <ArrowRight className="w-4 h-4 ml-1.5" />
                    </Button>
                </div>
            )}
        </div>
    );
}
