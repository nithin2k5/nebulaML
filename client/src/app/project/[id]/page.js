"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_ENDPOINTS } from "@/lib/config";
import { usePolling } from "@/lib/usePolling";
import { deriveStates } from "@/lib/pipeline";
import { ArrowLeft, Cpu, CheckCircle, X } from "lucide-react";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

// Components for each tab
import NextStepRail from "@/components/NextStepRail";
import ProjectOverview from "@/components/project/ProjectOverview";
import ProjectUpload from "@/components/project/ProjectUpload";
import ProjectImages from "@/components/project/ProjectImages";
import ProjectAnnotate from "@/components/project/ProjectAnnotate";
import ProjectGenerate from "@/components/project/ProjectGenerate";
import ProjectTrain from "@/components/project/ProjectTrain";
import ProjectVersions from "@/components/project/ProjectVersions";
import ProjectTest from "@/components/project/ProjectTest";
import ProjectDeploy from "@/components/project/ProjectDeploy";
import ProjectHealth from "@/components/project/ProjectHealth";
import ProjectEvaluate from "@/components/project/ProjectEvaluate";
import ProjectActiveLearning from "@/components/project/ProjectActiveLearning";
import ProjectMonitoring from "@/components/project/ProjectMonitoring";
import ProjectTeam from "@/components/project/ProjectTeam";

export default function ProjectPage() {
    const params = useParams();
    const searchParams = useSearchParams();
    const router = useRouter();
    const [dataset, setDataset] = useState(null);
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState(null);
    const [trainingJobs, setTrainingJobs] = useState([]);
    const [monitoringTotal, setMonitoringTotal] = useState(0);
    const [evaluationRuns, setEvaluationRuns] = useState([]);
    const [versionCount, setVersionCount] = useState(0);
    const [versionRefreshKey, setVersionRefreshKey] = useState(0);
    const [activeTab, setActiveTab] = useState(searchParams.get('tab') || "overview");
    const [completionBanner, setCompletionBanner] = useState(null);
    const prevRunningCountRef = useRef(null);
    const { token, loading: authLoading } = useAuth();

    // Update URL when tab changes
    const handleTabChange = (val) => {
        setActiveTab(val);
        router.push(`/project/${params.id}?tab=${val}`, { scroll: false });
    };

    // Update tab if URL changes (external navigation)
    useEffect(() => {
        const tab = searchParams.get('tab');
        if (tab && tab !== activeTab) {
            setActiveTab(tab);
        }
    }, [searchParams]);

    useEffect(() => {
        if (params?.id && !authLoading) {
            if (token) {
                fetchDataset(params.id);
                fetchStats(params.id);
                fetchTrainingJobs(params.id);
                fetchMonitoringStats(params.id);
                fetchVersionCount(params.id);
                fetchEvaluationRuns(params.id);
            } else {
                setLoading(false);
            }
        }
    }, [params?.id, token, authLoading]);

    const fetchDataset = async (id) => {
        try {
            const res = await fetch(API_ENDPOINTS.DATASETS.GET(id), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (!res.ok) throw new Error("Dataset not found");
            const data = await res.json();
            setDataset(data);
        } catch (error) {
            console.error(error);
            toast.error("Failed to load project: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    const fetchStats = async (id) => {
        try {
            const res = await fetch(API_ENDPOINTS.DATASETS.STATS(id), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) setStats(await res.json());
        } catch (e) { console.error(e); }
    };

    const fetchTrainingJobs = async (datasetId) => {
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.JOBS, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                const jobs = (data.jobs || []).filter(j => j.dataset_id === datasetId);
                setTrainingJobs(jobs);

                // Detect transition: running → completed
                const running = jobs.filter(j => j.status === "running" || j.status === "pending");
                const completed = jobs.filter(j => j.status === "completed" || j.status === "success");
                if (prevRunningCountRef.current !== null && prevRunningCountRef.current > 0 && running.length === 0 && completed.length > 0) {
                    const latest = completed[0];
                    const mAP = latest?.results?.metrics?.["metrics/mAP50(B)"] ?? latest?.results?.map50 ?? null;
                    setCompletionBanner({ mAP, jobId: latest.job_id });
                    setTimeout(() => setCompletionBanner(null), 30000);
                }
                prevRunningCountRef.current = running.length;
            }
        } catch (e) { console.error(e); }
    };

    // Whether a frozen version exists is what separates "you can train" from
    // "training would fail", so the gate model needs it on this page.
    const fetchVersionCount = async (datasetId) => {
        try {
            const res = await fetch(API_ENDPOINTS.TRAINING.VERSIONS_LIST(datasetId), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setVersionCount((data.versions || []).length);
            }
        } catch (e) { /* non-critical */ }
    };

    // The Evaluate step is one of the few that can honestly report `done`:
    // a stored run is evidence the scoring happened, unlike test or deploy
    // where nothing records that anyone did it.
    const fetchEvaluationRuns = async (datasetId) => {
        try {
            const res = await fetch(API_ENDPOINTS.EVALUATION.RUNS(datasetId), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setEvaluationRuns(data.runs || []);
            }
        } catch (e) { /* non-critical */ }
    };

    const fetchMonitoringStats = async (datasetId) => {
        try {
            const res = await fetch(API_ENDPOINTS.MONITORING.STATS(datasetId), {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setMonitoringTotal(data.total_inferences || 0);
            }
        } catch (e) { /* non-critical */ }
    };

    // Keep the pipeline bar live while something is actually running. This used
    // to poll every 8s unconditionally, on every tab and behind a hidden
    // window, alongside the 3s pollers in ProjectTrain and ProjectVersions —
    // three timers on the same endpoint, each costing a database round trip.
    usePolling(
        () => fetchTrainingJobs(params.id),
        {
            intervalMs: 8000,
            idleIntervalMs: 60000,
            active: trainingJobs.some(
                j => j.status === "running" || j.status === "pending"
            ),
            enabled: Boolean(params?.id && token),
            runImmediately: false, // the mount effect above already fetched
        }
    );



    // Safety timeout
    useEffect(() => {
        const timer = setTimeout(() => {
            if (loading) {
                setLoading(false);
                toast.error("Loading timed out. Please check your connection.");
            }
        }, 10000);
        return () => clearTimeout(timer);
    }, [loading]);

    if (loading) return <div className="p-8">Loading project...</div>;
    if (!dataset) return <div className="p-8">Project not found</div>;

    // Derived training job counts for pipeline
    const completedJobs = trainingJobs.filter(j => j.status === 'completed' || j.status === 'success');
    const runningJobs   = trainingJobs.filter(j => j.status === 'running' || j.status === 'pending');
    const failedJobs    = trainingJobs.filter(j => j.status === 'failed');
    const hasModels     = completedJobs.length > 0;
    const isTraining    = runningJobs.length > 0;

    // One derivation for every step's state, from facts rather than from
    // whether a sibling step happens to have produced something.
    const stepStates = deriveStates({
        totalImages: stats?.total_images || 0,
        annotatedImages: stats?.annotated_images || 0,
        versionCount,
        completedJobs: completedJobs.length,
        runningJobs: runningJobs.length,
        failedJobs: failedJobs.length,
        monitoringTotal,
        evaluationCount: evaluationRuns.filter(r => r.status === 'completed').length,
        runningEvaluations: evaluationRuns.filter(
            r => r.status === 'running' || r.status === 'pending'
        ).length,
    });

    return (
        <div className="flex flex-col h-screen overflow-hidden bg-black text-white font-sans">
            {/* Project Header */}
            <header className="h-12 border-b border-white/20 bg-black/80 backdrop-blur-md flex items-center justify-between px-6 shrink-0">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" aria-label="Back to dashboard" onClick={() => router.push("/dashboard")} className="border border-white/20 hover:border-white/50 rounded-none h-8 w-8">
                        <ArrowLeft className="w-4 h-4" />
                    </Button>
                    <div className="flex items-center gap-3">
                        <h1 className="font-bold text-sm uppercase tracking-widest flex items-center gap-2">
                            {dataset.name}
                        </h1>
                        <Badge variant="outline" className="text-[10px]">{dataset.type || "DETECTION"}</Badge>
                        <span className="text-[10px] font-mono text-gray-500 ml-4 hidden md:inline">
                            {stats?.total_images || 0} images {"·"} {dataset.classes?.length || 0} classes
                        </span>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {isTraining && (
                        <div 
                            className="flex items-center gap-2 px-3 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium cursor-pointer hover:bg-amber-500/20 transition-colors"
                            onClick={() => handleTabChange('versions')}
                            title="Click to view training progress"
                        >
                            <span className="w-1.5 h-1.5 bg-amber-400 animate-pulse" />
                            Training {Math.round(runningJobs[0]?.progress || 0)}%
                        </div>
                    )}
                    {failedJobs.length > 0 && !isTraining && !hasModels && (
                        <div className="flex items-center gap-2 px-3 py-1 bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-medium">
                            Training failed
                        </div>
                    )}
                    <Button size="sm" onClick={() => router.push(`/annotate?dataset=${dataset.id}`)}>
                        Open annotator
                    </Button>
                </div>
            </header>



            <NextStepRail stepStates={stepStates} activeTab={activeTab} onNavigate={handleTabChange} />

            {/* Tabs Navigation similar to Roboflow */}
            <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col min-h-0">
                {isTraining && (
                    <div className="px-6 py-3 bg-amber-500/10 border-b border-amber-500/30 flex items-center justify-between text-sm">
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-2 text-amber-400 font-bold">
                                <Cpu className="w-4 h-4 animate-pulse" />
                                <span>Training in progress</span>
                            </div>
                            <span className="text-amber-500/70 hidden md:inline">It keeps running if you leave this tab.</span>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleTabChange('versions')}
                            className="border-amber-500/30 text-amber-400 hover:bg-amber-500/20 hover:text-amber-300"
                        >
                            View progress
                        </Button>
                    </div>
                )}

                {completionBanner && (
                    <div className="px-6 py-3 bg-emerald-500/10 border-b border-emerald-500/30 flex items-center justify-between text-sm">
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-2 text-emerald-400 font-bold">
                                <CheckCircle className="w-4 h-4 shrink-0" />
                                <span>Training complete</span>
                            </div>
                            {completionBanner.mAP !== null && (
                                <span className="text-emerald-500/70 hidden md:inline">mAP50 {(completionBanner.mAP * 100).toFixed(1)}%</span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" className="border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20" onClick={() => { setCompletionBanner(null); handleTabChange('test'); }}>
                                Test it
                            </Button>
                            <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-400" onClick={() => { setCompletionBanner(null); handleTabChange('deploy'); }}>
                                Deploy
                            </Button>
                            <Button size="icon" aria-label="Dismiss notification" variant="ghost" className="w-8 h-8 rounded-none border border-transparent hover:border-emerald-500/50 text-emerald-500" onClick={() => setCompletionBanner(null)}>
                                <X className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                )}

                <div className="flex-1 overflow-auto bg-muted/5 p-6">
                    <div className="max-w-7xl mx-auto h-full">
                        <TabsContent value="overview" className="mt-0 h-full">
                            <ProjectOverview dataset={dataset} stats={stats} trainingJobs={trainingJobs} onRefresh={() => { fetchDataset(dataset.id); fetchStats(dataset.id); }} onNavigate={handleTabChange} />
                        </TabsContent>

                        <TabsContent value="upload" className="mt-0 h-full">
                            <ProjectUpload dataset={dataset} onUploadComplete={() => fetchStats(dataset.id)} onNavigate={handleTabChange} />
                        </TabsContent>

                        <TabsContent value="images" className="mt-0 h-full overflow-y-auto">
                            <ProjectImages dataset={dataset} onRefresh={() => { fetchDataset(dataset.id); fetchStats(dataset.id); }} />
                        </TabsContent>

                        <TabsContent value="annotate" className="mt-0 h-full">
                            <ProjectAnnotate dataset={dataset} stats={stats} onNavigate={handleTabChange} />
                        </TabsContent>

                        <TabsContent value="health" className="mt-0 h-full">
                            <ProjectHealth params={params} />
                        </TabsContent>

                        <TabsContent value="generate" className="mt-0 h-full">
                            <ProjectGenerate dataset={dataset} stats={stats} onGenerate={() => { fetchStats(dataset.id); fetchVersionCount(dataset.id); setVersionRefreshKey(k => k + 1); handleTabChange('train'); }} />
                        </TabsContent>

                        <TabsContent value="versions" className="mt-0 h-full">
                            <ProjectVersions dataset={dataset} onDeploy={() => handleTabChange('deploy')} />
                        </TabsContent>

                        <TabsContent value="train" className="mt-0 h-full">
                            <ProjectTrain dataset={dataset} versionRefreshKey={versionRefreshKey} onTrainingStarted={() => handleTabChange('versions')} onDeploy={() => handleTabChange('deploy')} />
                        </TabsContent>

                        <TabsContent value="evaluate" className="mt-0 h-full overflow-y-auto">
                            <ProjectEvaluate dataset={dataset} onNavigate={handleTabChange} />
                        </TabsContent>

                        <TabsContent value="test" className="mt-0 h-full">
                            <ProjectTest dataset={dataset} />
                        </TabsContent>

                        <TabsContent value="deploy" className="mt-0 h-full">
                            <ProjectDeploy dataset={dataset} />
                        </TabsContent>

                        <TabsContent value="active-learning" className="mt-0 h-full">
                            <ProjectActiveLearning dataset={dataset} onNavigate={handleTabChange} />
                        </TabsContent>

                        <TabsContent value="monitoring" className="mt-0 h-full">
                            <ProjectMonitoring dataset={dataset} />
                        </TabsContent>

                        <TabsContent value="team" className="mt-0 h-full">
                            <ProjectTeam dataset={dataset} />
                        </TabsContent>
                    </div>
                </div>
            </Tabs>
        </div>
    );
}
