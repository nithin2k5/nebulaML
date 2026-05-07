"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Zap, Cpu, Database, TrendingUp, Activity, Clock, Check, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { API_ENDPOINTS } from "@/lib/config";

import { useAuth } from "@/context/AuthContext";

export default function DashboardStats({ onNavigate }) {
  const { token } = useAuth();
  const [liveStats, setLiveStats] = useState({
    totalDatasets: 0,
    totalImages: 0,
    totalAnnotated: 0,
    totalModels: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLiveStats();
    const interval = setInterval(fetchLiveStats, 15000);
    return () => clearInterval(interval);
  }, []);

  const fetchLiveStats = async () => {
    try {
      const headers = { "Authorization": `Bearer ${token}` };
      const [summaryRes, modelsRes] = await Promise.allSettled([
        fetch(API_ENDPOINTS.DATASETS.SUMMARY, { headers }),
        fetch(`${API_ENDPOINTS.MODELS.LIST}`, { headers }),
      ]);

      let totalDatasets = 0, totalImages = 0, totalAnnotated = 0, totalReviewed = 0;
      if (summaryRes.status === 'fulfilled' && summaryRes.value.ok) {
        const summaryData = await summaryRes.value.json();
        totalDatasets = summaryData.total_datasets || 0;
        totalImages = summaryData.total_images || 0;
        totalAnnotated = summaryData.annotated_images || 0;
        totalReviewed = summaryData.reviewed_images || 0;
      }

      let totalModels = 0;
      if (modelsRes.status === 'fulfilled' && modelsRes.value.ok) {
        const modelsData = await modelsRes.value.json();
        totalModels = modelsData.models?.length || 0;
      }

      setLiveStats({ totalDatasets, totalImages, totalAnnotated, totalModels, totalReviewed });
    } catch (e) {
      console.error("Stats fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  const annotationPercent = liveStats.totalImages > 0
    ? Math.round((liveStats.totalAnnotated / liveStats.totalImages) * 100) : 0;

  const stats = [
    {
      title: "Datasets",
      value: liveStats.totalDatasets.toString(),
      sub: `${liveStats.totalImages} images total`,
      icon: Database,
      color: "text-blue-400 bg-blue-400/10",
    },
    {
      title: "Annotated",
      value: liveStats.totalAnnotated.toString(),
      sub: `${annotationPercent}% complete`,
      icon: Activity,
      color: "text-emerald-400 bg-emerald-400/10",
    },
    {
      title: "Reviewed",
      value: (liveStats.totalReviewed || 0).toString(),
      sub: "Quality checked",
      icon: Check,
      color: "text-indigo-400 bg-indigo-400/10",
    },
    {
      title: "Models",
      value: liveStats.totalModels.toString(),
      sub: "In registry",
      icon: Cpu,
      color: "text-purple-400 bg-purple-400/10",
    },
    {
      title: "Pipeline",
      value: annotationPercent >= 80 ? "Ready" : "Building",
      sub: annotationPercent >= 80 ? "Ready to train" : "Need more labels",
      icon: TrendingUp,
      color: "text-amber-400 bg-amber-400/10",
    }
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6">
        {stats.map((stat, index) => (
          <div
            key={index}
            className={cn(
              "group relative p-6 rounded-2xl bg-card/40 backdrop-blur-md border border-white/5",
              "hover:bg-white/5 transition-all duration-300 hover:-translate-y-1 shadow-lg shadow-black/10",
              loading && "animate-shimmer"
            )}
          >
            <div className="flex justify-between items-start mb-4">
              <div className={cn("p-3 rounded-xl", stat.color)}>
                <stat.icon className="text-xl" />
              </div>
            </div>
            <div>
              <p className="text-muted-foreground text-sm font-medium">{stat.title}</p>
              <h3 className="text-3xl font-bold mt-1 text-white tracking-tight">{stat.value}</h3>
              <p className="text-xs text-muted-foreground mt-1">{stat.sub}</p>
            </div>
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="p-[1px] rounded-2xl bg-gradient-to-br from-indigo-500/20 via-transparent to-transparent">
          <div className="h-full rounded-2xl bg-card/60 backdrop-blur-md border border-white/5 p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400">
                  <Zap />
                </div>
                <h3 className="text-lg font-bold">Quick Inference</h3>
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed mb-6">
                Drag & drop images to test your best model instantly. Supported formats: JPG, PNG, WEBP.
              </p>
            </div>
            <Button
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white border-0 shadow-lg shadow-indigo-500/20"
              onClick={() => onNavigate && onNavigate("inference")}
            >
              Start Detection
              <ArrowRight className="ml-2" />
            </Button>
          </div>
        </div>

        <div className="p-[1px] rounded-2xl bg-gradient-to-br from-purple-500/20 via-transparent to-transparent">
          <div className="h-full rounded-2xl bg-card/60 backdrop-blur-md border border-white/5 p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-purple-500/20 rounded-lg text-purple-400">
                  <Cpu />
                </div>
                <h3 className="text-lg font-bold">Start New Training</h3>
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed mb-6">
                Configure a new training run on your GPU. Requires a prepared dataset version.
              </p>
            </div>
            <Button
              variant="outline"
              className="w-full border-white/10 hover:bg-white/5 bg-transparent"
              onClick={() => onNavigate && onNavigate("datasets")}
            >
              Create Dataset
              <ArrowRight className="ml-2" />
            </Button>
          </div>
        </div>
      </div>

      {/* Recent Activity Table -> Removed per user request */}
    </div>
  );
}
