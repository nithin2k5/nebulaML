"use client";

import { useState, useEffect } from "react";
import { Check, X, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

const STEPS = [
    {
        id: "upload",
        label: "INGEST",
        hint: "Upload at least 20 images per class for reliable results.",
    },
    {
        id: "annotate",
        label: "ANNOTATE",
        hint: "Draw bounding boxes around every object in each image.",
        troubleshoot: "Missing annotations? Use Smart Annotate to speed up the process.",
    },
    {
        id: "generate",
        label: "GENERATE",
        hint: "Freeze your annotated dataset into an immutable training snapshot.",
        troubleshoot: "Generation blocked? Check the quality gate above for class imbalance or corrupt images.",
    },
    {
        id: "train",
        label: "TRAIN",
        hint: "Start with the Balanced preset — you can refine later.",
        troubleshoot: "Training failed? Review the pre-flight check blockers and ensure your version has enough images.",
    },
    {
        id: "test",
        label: "TEST",
        hint: "Run inference on a few images to validate your model's performance.",
    },
    {
        id: "deploy",
        label: "DEPLOY",
        hint: "Your model is ready — use the API or export for edge devices.",
    },
];

export default function WizardBanner({ pipelineStages, activeTab, onNavigate }) {
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        if (typeof window !== "undefined") {
            setVisible(!!localStorage.getItem("nebula_first_project"));
        }
    }, []);

    if (!visible) return null;

    // Derive which steps are complete from pipelineStages
    const stageStatus = Object.fromEntries(
        (pipelineStages || []).map(s => [s.id, s.status])
    );
    const allDone = STEPS.every(s => stageStatus[s.id] === "complete");

    const dismiss = () => {
        localStorage.removeItem("nebula_first_project");
        setVisible(false);
    };

    if (allDone) {
        dismiss();
        return null;
    }

    // Find first incomplete step
    const currentStepIndex = STEPS.findIndex(s => stageStatus[s.id] !== "complete");
    const currentStep = STEPS[currentStepIndex];
    const isCurrentTabBlocked = currentStep && activeTab === currentStep.id && stageStatus[currentStep.id] === "blocked";

    return (
        <div className="px-6 py-3 bg-violet-500/10 border-b border-violet-500/30 font-sans">
            <div className="max-w-7xl mx-auto space-y-3">
                <div className="flex items-center gap-4">
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-violet-400 shrink-0 hidden sm:block">SYS.GUIDE</span>
                    <div className="flex items-center gap-1 flex-1 overflow-x-auto custom-scrollbar pb-1">
                        {STEPS.map((step, i) => {
                            const isDone = stageStatus[step.id] === "complete";
                            const isCurrent = i === currentStepIndex;
                            return (
                                <div key={step.id} className="flex items-center shrink-0">
                                    <button
                                        onClick={() => onNavigate?.(step.id)}
                                        className={`flex items-center gap-2 px-2 py-1 text-[10px] font-mono uppercase tracking-widest transition-colors
                                            ${isCurrent ? "bg-violet-500 text-black font-bold" : ""}
                                            ${isDone ? "text-emerald-500" : !isCurrent ? "text-gray-500 hover:text-white" : ""}
                                        `}
                                    >
                                        {isDone
                                            ? <Check className="w-3 h-3 shrink-0" />
                                            : <span className={`w-3.5 h-3.5 border flex items-center justify-center text-[8px] shrink-0 ${isCurrent ? "border-black" : "border-current"}`}>{i + 1}</span>
                                        }
                                        {step.label}
                                    </button>
                                    {i < STEPS.length - 1 && (
                                        <span className="mx-2 text-white/20 text-[10px] font-mono">/</span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    <Button variant="ghost" size="icon" className="w-6 h-6 shrink-0 rounded-none border border-transparent hover:border-violet-500" onClick={dismiss}>
                        <X className="w-3.5 h-3.5" />
                    </Button>
                </div>

                {/* Contextual hint for current step */}
                {currentStep && (
                    <div className="flex items-start gap-2 pl-1">
                        <ArrowRight className="w-3 h-3 text-violet-400 shrink-0 mt-0.5" />
                        <p className="text-[10px] font-mono uppercase tracking-wide text-gray-400">
                            <span className="font-bold text-violet-400">{currentStep.label}: </span>
                            {isCurrentTabBlocked && currentStep.troubleshoot
                                ? currentStep.troubleshoot
                                : currentStep.hint}
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
