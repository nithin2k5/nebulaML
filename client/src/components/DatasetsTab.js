"use client";

import { useAuth } from "@/context/AuthContext";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { API_ENDPOINTS } from "@/lib/config";
import { cn } from "@/lib/utils";
import { toast } from 'sonner';
import {
  Plus, Image, Box, Trash2, Download, Cpu,
  Database, ChevronRight, Upload, Folder, Check,
  FolderKanban
} from "lucide-react";

export default function DatasetsTab() {
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newDataset, setNewDataset] = useState({ name: "", description: "", classes: "" });
  const [showCreate, setShowCreate] = useState(false);
  const router = useRouter();
  const { token } = useAuth();

  useEffect(() => {
    fetchDatasets();
  }, []);

  const fetchDatasets = async () => {
    setLoading(true);
    try {
      const headers = { "Authorization": `Bearer ${token}` };
      const response = await fetch(API_ENDPOINTS.DATASETS.LIST, { headers });
      if (!response.ok) throw new Error("Failed to fetch");
      const rawData = await response.json();
      const data = Array.isArray(rawData) ? rawData : (rawData.datasets || []);

      const datasetsWithStats = await Promise.all(
        data.map(async (ds) => {
          try {
            const statsRes = await fetch(API_ENDPOINTS.DATASETS.STATS(ds.id), { headers });
            if (statsRes.ok) {
              const stats = await statsRes.json();
              return { ...ds, stats };
            }
          } catch (e) { /* ignore */ }
          return { ...ds, stats: { total_images: 0, annotated_images: 0 } };
        })
      );

      setDatasets(datasetsWithStats);
    } catch (error) {
      console.error(error);
      toast.error("Failed to fetch datasets");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDataset = async () => {
    if (!newDataset.name.trim()) {
      toast.error("Dataset name is required");
      return;
    }

    const classesArray = newDataset.classes
      .split(",")
      .map(c => c.trim())
      .filter(c => c.length > 0);

    if (classesArray.length === 0) {
      toast.error("At least one class is required");
      return;
    }

    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.CREATE, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          name: newDataset.name.trim(),
          description: newDataset.description.trim(),
          classes: classesArray,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`Dataset "${newDataset.name}" created!`);
        setNewDataset({ name: "", description: "", classes: "" });
        setShowCreate(false);
        fetchDatasets();
        router.push(`/project/${data.dataset_id}`);
      } else {
        const err = await response.json();
        toast.error(err.detail || "Create failed");
      }
    } catch (error) {
      toast.error("Error: " + error.message);
    }
  };

  const handleDelete = async (id, name) => {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.DELETE(id), {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (response.ok) {
        toast.success(`"${name}" deleted`);
        fetchDatasets();
      } else {
        toast.error("Delete failed");
      }
    } catch (error) {
      toast.error("Delete error: " + error.message);
    }
  };

  const handleExport = async (id) => {
    const toastId = toast.loading('Preparing export...', { description: '0%' });
    try {
      const response = await fetch(`http://localhost:8000/api/annotations/datasets/${id}/export`, {
        method: 'POST',
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({})
      });

      if (!response.ok) throw new Error("Export request failed");
      const data = await response.json();

      if (data.job_id) {
        const interval = setInterval(async () => {
          try {
            const statusRes = await fetch(`http://localhost:8000/api/annotations/datasets/${id}/export-status/${data.job_id}`);
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              if (statusData.status === "completed") {
                clearInterval(interval);
                toast.success("Export ready! Downloading...", { id: toastId });
                downloadDataset(id);
              } else if (statusData.status === "failed") {
                clearInterval(interval);
                toast.error("Export failed: " + statusData.error, { id: toastId });
              } else {
                toast.loading('Preparing export...', { description: `${statusData.progress || 0}%`, id: toastId });
              }
            }
          } catch (err) {
            console.error("Polling error:", err);
          }
        }, 1000);
      } else {
        toast.success("Export ready! Downloading...", { id: toastId });
        downloadDataset(id);
      }
    } catch (error) {
      toast.error("Export failed", { id: toastId });
    }
  };

  const downloadDataset = async (id) => {
    try {
      const downloadResponse = await fetch(`http://localhost:8000/api/annotations/datasets/${id}/download`, {
        headers: { "Authorization": `Bearer ${token}` }
      });

      if (!downloadResponse.ok) throw new Error("Download failed");

      const blob = await downloadResponse.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dataset_${id}_export.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      toast.error("Download failed");
    }
  };

  return (
    <div className="space-y-8 animate-fade-in text-gray-100">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">Datasets</h2>
          <p className="text-muted-foreground mt-1">Create, manage, and annotate your object detection datasets.</p>
        </div>
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogTrigger asChild>
            <Button className="bg-indigo-600 hover:bg-indigo-500 text-white">
              <Plus className="mr-2" /> New Dataset
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-white/10">
            <DialogHeader>
              <DialogTitle>Create Dataset</DialogTitle>
              <DialogDescription>Define your dataset and its object classes.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input
                  placeholder="e.g., Traffic Signs v1"
                  value={newDataset.name}
                  onChange={e => setNewDataset({ ...newDataset, name: e.target.value })}
                  className="bg-black/30 border-white/10"
                />
              </div>
              <div className="space-y-2">
                <Label>Description <span className="text-gray-500">(optional)</span></Label>
                <Input
                  placeholder="Brief description..."
                  value={newDataset.description}
                  onChange={e => setNewDataset({ ...newDataset, description: e.target.value })}
                  className="bg-black/30 border-white/10"
                />
              </div>
              <div className="space-y-2">
                <Label>Classes <span className="text-gray-500">(comma-separated)</span></Label>
                <Input
                  placeholder="e.g., stop_sign, yield, speed_limit"
                  value={newDataset.classes}
                  onChange={e => setNewDataset({ ...newDataset, classes: e.target.value })}
                  className="bg-black/30 border-white/10"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreate(false)} className="border-white/10">Cancel</Button>
              <Button onClick={handleCreateDataset} className="bg-indigo-600 hover:bg-indigo-500">Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-48 rounded-2xl bg-white/5 animate-shimmer border border-white/5" />
          ))}
        </div>
      ) : datasets.length === 0 ? (
        <div className="py-20 text-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] max-w-2xl mx-auto">
          <div className="w-20 h-20 rounded-full bg-indigo-500/10 flex items-center justify-center mx-auto mb-6 text-indigo-400">
            <Folder className="text-4xl" />
          </div>
          <h3 className="text-2xl font-bold mb-3">Welcome to NebulaML</h3>
          <p className="text-gray-400 mb-8 max-w-md mx-auto leading-relaxed">
            You don&apos;t have any datasets yet. Create your first dataset to start the ML pipeline.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left max-w-xl mx-auto mb-10">
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center mb-3">1</div>
              <h4 className="font-semibold text-sm mb-1">Create Dataset</h4>
              <p className="text-xs text-gray-500">Define classes and metadata</p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5 opacity-70">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center mb-3">2</div>
              <h4 className="font-semibold text-sm mb-1">Upload & Label</h4>
              <p className="text-xs text-gray-500">Add images and bounding boxes</p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5 opacity-70">
              <div className="w-8 h-8 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center mb-3">3</div>
              <h4 className="font-semibold text-sm mb-1">Train Model</h4>
              <p className="text-xs text-gray-500">Click to train YOLO automatically</p>
            </div>
          </div>

          <Button onClick={() => setShowCreate(true)} size="lg" className="bg-indigo-600 hover:bg-indigo-500 text-white px-8 rounded-full shadow-[0_0_20px_rgba(99,102,241,0.3)] transition-transform hover:scale-105">
            <Plus className="mr-2" /> Create First Dataset
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {datasets?.map((dataset) => {
            const total = dataset.stats?.total_images || 0;
            const annotated = dataset.stats?.annotated_images || 0;
            const progress = total > 0 ? Math.round((annotated / total) * 100) : 0;

            return (
              <div
                key={dataset.id}
                className="group rounded-2xl bg-card/40 backdrop-blur-md border border-white/5 hover:border-indigo-500/30 hover:bg-white/5 transition-all duration-300 flex flex-col overflow-hidden shadow-lg"
              >
                <div className="p-6 flex-1">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500/20 transition-all">
                      <FolderKanban className="text-lg" />
                    </div>
                    <Badge variant="outline" className="text-[10px] h-5 border-white/10">
                      {dataset.type || "Detection"}
                    </Badge>
                  </div>

                  <h3 className="font-bold text-lg mb-1 text-white truncate">{dataset.name}</h3>
                  {dataset.description && (
                    <p className="text-sm text-gray-500 mb-4 line-clamp-2">{dataset.description}</p>
                  )}

                  {/* Stats */}
                  <div className="space-y-3">
                    <div className="flex items-center gap-4 text-sm">
                      <div className="flex items-center gap-1.5 text-gray-400">
                        <Image className="w-3.5 h-3.5" />
                        <span>{total} images</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-gray-400">
                        <Box className="w-3.5 h-3.5" />
                        <span>{dataset.classes?.length || 0} classes</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-emerald-400/80">
                        <Check className="w-3.5 h-3.5" />
                        <span>{dataset.stats?.reviewed_images || 0} reviewed</span>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div>
                      <div className="flex justify-between text-xs mb-1.5">
                        <span className="text-gray-500">Annotation Progress</span>
                        <span className={cn(
                          "font-mono",
                          progress === 100 ? "text-emerald-400" : progress > 0 ? "text-indigo-400" : "text-gray-600"
                        )}>{progress}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-500",
                            progress === 100 ? "bg-emerald-500" : "bg-indigo-500"
                          )}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>

                    {/* Class badges */}
                    {dataset.classes?.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {dataset.classes.slice(0, 4).map((cls, i) => (
                          <Badge key={i} variant="outline" className="text-[10px] h-5 border-white/10 bg-white/[0.03]">
                            {cls}
                          </Badge>
                        ))}
                        {dataset.classes.length > 4 && (
                          <Badge variant="outline" className="text-[10px] h-5 border-white/10 bg-white/[0.03]">
                            +{dataset.classes.length - 4}
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="p-4 bg-white/[0.02] border-t border-white/5 flex items-center gap-2">
                  <Button
                    onClick={() => router.push(`/project/${dataset.id}`)}
                    className="flex-1 bg-white text-black hover:bg-gray-200"
                    size="sm"
                  >
                    Open <ChevronRight className="ml-1" />
                  </Button>
                  <Button
                    variant="ghost" size="icon"
                    onClick={() => handleExport(dataset.id)}
                    className="text-gray-400 hover:text-white hover:bg-white/5 h-8 w-8"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    variant="ghost" size="icon"
                    onClick={() => handleDelete(dataset.id, dataset.name)}
                    className="text-gray-400 hover:text-red-400 hover:bg-red-400/10 h-8 w-8"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
