"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  CheckCircle,
  Upload as UploadIcon,
  Edit,
  Download,
  Play,
  Box,
  Layers,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { API_ENDPOINTS } from "@/lib/config";
import { cn, formatMetricValue } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function DatasetWorkflow({ dataset, onRefresh }) {
  const { token } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState(null);
  const [trainingJobs, setTrainingJobs] = useState([]);
  const [showTrainDialog, setShowTrainDialog] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [trainingConfig, setTrainingConfig] = useState({
    epochs: 100,
    batch_size: 16,
    img_size: 640,
    model_name: "yolov8n.pt",
    learning_rate: 0.01
  });

  const fetchDatasetStats = async () => {
    try {
      if (!token) return;
      const response = await fetch(API_ENDPOINTS.DATASETS.STATS(dataset.id), {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (!response.ok) return;
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  };

  const fetchTrainingJobs = async () => {
    try {
      if (!token) return;
      const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (!res.ok) return;
      const data = await res.json();
      setTrainingJobs((data.jobs || []).filter(j => j.dataset_id === dataset.id));
    } catch (e) {
      console.error("Error fetching training jobs:", e);
    }
  };

  useEffect(() => {
    if (dataset && token) {
      fetchDatasetStats();
      fetchTrainingJobs();
    }
  }, [dataset?.id, token]);

  // Poll stats every 5s and training jobs every 8s
  useEffect(() => {
    if (!dataset || !token) return;
    const statsInterval = setInterval(fetchDatasetStats, 5000);
    const jobsInterval  = setInterval(fetchTrainingJobs, 8000);
    return () => {
      clearInterval(statsInterval);
      clearInterval(jobsInterval);
    };
  }, [dataset?.id, token]);

  const steps = [
    { number: 1, id: "create",   title: "Initialize", description: "Dataset setup",    icon: Layers },
    { number: 2, id: "upload",   title: "Upload",     description: "Add images",       icon: UploadIcon },
    { number: 3, id: "annotate", title: "Annotate",   description: "Label objects",    icon: Edit },
    { number: 4, id: "train",    title: "Train",      description: "Start Model",      icon: Play },
  ];

  const runningJobs   = trainingJobs.filter(j => j.status === "running");
  const completedJobs = trainingJobs.filter(j => j.status === "completed" || j.status === "success");
  const failedJobs    = trainingJobs.filter(j => j.status === "failed");
  const isTraining    = runningJobs.length > 0;
  const hasModels     = completedJobs.length > 0;

  const getStepStatus = (stepNumber) => {
    if (stepNumber === 1) return "complete";

    if (stepNumber === 2) {
      if (dataset?.images?.length > 0) return "complete";
      return "current";
    }

    if (stepNumber === 3) {
      if (dataset?.images?.length === 0) return "pending";
      if (stats?.annotated_images === stats?.total_images && stats?.total_images > 0) return "complete";
      return "current";
    }

    if (stepNumber === 4) {
      if (isTraining) return "running";
      if (hasModels) return "complete";
      if (failedJobs.length > 0) return "failed";
      if (stats?.annotated_images === stats?.total_images && stats?.total_images > 0) return "current";
      return "pending";
    }

    return "pending";
  };

  const currentStepIndex = steps.findIndex(s => {
    const st = getStepStatus(s.number);
    return st === "current" || st === "running";
  });
  const progressPercent = Math.max(5, (Math.max(0, currentStepIndex) / (steps.length - 1)) * 100);

  const handleDragOver = useCallback((e) => { e.preventDefault(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback((e) => { e.preventDefault(); setIsDragging(false); }, []);
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
        headers: { "Authorization": `Bearer ${token}` },
        body: formData,
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      if (data.success) {
        toast.success(`${files.length} image${files.length > 1 ? 's' : ''} uploaded`);
        if (onRefresh) onRefresh();
        fetchDatasetStats();
      } else {
        throw new Error(data.detail || "Upload failed");
      }
    } catch (error) {
      console.error("Upload error:", error);
      toast.error(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  const renderTrainStepContent = () => {
    const status = getStepStatus(4);

    if (status === "running") {
      const job = runningJobs[0];
      return (
        <div className="mt-6 space-y-4 animate-in fade-in duration-300">
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-amber-400 font-semibold">
                <Loader2 className="animate-spin w-4 h-4" />
                Training in Progress
              </div>
              <Badge variant="outline" className="border-amber-500/40 text-amber-400 text-xs">
                {Math.round(job?.progress || 0)}%
              </Badge>
            </div>
            <Progress value={Math.max(5, job?.progress || 0)} className="h-2 bg-amber-500/10 [&>div]:bg-amber-500" />
            {job?.current_epoch != null && job?.config?.epochs != null && (
              <p className="text-xs text-muted-foreground">
                Epoch {job.current_epoch} / {job.config.epochs}
                {job.config?.model_name && ` · ${job.config.model_name}`}
              </p>
            )}
            {job?.metrics && Object.entries(job.metrics).length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {Object.entries(job.metrics).slice(0, 4).map(([k, v]) => (
                  <span key={k} className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border font-mono">
                    {k}: {formatMetricValue(v)}
                  </span>
                ))}
              </div>
            )}
            <Button
              size="sm"
              variant="outline"
              className="w-full mt-1 border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
              onClick={() => router.push(`/project/${dataset.id}?tab=versions`)}
            >
              View Live Progress
            </Button>
          </div>
        </div>
      );
    }

    if (status === "complete") {
      return (
        <div className="mt-6 space-y-4 animate-in fade-in duration-300">
          <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-5 space-y-3">
            <div className="flex items-center gap-2 text-green-400 font-semibold">
              <CheckCircle className="w-4 h-4" />
              {completedJobs.length} Trained Model{completedJobs.length > 1 ? 's' : ''} Ready
            </div>
            {completedJobs[0]?.metrics && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(completedJobs[0].metrics).slice(0, 4).map(([k, v]) => (
                  <span key={k} className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border font-mono">
                    {k}: {formatMetricValue(v)}
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-2 pt-1">
              <Button size="sm" variant="outline" className="flex-1"
                onClick={() => router.push(`/project/${dataset.id}?tab=versions`)}>
                View Registry
              </Button>
              <Button size="sm" className="flex-1"
                onClick={() => router.push(`/project/${dataset.id}?tab=deploy`)}>
                Deploy Model
              </Button>
            </div>
          </div>
        </div>
      );
    }

    if (status === "failed") {
      return (
        <div className="mt-6 animate-in fade-in duration-300">
          <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-5 space-y-3">
            <div className="flex items-center gap-2 text-red-400 font-semibold">
              <AlertCircle className="w-4 h-4" />
              Last training failed
            </div>
            {failedJobs[0]?.error && (
              <p className="text-xs text-muted-foreground font-mono truncate">{failedJobs[0].error}</p>
            )}
          </div>
          {renderStartTrainingUI()}
        </div>
      );
    }

    if (status === "current") {
      return renderStartTrainingUI();
    }

    return null;
  };

  const renderStartTrainingUI = () => (
    <div className="mt-6 flex flex-col sm:flex-row gap-4 justify-center animate-in fade-in zoom-in duration-300">
      <Button
        variant="outline"
        size="lg"
        className="h-auto py-6 px-8 flex flex-col gap-2 hover:bg-muted/50 border-2"
        onClick={async () => {
          try {
            const res = await fetch(API_ENDPOINTS.DATASETS.EXPORT(dataset.id), {
              method: "POST",
              headers: { "Authorization": `Bearer ${token}` }
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            if (data.success) {
              toast.success("Dataset exported successfully!");
              if (onRefresh) onRefresh();
            } else throw new Error(data.detail);
          } catch (e) { toast.error(`Export failed: ${e.message}`); }
        }}
      >
        <Download className="text-3xl mb-1 text-muted-foreground" />
        <span className="font-semibold">Export Dataset</span>
        <span className="text-xs font-normal text-muted-foreground">Download format zip</span>
      </Button>

      <Dialog open={showTrainDialog} onOpenChange={setShowTrainDialog}>
        <DialogTrigger asChild>
          <Button
            size="lg"
            className="h-auto py-6 px-8 flex flex-col gap-2 bg-gradient-to-br from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white shadow-xl shadow-green-500/20 border-0"
          >
            <Play className="text-3xl mb-1 text-white/90" />
            <span className="font-semibold text-lg">Start Training</span>
            <span className="text-xs font-normal text-white/80">Configure and train your model</span>
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Train Configuration</DialogTitle>
            <DialogDescription>Setup your training parameters</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Epochs</Label>
                <Input
                  type="number"
                  value={trainingConfig.epochs}
                  onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1) setTrainingConfig({ ...trainingConfig, epochs: v }); }}
                />
              </div>
              <div className="space-y-2">
                <Label>Batch Size</Label>
                <Input
                  type="number"
                  value={trainingConfig.batch_size}
                  onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1) setTrainingConfig({ ...trainingConfig, batch_size: v }); }}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Model Size</Label>
              <Select
                value={trainingConfig.model_name}
                onValueChange={v => setTrainingConfig({ ...trainingConfig, model_name: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="yolov8n.pt">Nano (Fastest)</SelectItem>
                  <SelectItem value="yolov8s.pt">Small</SelectItem>
                  <SelectItem value="yolov8m.pt">Medium</SelectItem>
                  <SelectItem value="yolov8l.pt">Large</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button
            className="w-full bg-green-600 hover:bg-green-700 text-white"
            onClick={async () => {
              try {
                const res = await fetch(API_ENDPOINTS.TRAINING.EXPORT_AND_TRAIN, {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                  },
                  body: JSON.stringify({
                    dataset_id: dataset.id,
                    config: { ...trainingConfig, strict_epochs: true }
                  })
                });
                if (!res.ok) throw new Error(await res.text());
                const data = await res.json();
                if (data.success) {
                  setShowTrainDialog(false);
                  toast.success("Training started! Monitoring progress...");
                  fetchTrainingJobs();
                  router.push(`/project/${dataset.id}?tab=versions`);
                } else throw new Error(data.detail);
              } catch (e) { toast.error(`Failed to start training: ${e.message}`); }
            }}
          >
            Start Training
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );

  const renderStepContent = (step) => {
    const status = getStepStatus(step.number);

    if (step.number === 2 && (status === "current" || status === "complete")) {
      return (
        <div className="mt-6 animate-in fade-in zoom-in duration-300">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "group relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-all",
              isDragging
                ? "border-primary bg-primary/5 scale-[1.01]"
                : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30"
            )}
          >
            <div className="rounded-full bg-background p-4 shadow-sm ring-1 ring-inset ring-gray-900/5 mb-4 group-hover:scale-110 transition-transform">
              <UploadIcon className={cn("text-2xl transition-colors", isDragging ? "text-primary" : "text-muted-foreground")} />
            </div>

            <div className="space-y-1 mb-4">
              <p className="font-medium text-foreground">
                {uploading ? "Uploading files..." : "Drop images here to upload"}
              </p>
              <p className="text-sm text-muted-foreground">
                Support for JPG, PNG, WEBP
              </p>
            </div>

            <Button
              variant="secondary"
              size="sm"
              disabled={uploading}
              className="relative"
              onClick={() => document.getElementById("file-upload").click()}
            >
              {uploading ? <><Loader2 className="w-3 h-3 mr-2 animate-spin" />Uploading...</> : "Select Files"}
            </Button>
            <input
              id="file-upload"
              type="file"
              multiple
              accept="image/*"
              className="hidden"
              onChange={(e) => e.target.files.length > 0 && uploadFiles(Array.from(e.target.files))}
            />
          </div>

          {dataset?.images?.length > 0 && (
            <div className="mt-4 flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-500/10 px-3 py-2 rounded-md border border-green-100 dark:border-green-500/20">
              <CheckCircle className="w-4 h-4" />
              <span>{dataset.images.length} images uploaded successfully</span>
            </div>
          )}
        </div>
      );
    }

    if (step.number === 3 && (status === "current" || status === "complete")) {
      return (
        <div className="mt-6 space-y-4 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Card className="border-muted bg-muted/30">
              <CardContent className="p-4 flex flex-col items-center justify-center text-center">
                <span className="text-3xl font-bold text-foreground">{stats?.total_images || 0}</span>
                <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Total Images</span>
              </CardContent>
            </Card>
            <Card className={cn("border-muted", stats?.completion_percentage === 100 ? "bg-green-500/10 border-green-200" : "bg-muted/30")}>
              <CardContent className="p-4 flex flex-col items-center justify-center text-center">
                <span className={cn("text-3xl font-bold", stats?.completion_percentage === 100 ? "text-green-600" : "text-primary")}>
                  {stats?.annotated_images || 0}
                </span>
                <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Annotated</span>
              </CardContent>
            </Card>
            <Card className="border-muted bg-muted/30 sm:col-span-2 lg:col-span-1">
              <CardContent className="p-4 flex flex-col items-center justify-center text-center">
                <span className="text-3xl font-bold text-foreground">{stats?.completion_percentage?.toFixed(0) || 0}%</span>
                <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Completion</span>
              </CardContent>
            </Card>
          </div>

          <div className="flex justify-center pt-2">
            <Button
              size="lg"
              onClick={() => router.push(`/annotate?dataset=${dataset.id}`)}
              className="w-full sm:w-auto min-w-[200px] shadow-lg shadow-primary/20 transition-all hover:scale-105"
            >
              <Edit className="mr-2" />
              {status === "complete" ? "Review Annotations" : "Start Annotating"}
            </Button>
          </div>
        </div>
      );
    }

    if (step.number === 4) return renderTrainStepContent();

    return null;
  };

  return (
    <Card className="border-none shadow-none bg-transparent">
      <CardHeader className="px-0 pt-0 pb-8">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-2xl font-bold tracking-tight">Dataset Pipeline</CardTitle>
            <CardDescription className="text-base mt-1">Manage your dataset lifecycle from upload to training</CardDescription>
          </div>
          {stats && (
            <Badge variant="outline" className="px-3 py-1 border-muted-foreground/20 text-muted-foreground">
              {dataset?.classes?.length || 0} Classes
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="px-0">
        <div className="relative mb-12">
          <div className="absolute top-1/2 left-0 w-full h-0.5 bg-muted -translate-y-1/2 z-0 hidden md:block">
            <div
              className="h-full bg-primary transition-all duration-500 ease-in-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          <div className="relative z-10 grid grid-cols-1 md:grid-cols-5 gap-6 md:gap-0">
            {steps.map((step) => {
              const status = getStepStatus(step.number);
              const isComplete = status === "complete";
              const isCurrent  = status === "current" || status === "running";
              const isFailed   = status === "failed";

              return (
                <div key={step.id} className="flex flex-row md:flex-col items-center gap-4 md:gap-3 text-left md:text-center group">
                  <div
                    className={cn(
                      "w-10 h-10 md:w-12 md:h-12 rounded-full flex items-center justify-center border-2 transition-all duration-300 shadow-sm",
                      isComplete ? "bg-primary border-primary text-primary-foreground" :
                        isFailed  ? "bg-red-500/10 border-red-500 text-red-500" :
                        isCurrent ? "bg-background border-primary text-primary scale-110 ring-4 ring-primary/10" :
                                    "bg-muted border-transparent text-muted-foreground"
                    )}
                  >
                    {isComplete ? <CheckCircle className="text-xl" /> :
                     isFailed   ? <AlertCircle className="text-lg" /> :
                     status === "running" ? <Loader2 className="text-lg animate-spin" /> :
                                  <step.icon className="text-lg" />}
                  </div>
                  <div className="flex-1 md:flex-none">
                    <p className={cn("text-sm font-semibold transition-colors",
                      isCurrent ? "text-foreground" : isFailed ? "text-red-500" : "text-muted-foreground")}>
                      {step.title}
                    </p>
                    <p className="text-xs text-muted-foreground hidden md:block">{step.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="min-h-[300px] border rounded-xl p-8 bg-card/50 backdrop-blur-sm shadow-sm relative overflow-hidden">
          {steps.map(step => {
            const status = getStepStatus(step.number);
            const showContent =
              status === "current" || status === "running" || status === "failed" ||
              (step.number === 3 && status === "complete" && getStepStatus(4) === "pending");

            if (!showContent) return null;
            return (
              <div key={step.id} className="animate-in fade-in duration-500">
                <div className="mb-6 pb-6 border-b border-border/50">
                  <h3 className="text-xl font-semibold flex items-center gap-2">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold">
                      {step.number}
                    </span>
                    {step.title} Stage
                  </h3>
                  <p className="text-muted-foreground ml-8 mt-1">{step.description}</p>
                </div>
                {renderStepContent(step)}
              </div>
            );
          })}

          {getStepStatus(4) === "complete" && (
            <div className="animate-in fade-in duration-500">
              <div className="mb-6 pb-6 border-b border-border/50">
                <h3 className="text-xl font-semibold flex items-center gap-2">
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-green-500/20 text-green-500 text-xs font-bold">4</span>
                  Train Stage
                </h3>
              </div>
              {renderTrainStepContent()}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
