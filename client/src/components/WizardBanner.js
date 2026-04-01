"use client";

import { useState, useEffect } from "react";
import { CheckCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const STEPS = [
    { id: "upload",   label: "Upload Images" },
    { id: "annotate", label: "Annotate" },
    { id: "generate", label: "Generate Version" },
    { id: "train",    label: "Train Model" },
    { id: "test",     label: "Test" },
    { id: "deploy",   label: "Deploy" },
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

    return (
        <div className="px-6 py-3 bg-primary/5 border-b border-primary/20">
            <div className="max-w-7xl mx-auto flex items-center gap-4">
                <span className="text-xs font-semibold text-primary shrink-0 hidden sm:block">Get started</span>
                <div className="flex items-center gap-1 flex-1 overflow-x-auto">
                    {STEPS.map((step, i) => {
                        const isDone = stageStatus[step.id] === "complete";
                        const isCurrent = i === currentStepIndex;
                        return (
                            <div key={step.id} className="flex items-center shrink-0">
                                <button
                                    onClick={() => onNavigate?.(step.id)}
                                    className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors
                                        ${isCurrent ? "bg-primary text-primary-foreground" : ""}
                                        ${isDone ? "text-emerald-600 dark:text-emerald-400" : !isCurrent ? "text-muted-foreground hover:text-foreground" : ""}
                                    `}
                                >
                                    {isDone
                                        ? <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                                        : <span className={`w-4 h-4 rounded-full border-2 flex items-center justify-center text-[10px] shrink-0 ${isCurrent ? "border-primary-foreground" : "border-current"}`}>{i + 1}</span>
                                    }
                                    {step.label}
                                </button>
                                {i < STEPS.length - 1 && (
                                    <span className="mx-1 text-muted-foreground/40 text-xs">›</span>
                                )}
                            </div>
                        );
                    })}
                </div>
                <Button variant="ghost" size="icon" className="w-6 h-6 shrink-0" onClick={dismiss}>
                    <X className="w-3.5 h-3.5" />
                </Button>
            </div>
        </div>
    );
}
