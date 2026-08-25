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
      title: "PROJECTS",
      value: liveStats.totalDatasets.toString(),
      sub: `${liveStats.totalImages} TOTAL_IMGS`,
      icon: Database,
      color: "text-blue-400 border-blue-500/30",
    },
    {
      title: "ANNOTATED",
      value: liveStats.totalAnnotated.toString(),
      sub: `${annotationPercent}% COMPLETE`,
      icon: Activity,
      color: "text-emerald-400 border-emerald-500/30",
    },
    {
      title: "REVIEWED",
      value: (liveStats.totalReviewed || 0).toString(),
      sub: "Q/A_PASSED",
      icon: Check,
      color: "text-indigo-400 border-indigo-500/30",
    },
    {
      title: "MODELS",
      value: liveStats.totalModels.toString(),
      sub: "IN_REGISTRY",
      icon: Cpu,
      color: "text-violet-400 border-violet-500/30",
    },
    {
      title: "PIPELINE",
      value: annotationPercent >= 80 ? "READY" : "BUILDING",
      sub: annotationPercent >= 80 ? "RDY_TO_TRAIN" : "NEED_LABELS",
      icon: TrendingUp,
      color: "text-amber-400 border-amber-500/30",
    }
  ];

  return (
    <div className="space-y-8 animate-fade-in font-sans">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {stats.map((stat, index) => (
          <Card key={index} className={cn("p-0 rounded-none border-white/20 bg-black", stat.color)}>
            <CardContent className="p-4 flex flex-col justify-between h-full group">
              <div className="flex justify-between items-start mb-4">
                <div className={cn("p-2 border bg-black group-hover:bg-white/5 transition-colors", stat.color)}>
                  <stat.icon className="w-4 h-4" />
                </div>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] font-mono font-bold uppercase tracking-widest">{stat.title}</p>
                <h3 className="text-2xl font-bold mt-1 text-white tracking-tight font-mono">{stat.value}</h3>
                <p className="text-[10px] text-gray-500 mt-1 font-mono uppercase">{stat.sub}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="rounded-none border-violet-500/30 bg-black p-0 hover:border-violet-500/60 transition-colors">
          <CardContent className="p-6 flex flex-col justify-between h-full">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 border border-violet-500/30 bg-violet-500/10 text-violet-400">
                  <Zap className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold uppercase tracking-widest text-white">QUICK_INFERENCE</h3>
              </div>
              <p className="text-gray-400 text-xs font-mono uppercase leading-relaxed mb-6">
                Drag & drop images to test your best model instantly. Supported formats: JPG, PNG, WEBP.
              </p>
            </div>
            <Button
              className="w-full bg-violet-500 hover:bg-violet-400 text-black border-0 shadow-none"
              onClick={() => onNavigate && onNavigate("inference")}
            >
              [ EXECUTE_DETECTION ]
              <ArrowRight className="ml-2 w-4 h-4" />
            </Button>
          </CardContent>
        </Card>

        <Card className="rounded-none border-white/20 bg-black p-0 hover:border-white/40 transition-colors">
          <CardContent className="p-6 flex flex-col justify-between h-full">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 border border-white/20 bg-white/5 text-gray-300">
                  <Cpu className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold uppercase tracking-widest text-white">NEW_TRAINING_JOB</h3>
              </div>
              <p className="text-gray-400 text-xs font-mono uppercase leading-relaxed mb-6">
                Configure a new training run on GPU cluster. Requires a prepared dataset version.
              </p>
            </div>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => onNavigate && onNavigate("datasets")}
            >
              [ INIT_DATASET ]
              <ArrowRight className="ml-2 w-4 h-4" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
