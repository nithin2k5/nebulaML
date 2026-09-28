"use client";

import { useState, useEffect } from "react";
import { ArrowRight, Check, ChevronDown, ChevronUp, Lock, Loader2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PHASES, STEPS, STATE, nextStep } from "@/lib/pipeline";

// Collapsing the rail stores a preference. It deliberately does NOT store
// "never show me this again": the banner this replaces was gated on a
// `nebula_first_project` flag that only existed if you created the project
// yourself, and dismissing it called removeItem — so invited teammates never
// saw guidance at all, and nobody who dismissed it could get it back.
const COLLAPSE_KEY = "nebula_guide_collapsed";

const PIPELINE_PHASES = PHASES.filter((p) => !p.ambient);

export default function NextStepRail({ stepStates, activeTab, onNavigate }) {
    const [collapsed, setCollapsed] = useState(false);

    useEffect(() => {
        try {
            setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
        } catch {
            // Private mode, blocked site data: just show it expanded.
        }
    }, []);

    const toggle = () => {
        const next = !collapsed;
        setCollapsed(next);
        try {
            if (next) localStorage.setItem(COLLAPSE_KEY, "1");
            else localStorage.removeItem(COLLAPSE_KEY);
        } catch { /* nothing to persist to; the toggle still works this session */ }
    };

    if (!stepStates) return null;

    const next = nextStep(stepStates);
    const onNextStep = next && activeTab === next.id;

    const StateIcon = !next
        ? Check
        : stepStates[next.id]?.state === STATE.ACTIVE
          ? Loader2
          : stepStates[next.id]?.state === STATE.FAILED
            ? AlertTriangle
            : ArrowRight;

    const headline = next
        ? onNextStep
            ? next.label
            : `Next: ${next.label}`
        : "Nothing waiting on you";
    const detail = next
        ? stepStates[next.id]?.reason || next.blurb
        : "Every step that can be done has been.";

    return (
        <div className="px-6 py-3 bg-violet-500/10 border-b border-violet-500/30">
            <div className="max-w-7xl mx-auto flex items-center gap-5">

                <div className="flex items-center gap-2 shrink-0">
                    <StateIcon
                        className={`w-4 h-4 text-violet-400 ${stepStates[next?.id]?.state === STATE.ACTIVE ? "animate-spin" : ""}`}
                    />
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-violet-400 hidden lg:inline">
                        Guide
                    </span>
                </div>

                <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                    <p className="text-sm text-white truncate">
                        <span className="font-semibold">{headline}</span>
                        {detail && <span className="text-gray-300"> — {detail}</span>}
                    </p>
                    {!collapsed && (
                        <div className="flex items-center gap-4 flex-wrap pt-1">
                            {PIPELINE_PHASES.map((phase) => {
                                const inPhase = STEPS.filter((s) => s.phase === phase.id);
                                const done = inPhase.filter(
                                    (s) => stepStates[s.id]?.state === STATE.DONE
                                ).length;
                                const blocked = inPhase.every(
                                    (s) => stepStates[s.id]?.state === STATE.LOCKED
                                );
                                const complete = done === inPhase.length;
                                return (
                                    <span
                                        key={phase.id}
                                        className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider"
                                        title={phase.blurb}
                                    >
                                        {complete ? (
                                            <Check className="w-3 h-3 text-emerald-400 shrink-0" />
                                        ) : blocked ? (
                                            <Lock className="w-3 h-3 text-gray-600 shrink-0" />
                                        ) : (
                                            <span className="w-2 h-2 bg-violet-400 shrink-0" />
                                        )}
                                        <span
                                            className={
                                                complete
                                                    ? "text-emerald-400"
                                                    : blocked
                                                      ? "text-gray-600"
                                                      : "text-gray-300"
                                            }
                                        >
                                            {phase.label} {done}/{inPhase.length}
                                        </span>
                                    </span>
                                );
                            })}
                        </div>
                    )}
                </div>

                {next && !onNextStep && (
                    <Button size="sm" className="shrink-0" onClick={() => onNavigate?.(next.id)}>
                        Go to {next.label}
                    </Button>
                )}

                <Button
                    variant="ghost"
                    size="icon"
                    aria-label={collapsed ? "Expand the guide" : "Collapse the guide"}
                    aria-expanded={!collapsed}
                    className="w-7 h-7 shrink-0 rounded-none border border-transparent hover:border-violet-500"
                    onClick={toggle}
                >
                    {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
                </Button>

            </div>
        </div>
    );
}
