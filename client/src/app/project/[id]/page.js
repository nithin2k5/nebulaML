"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_ENDPOINTS } from "@/lib/config";
import { ArrowLeft, Upload, Image, Cpu, Layers, Code, Grid, Activity, Brain, BarChart3 } from "lucide-react";
import { toast } from 'sonner';
import { useAuth } from "@/context/AuthContext";

// Components for each tab
import ProjectOverview from "@/components/project/ProjectOverview";
import ProjectUpload from "@/components/project/ProjectUpload";
import ProjectAnnotate from "@/components/project/ProjectAnnotate";
import ProjectGenerate from "@/components/project/ProjectGenerate";
import ProjectTrain from "@/components/project/ProjectTrain";
import ProjectVersions from "@/components/project/ProjectVersions";
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
    const [versionRefreshKey, setVersionRefreshKey] = useState(0);
    const [activeTab, setActiveTab] = useState(searchParams.get('tab') || "overview");
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
                setTrainingJobs((data.jobs || []).filter(j => j.dataset_id === datasetId));
            }
        } catch (e) { console.error(e); }
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
    const runningJobs   = trainingJobs.filter(j => j.status === 'running');
    const failedJobs    = trainingJobs.filter(j => j.status === 'failed');
    const hasModels     = completedJobs.length > 0;
    const isTraining    = runningJobs.length > 0;
    const hasFailed     = failedJobs.length > 0 && !hasModels && !isTraining;

    const pipelineStages = [
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
            id: 'generate',
            label: 'Generate',
            icon: Layers,
            status: (stats?.annotated_images > 0 && stats?.annotated_images === stats?.total_images) ? 'complete' :
                    (stats?.annotated_images > 0) ? 'inprogress' : 'pending',
            meta: 'Version Snapshot'
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
            id: 'versions',
            label: 'Registry',
            icon: Grid,
            status: hasModels ? 'complete' : 'pending',
            meta: `${completedJobs.length} Model${completedJobs.length !== 1 ? 's' : ''}`
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
            label: 'Active Learn',
            icon: Brain,
            status: 'pending',
            meta: 'Re-train Loop'
        },
        {
            id: 'monitoring',
            label: 'Monitor',
            icon: BarChart3,
            status: 'pending',
            meta: 'No Data'
        },
        {
            id: 'health',
            label: 'Health',
            icon: Activity,
            status: 'pending',
            meta: 'No Issues'
        },
        {
            id: 'team',
            label: 'Team',
            icon: Grid,
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
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium">
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

            {/* Pipeline Visualizer (Quick Nav) */}
            <div className="px-6 py-4 bg-muted/5 border-b border-border">
                <div className="flex items-center justify-between max-w-4xl mx-auto relative">
                    {/* Connecting Line */}
                    <div className="absolute top-1/2 left-0 w-full h-0.5 bg-border -z-10 -translate-y-1/2" />

                    {pipelineStages.map((stage, idx) => (
                        <div
                            key={stage.id}
                            onClick={() => handleTabChange(stage.id)}
                            className={`flex flex-col items-center gap-2 cursor-pointer group bg-background px-4 py-2 rounded-xl border transition-all hover:scale-105 ${activeTab === stage.id ? 'border-primary ring-2 ring-primary/20' : 'border-border'}`}
                        >
                            <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 ${stage.status === 'complete' ? 'bg-green-500/10 border-green-500 text-green-500' :
                                stage.status === 'inprogress' ? 'bg-amber-500/10 border-amber-500 text-amber-500 animate-pulse' :
                                stage.status === 'failed' ? 'bg-red-500/10 border-red-500 text-red-500' :
                                    'bg-muted border-muted-foreground/30 text-muted-foreground'
                                }`}>
                                <stage.icon className="w-5 h-5" />
                            </div>
                            <div className="text-center">
                                <p className={`text-xs font-semibold ${activeTab === stage.id ? 'text-primary' : 'text-foreground'}`}>{stage.label}</p>
                                <p className="text-[10px] text-muted-foreground">{stage.meta}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

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

                <div className="flex-1 overflow-auto bg-muted/5 p-6">
                    <div className="max-w-7xl mx-auto h-full">
                        <TabsContent value="overview" className="mt-0 h-full">
                            <ProjectOverview dataset={dataset} stats={stats} onRefresh={() => { fetchDataset(dataset.id); fetchStats(dataset.id); }} />
                        </TabsContent>

                        <TabsContent value="upload" className="mt-0 h-full">
                            <ProjectUpload dataset={dataset} onUploadComplete={() => fetchStats(dataset.id)} />
                        </TabsContent>

                        <TabsContent value="annotate" className="mt-0 h-full">
                            <ProjectAnnotate dataset={dataset} stats={stats} />
                        </TabsContent>

                        <TabsContent value="generate" className="mt-0 h-full">
                            <ProjectGenerate dataset={dataset} stats={stats} onGenerate={() => { fetchStats(dataset.id); setVersionRefreshKey(k => k + 1); handleTabChange('train'); }} />
                        </TabsContent>

                        <TabsContent value="train" className="mt-0 h-full">
                            <ProjectTrain dataset={dataset} versionRefreshKey={versionRefreshKey} onTrainingStarted={() => handleTabChange('versions')} />
                        </TabsContent>

                        <TabsContent value="versions" className="mt-0 h-full">
                            <ProjectVersions dataset={dataset} onDeploy={() => handleTabChange('deploy')} />
                        </TabsContent>

                        <TabsContent value="deploy" className="mt-0 h-full">
                            <ProjectDeploy dataset={dataset} />
                        </TabsContent>

                        <TabsContent value="active-learning" className="mt-0 h-full">
                            <ProjectActiveLearning dataset={dataset} />
                        </TabsContent>

                        <TabsContent value="monitoring" className="mt-0 h-full">
                            <ProjectMonitoring dataset={dataset} />
                        </TabsContent>

                        <TabsContent value="health" className="mt-0 h-full">
                            <ProjectHealth params={params} />
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
