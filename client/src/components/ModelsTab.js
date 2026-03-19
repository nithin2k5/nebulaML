"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { toast } from 'sonner';
import {
  Database, Download, Trash2, RefreshCw,
  Box, Clock, HardDrive, Activity
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";

export default function ModelsTab() {
  const { token } = useAuth();
  const [models, setModels] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchModels = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(API_ENDPOINTS.MODELS.LIST, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await response.json();
      setModels(data.models || []);
    } catch (error) {
      console.error("Error fetching models:", error);
      setModels([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, []);

  const handleDownload = async (modelName) => {
    try {
      const response = await fetch(API_ENDPOINTS.MODELS.DOWNLOAD(modelName), {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${modelName}_best.pt`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success(`Downloading ${modelName}...`);
    } catch (error) {
      toast.error("Download failed. Backend may be unreachable.");
    }
  };

  const handleDelete = async (modelName) => {
    if (!confirm(`Delete model "${modelName}" permanently?`)) return;
    try {
      const response = await fetch(API_ENDPOINTS.MODELS.DELETE(modelName), { 
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (response.ok) {
        toast.success(`"${modelName}" deleted`);
        fetchModels();
      } else {
        toast.error("Delete failed");
      }
    } catch (error) {
      toast.error("Delete failed: " + error.message);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + ["B", "KB", "MB", "GB"][i];
  };

  return (
    <div className="space-y-8 animate-fade-in text-gray-100">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">Model Registry</h2>
          <p className="text-muted-foreground mt-1">Versioning and artifact management for your models.</p>
        </div>
        <Button
          onClick={fetchModels}
          disabled={isLoading}
          variant="outline"
          className="border-white/10 bg-white/5 hover:bg-white/10 text-white"
        >
          <RefreshCw className={`mr-2 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-52 rounded-2xl bg-white/5 animate-shimmer border border-white/5" />
          ))}
        </div>
      ) : models.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {models.map((model, index) => (
            <div
              key={index}
              className="group relative rounded-2xl bg-card/40 backdrop-blur-md border border-white/5 hover:border-indigo-500/30 hover:bg-white/5 transition-all duration-300 flex flex-col overflow-hidden shadow-lg"
            >
              <div className="p-6 flex-1">
                <div className="flex items-start justify-between mb-6">
                  <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500/20 group-hover:scale-110 transition-all duration-300">
                    <Box className="text-2xl" />
                  </div>
                  <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20">
                    Ready
                  </Badge>
                </div>

                <h3 className="font-bold text-lg mb-1 text-white truncate" title={model.name}>{model.name}</h3>
                <p className="text-sm text-gray-500 font-mono mb-6">v8.0.0 • PyTorch</p>

                <div className="space-y-3 text-sm text-gray-400">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <HardDrive className="text-gray-500" />
                      <span>Size</span>
                    </div>
                    <span className="text-gray-200 font-medium">{formatFileSize(model.size)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Clock className="text-gray-500" />
                      <span>Created</span>
                    </div>
                    <span className="text-gray-200">{new Date(model.created * 1000).toLocaleDateString()}</span>
                  </div>
                  {model.metrics && (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Activity className="text-gray-500" />
                        <span>mAP@50</span>
                      </div>
                      <span className="text-emerald-400 font-mono">{Number(model.metrics?.mAP50 || 0).toFixed(3)}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="p-4 bg-white/[0.02] border-t border-white/5 flex items-center gap-3">
                <Button
                  onClick={() => handleDownload(model.name)}
                  className="flex-1 bg-white text-black hover:bg-gray-200"
                  size="sm"
                >
                  <Download className="mr-2" /> Download
                </Button>
                <Button
                  onClick={() => handleDelete(model.name)}
                  variant="ghost"
                  size="icon"
                  className="text-gray-400 hover:text-red-400 hover:bg-red-400/10 h-8 w-8"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="py-20 text-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02]">
          <div className="w-16 h-16 rounded-full bg-indigo-500/10 flex items-center justify-center mx-auto mb-4 text-indigo-400">
            <Database className="text-3xl" />
          </div>
          <h3 className="text-xl font-bold mb-2">Registry Empty</h3>
          <p className="text-muted-foreground">Train your first model to see artifacts here.</p>
        </div>
      )}
    </div>
  );
}
