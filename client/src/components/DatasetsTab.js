"use client";

import { useAuth } from "@/context/AuthContext";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  const exportIntervalsRef = useRef([]);
  const [showCreate, setShowCreate] = useState(false);
  const router = useRouter();
  const { token } = useAuth();

  useEffect(() => {
    if (token) fetchDatasets();
  }, [token]);

  useEffect(() => {
    return () => {
      exportIntervalsRef.current.forEach(clearInterval);
    };
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
        // Mark first project for onboarding wizard
        if (typeof window !== "undefined" && !localStorage.getItem("nebula_first_project")) {
          localStorage.setItem("nebula_first_project", "1");
        }
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
      const response = await fetch(API_ENDPOINTS.DATASETS.EXPORT(id), {
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
            const statusRes = await fetch(API_ENDPOINTS.DATASETS.EXPORT_STATUS(id, data.job_id), {
              headers: { "Authorization": `Bearer ${token}` }
            });
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              if (statusData.status === "completed") {
                clearInterval(interval);
                exportIntervalsRef.current = exportIntervalsRef.current.filter(i => i !== interval);
                toast.success("Export ready! Downloading...", { id: toastId });
                downloadDataset(id);
              } else if (statusData.status === "failed") {
                clearInterval(interval);
                exportIntervalsRef.current = exportIntervalsRef.current.filter(i => i !== interval);
                toast.error("Export failed: " + statusData.error, { id: toastId });
              } else {
                toast.loading('Preparing export...', { description: `${statusData.progress || 0}%`, id: toastId });
              }
            }
          } catch (err) {
            console.error("Polling error:", err);
          }
        }, 1000);
        exportIntervalsRef.current.push(interval);
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
      const downloadResponse = await fetch(API_ENDPOINTS.ANNOTATIONS.DOWNLOAD(id), {
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
    <div className="space-y-8 animate-fade-in text-white font-sans">
      <div className="flex items-center justify-between border-b border-white/20 pb-6">
        <div>
          <h2 className="text-xl font-bold tracking-widest uppercase text-white">PROJECTS_DB</h2>
          <p className="text-xs font-mono text-gray-500 uppercase mt-1">Manage and annotate object detection schemas.</p>
        </div>
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 w-4 h-4" /> [ ALLOCATE_PROJECT ]
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>INIT_PROJECT_SCHEMA</DialogTitle>
              <DialogDescription>Define your dataset matrix and object classifications.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label className="text-[10px] font-mono text-violet-400">SCHEMA_NAME</Label>
                <Input
                  placeholder="e.g., TRAFFIC_SIGNS_V1"
                  value={newDataset.name}
                  onChange={e => setNewDataset({ ...newDataset, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] font-mono text-violet-400">META_DESCRIPTION <span className="text-gray-600">[OPTIONAL]</span></Label>
                <Input
                  placeholder="System description..."
                  value={newDataset.description}
                  onChange={e => setNewDataset({ ...newDataset, description: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] font-mono text-violet-400">CLASS_VECTORS <span className="text-gray-600">[COMMA_SEPARATED]</span></Label>
                <Input
                  placeholder="stop, yield, limit"
                  value={newDataset.classes}
                  onChange={e => setNewDataset({ ...newDataset, classes: e.target.value })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowCreate(false)}>[ ABORT ]</Button>
              <Button onClick={handleCreateDataset}>[ EXECUTE_INIT ]</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <Card key={i} className="h-48 rounded-none bg-white/5 animate-pulse border border-white/10" />
          ))}
        </div>
      ) : datasets.length === 0 ? (
        <Card className="py-20 text-center rounded-none border border-white/20 bg-black max-w-2xl mx-auto">
          <CardContent className="flex flex-col items-center justify-center pt-6">
            <div className="w-16 h-16 border border-violet-500/30 bg-violet-500/10 flex items-center justify-center mb-6 text-violet-400">
              <Folder className="w-8 h-8" />
            </div>
            <h3 className="text-lg font-bold mb-3 uppercase tracking-widest text-white">DB_EMPTY // NO_PROJECTS_FOUND</h3>
            <p className="text-xs font-mono text-gray-500 mb-8 max-w-md mx-auto uppercase">
              No datasets allocated. Initialize a new project schema to commence ML pipeline.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left max-w-xl mx-auto mb-10 w-full">
              <div className="p-4 bg-black border border-white/20">
                <div className="text-xs font-mono font-bold text-violet-400 mb-2">SEQ_01</div>
                <h4 className="font-bold text-xs uppercase mb-1">ALLOCATE</h4>
                <p className="text-[10px] font-mono text-gray-500 uppercase">Define classes & metadata</p>
              </div>
              <div className="p-4 bg-black border border-white/20 opacity-70">
                <div className="text-xs font-mono font-bold text-emerald-400 mb-2">SEQ_02</div>
                <h4 className="font-bold text-xs uppercase mb-1">INGEST</h4>
                <p className="text-[10px] font-mono text-gray-500 uppercase">Upload imagery & labels</p>
              </div>
              <div className="p-4 bg-black border border-white/20 opacity-70">
                <div className="text-xs font-mono font-bold text-amber-400 mb-2">SEQ_03</div>
                <h4 className="font-bold text-xs uppercase mb-1">TRAIN</h4>
                <p className="text-[10px] font-mono text-gray-500 uppercase">Execute YOLO training</p>
              </div>
            </div>

            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-2 w-4 h-4" /> [ INIT_FIRST_PROJECT ]
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {datasets?.map((dataset, dsIdx) => {
            const total = dataset.stats?.total_images || 0;
            const annotated = dataset.stats?.annotated_images || 0;
            const progress = total > 0 ? Math.round((annotated / total) * 100) : 0;

            return (
              <Card
                key={dataset.id || `ds-${dsIdx}`}
                className="group relative rounded-none bg-black border border-white/20 hover:border-violet-500/50 transition-colors flex flex-col h-full"
              >
                <CardContent className="p-6 flex flex-col h-full z-10 pt-8">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-4 gap-3">
                    <div className="flex items-center gap-4 w-full overflow-hidden">
                      <div className="w-10 h-10 border border-violet-500/30 bg-violet-500/10 flex items-center justify-center text-violet-400 transition-colors group-hover:bg-violet-500 group-hover:text-black">
                        <FolderKanban className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-sm text-white uppercase tracking-widest truncate" title={dataset.name}>{dataset.name}</h3>
                        {dataset.description ? (
                          <p className="text-[10px] font-mono text-gray-500 uppercase truncate mt-0.5" title={dataset.description}>{dataset.description}</p>
                        ) : (
                          <p className="text-[10px] font-mono text-gray-600 uppercase mt-0.5">NO_META</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-3 gap-0 my-4 border border-white/10 bg-black/50">
                    <div className="flex flex-col items-center justify-center p-3 border-r border-white/10">
                      <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-500 uppercase mb-1">
                        <span>IMGS</span>
                      </div>
                      <span className="text-sm font-bold font-mono text-white">{total}</span>
                    </div>
                    <div className="flex flex-col items-center justify-center p-3 border-r border-white/10">
                      <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-500 uppercase mb-1">
                        <span>CLS</span>
                      </div>
                      <span className="text-sm font-bold font-mono text-white">{dataset.classes?.length || 0}</span>
                    </div>
                    <div className="flex flex-col items-center justify-center p-3">
                      <div className="flex items-center gap-1.5 text-[10px] font-mono text-emerald-500/70 uppercase mb-1">
                        <span>REV</span>
                      </div>
                      <span className="text-sm font-bold font-mono text-emerald-400">{dataset.stats?.reviewed_images || 0}</span>
                    </div>
                  </div>

                  {/* Progress & Classes */}
                  <div className="mt-auto space-y-4 pt-2">
                    {/* Class badges */}
                    {dataset.classes?.length > 0 ? (
                      <div className="flex flex-wrap gap-2 min-h-[24px]">
                        {dataset.classes.slice(0, 3).map((cls, i) => (
                          <Badge key={i} variant="secondary">
                            {cls}
                          </Badge>
                        ))}
                        {dataset.classes.length > 3 && (
                          <Badge variant="outline">
                            +{dataset.classes.length - 3}
                          </Badge>
                        )}
                      </div>
                    ) : (
                      <div className="h-[24px]" />
                    )}

                    {/* Progress Bar */}
                    <div className="bg-black border border-white/10 p-2">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-[10px] font-mono font-bold text-gray-500 uppercase tracking-widest">ANN_PROGRESS</span>
                        <span className={cn(
                          "text-[10px] font-mono font-bold uppercase",
                          progress === 100 ? "text-emerald-400" : progress > 0 ? "text-violet-400" : "text-gray-500"
                        )}>{progress}%</span>
                      </div>
                      <div className="h-1 bg-white/10 w-full overflow-hidden">
                        <div
                          className={cn(
                            "h-full transition-all duration-1000 ease-out",
                            progress === 100 ? "bg-emerald-500" : "bg-violet-500"
                          )}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </CardContent>

                {/* Actions */}
                <div className="px-4 py-3 bg-black border-t border-white/10 flex items-center gap-2 relative z-10">
                  <Button
                    onClick={() => router.push(`/project/${dataset.id}`)}
                    className="flex-1"
                  >
                    [ ACCESS_DB ] <ChevronRight className="ml-1 w-4 h-4" />
                  </Button>
                  <div className="flex gap-2">
                    <Button
                      variant="outline" size="icon"
                      onClick={() => handleExport(dataset.id)}
                      title="EXPORT"
                    >
                      <Download className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="destructive" size="icon"
                      onClick={() => handleDelete(dataset.id, dataset.name)}
                      title="DELETE"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
