"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_ENDPOINTS } from "@/lib/config";
import { ArrowLeft, Upload, Image, Cpu, Layers, Code, Grid, Activity, Brain, BarChart3, LayoutDashboard, Package, Users, TestTube2, CheckCircle, X } from "lucide-react";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

// Components for each tab
import WizardBanner from "@/components/WizardBanner";
import ProjectOverview from "@/components/project/ProjectOverview";
import ProjectUpload from "@/components/project/ProjectUpload";
import ProjectAnnotate from "@/components/project/ProjectAnnotate";
import ProjectGenerate from "@/components/project/ProjectGenerate";
import ProjectTrain from "@/components/project/ProjectTrain";
import ProjectVersions from "@/components/project/ProjectVersions";
import ProjectTest from "@/components/project/ProjectTest";
import ProjectDeploy from "@/components/project/ProjectDeploy";
import ProjectHealth from "@/components/project/ProjectHealth";
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

    // Poll training jobs every 8s so the pipeline bar stays live
    useEffect(() => {
        if (!params?.id || !token) return;
        const interval = setInterval(() => fetchTrainingJobs(params.id), 8000);
        return () => clearInterval(interval);
    }, [params?.id, token]);



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
    const hasFailed     = failedJobs.length > 0 && !hasModels && !isTraining;

    const pipelineStages = [
        {
            id: 'overview',
            label: 'Overview',
            icon: LayoutDashboard,
            status: 'pending',
            meta: 'Summary'
        },
        {
            id: 'upload',
            label: 'Upload',
            icon: Upload,
            status: (stats?.total_images > 0) ? 'complete' : 'pending',
            meta: `${stats?.total_images || 0} Images`
        },
        {
            id: 'annotate',
            label: 'Annotate',
            icon: Image,
            status: (stats?.annotated_images > 0 && stats?.annotated_images === stats?.total_images) ? 'complete' :
                (stats?.annotated_images > 0) ? 'inprogress' : 'pending',
            meta: `${Math.round(stats?.completion_percentage || 0)}% Done`
        },
        {
            id: 'health',
            label: 'Health',
            icon: Activity,
            status: (stats?.total_images > 0) ? (hasModels ? 'complete' : 'inprogress') : 'pending',
            meta: stats?.total_images > 0 ? 'Quality Check' : 'No Data'
        },
        {
            id: 'generate',
            label: 'Generate',
            icon: Layers,
            status: (stats?.annotated_images > 0 && stats?.annotated_images === stats?.total_images) ? 'complete' :
                    (stats?.annotated_images > 0) ? 'inprogress' : 'pending',
            meta: 'Version Snapshot'
        },
        {
            id: 'versions',
            label: 'Registry',
            icon: Package,
            status: hasModels ? 'complete' : 'pending',
            meta: `${completedJobs.length} Model${completedJobs.length !== 1 ? 's' : ''}`
        },
        {
            id: 'train',
            label: 'Train',
            icon: Cpu,
            status: isTraining ? 'inprogress' :
                    hasModels ? 'complete' :
                    hasFailed ? 'failed' : 'pending',
            meta: isTraining ? `${runningJobs[0] ? Math.round(runningJobs[0].progress || 0) + '%' : 'Running'}` :
                  hasModels ? `${completedJobs.length} Model${completedJobs.length > 1 ? 's' : ''}` :
                  hasFailed ? 'Failed' : 'No Jobs'
        },
        {
            id: 'test',
            label: 'Test',
            icon: TestTube2,
            status: hasModels ? 'complete' : 'pending',
            meta: hasModels ? 'Ready' : 'No Model'
        },
        {
            id: 'deploy',
            label: 'Deploy',
            icon: Code,
            status: hasModels ? 'complete' : 'pending',
            meta: hasModels ? 'Ready' : 'Not Ready'
        },
        {
            id: 'active-learning',
            label: 'Learning',
            icon: Brain,
            status: hasModels ? 'complete' : 'pending',
            meta: hasModels ? 'Ready' : 'Needs Model'
        },
        {
            id: 'monitoring',
            label: 'Monitor',
            icon: BarChart3,
            status: monitoringTotal > 0 ? 'complete' : hasModels ? 'inprogress' : 'pending',
            meta: monitoringTotal > 0 ? `${monitoringTotal} Inferences` : hasModels ? 'Run Inference' : 'No Data'
        },
        {
            id: 'team',
            label: 'Team',
            icon: Users,
            status: 'pending',
            meta: 'Access & Logs'
        }
    ];

    return (
        <div className="flex flex-col h-screen overflow-hidden">
            {/* Project Header */}
            <header className="h-16 border-b border-border bg-background/50 backdrop-blur-sm flex items-center justify-between px-6 shrink-0">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => router.push("/dashboard")}>
                        <ArrowLeft />
                    </Button>
                    <div>
                        <h1 className="font-bold text-lg flex items-center gap-2">
                            {dataset.name}
                            <Badge variant="outline" className="font-normal text-xs">{dataset.type || "Object Detection"}</Badge>
                        </h1>
                        <p className="text-xs text-muted-foreground">{stats?.total_images || 0} images • {dataset.classes?.length || 0} classes</p>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {isTraining && (
                        <div 
                            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium cursor-pointer hover:bg-amber-500/20 transition-colors"
                            onClick={() => handleTabChange('versions')}
                            title="Click to view training progress"
                        >
                            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                            Training {Math.round(runningJobs[0]?.progress || 0)}%
                        </div>
                    )}
                    {failedJobs.length > 0 && !isTraining && !hasModels && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-medium">
                            Last training failed
                        </div>
                    )}
                    <Button size="sm" onClick={() => router.push(`/annotate?dataset=${dataset.id}`)}>
                        Resume Annotating
                    </Button>
                </div>
            </header>

            {/* Pipeline Visualizer — scrollable row so steps stay readable */}
            <div className="px-3 sm:px-6 py-3 bg-muted/5 border-b border-border">
                <div className="max-w-7xl mx-auto overflow-x-auto overscroll-x-contain">
                    <div className="flex items-stretch gap-2 min-w-max py-1 pr-2">
                        {pipelineStages.map((stage) => (
                            <button
                                type="button"
                                key={stage.id}
                                onClick={() => handleTabChange(stage.id)}
                                className={`flex flex-col items-center self-stretch shrink-0 w-[6.25rem] sm:w-[6.5rem] min-h-[5.75rem] rounded-xl border bg-background px-1 py-2 transition-colors hover:bg-muted/50 ${activeTab === stage.id ? 'border-primary ring-2 ring-primary/25 shadow-sm' : 'border-border'}`}
                            >
                                <div className={`shrink-0 w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center border-2 ${stage.status === 'complete' ? 'bg-green-500/10 border-green-500 text-green-500' :
                                    stage.status === 'inprogress' ? 'bg-amber-500/10 border-amber-500 text-amber-500 animate-pulse' :
                                    stage.status === 'failed' ? 'bg-red-500/10 border-red-500 text-red-500' :
                                        'bg-muted border-muted-foreground/30 text-muted-foreground'
                                    }`}>
                                    <stage.icon className="w-4 h-4 sm:w-5 sm:h-5" />
                                </div>
                                <div className="mt-1.5 flex flex-1 flex-col items-center justify-end gap-0.5 w-full min-h-0 text-center">
                                    <span className={`w-full text-[10px] sm:text-[11px] font-semibold leading-snug whitespace-nowrap overflow-hidden text-ellipsis ${activeTab === stage.id ? 'text-primary' : 'text-foreground'}`}>{stage.label}</span>
                                    <span className="w-full text-[9px] sm:text-[10px] text-muted-foreground leading-tight line-clamp-2 break-words">{stage.meta}</span>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <WizardBanner pipelineStages={pipelineStages} activeTab={activeTab} onNavigate={handleTabChange} />

            {/* Tabs Navigation similar to Roboflow */}
            <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col min-h-0">
                <div className="border-b border-border bg-muted/5 px-6 hidden">
                    <TabsList className="h-12 bg-transparent p-0 gap-6">
                        <TabTrigger value="overview" icon={Grid}>Overview</TabTrigger>
                        <TabTrigger value="upload" icon={Upload}>Upload</TabTrigger>
                        <TabTrigger value="annotate" icon={Image}>Annotate</TabTrigger>
                        <TabTrigger value="generate" icon={Layers}>Generate</TabTrigger>
                        <TabTrigger value="train" icon={Cpu}>Train</TabTrigger>
                        <TabTrigger value="versions" icon={Layers}>Registry</TabTrigger>
                        <TabTrigger value="deploy" icon={Code}>Deploy</TabTrigger>
                    </TabsList>
                </div>

                {isTraining && (
                    <div className="px-6 py-3 bg-amber-500/5 border-b border-amber-500/20 flex items-center justify-between">
                        <div className="flex items-center gap-3 text-sm">
                            <div className="flex items-center gap-2">
                                <Cpu className="w-4 h-4 text-amber-500 animate-pulse" />
                                <span className="font-medium">Training in Progress</span>
                            </div>
                            <span className="text-muted-foreground">You can navigate freely - training continues in the background</span>
                        </div>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleTabChange('versions')}
                            className="text-amber-600 hover:text-amber-500"
                        >
                            View Progress
                        </Button>
                    </div>
                )}

                {completionBanner && (
                    <div className="px-6 py-3 bg-emerald-500/5 border-b border-emerald-500/20 flex items-center justify-between">
                        <div className="flex items-center gap-3 text-sm">
                            <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
                            <span className="font-medium">Training complete!</span>
                            {completionBanner.mAP !== null && (
                                <span className="text-muted-foreground">mAP50: <strong>{(completionBanner.mAP * 100).toFixed(1)}%</strong></span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" onClick={() => { setCompletionBanner(null); handleTabChange('test'); }}>
                                Test it
                            </Button>
                            <Button size="sm" onClick={() => { setCompletionBanner(null); handleTabChange('deploy'); }}>
                                Deploy it
                            </Button>
                            <Button size="icon" variant="ghost" className="w-7 h-7" onClick={() => setCompletionBanner(null)}>
                                <X className="w-4 h-4" />
                            </Button>
                        </div>
                    </div>
                )}

                <div className="flex-1 overflow-auto bg-muted/5 p-6">
                    <div className="max-w-7xl mx-auto h-full">
                        <TabsContent value="overview" className="mt-0 h-full">
                            <ProjectOverview dataset={dataset} stats={stats} onRefresh={() => { fetchDataset(dataset.id); fetchStats(dataset.id); }} />
                        </TabsContent>

                        <TabsContent value="upload" className="mt-0 h-full">
                            <ProjectUpload dataset={dataset} onUploadComplete={() => fetchStats(dataset.id)} />
                        </TabsContent>

                        <TabsContent value="annotate" className="mt-0 h-full">
                            <ProjectAnnotate dataset={dataset} stats={stats} onNavigate={handleTabChange} />
                        </TabsContent>

                        <TabsContent value="health" className="mt-0 h-full">
                            <ProjectHealth params={params} />
                        </TabsContent>

                        <TabsContent value="generate" className="mt-0 h-full">
                            <ProjectGenerate dataset={dataset} stats={stats} onGenerate={() => { fetchStats(dataset.id); setVersionRefreshKey(k => k + 1); handleTabChange('train'); }} />
                        </TabsContent>

                        <TabsContent value="versions" className="mt-0 h-full">
                            <ProjectVersions dataset={dataset} onDeploy={() => handleTabChange('deploy')} />
                        </TabsContent>

                        <TabsContent value="train" className="mt-0 h-full">
                            <ProjectTrain dataset={dataset} versionRefreshKey={versionRefreshKey} onTrainingStarted={() => handleTabChange('versions')} onDeploy={() => handleTabChange('deploy')} />
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

function TabTrigger({ value, icon: Icon, children }) {
    return (
        <TabsTrigger
            value={value}
            className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-full px-2 text-muted-foreground data-[state=active]:text-foreground transition-all gap-2"
        >
            <Icon />
            {children}
        </TabsTrigger>
    );
}
