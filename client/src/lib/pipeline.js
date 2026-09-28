import {
    Activity,
    BarChart3,
    Brain,
    Code,
    Cpu,
    Grid,
    Image as ImageIcon,
    Layers,
    LayoutDashboard,
    Package,
    TestTube2,
    Upload,
    Users,
} from "lucide-react";

// The one description of the project pipeline.
//
// This used to live in three places that disagreed: `pipelineStages` in
// app/project/[id]/page.js listed 13 steps, WizardBanner's STEPS listed 6, and
// the sidebar in app/project/layout.js hardcoded a different 6. Whichever one
// you read, the other two contradicted it — and the seven steps missing from
// the sidebar had no standing way in at all.

export const PHASES = [
    {
        id: "data",
        label: "Data",
        blurb: "Get images in and labelled well enough to freeze.",
    },
    {
        id: "build",
        label: "Build",
        blurb: "Freeze a version, train against it, read the result.",
    },
    {
        id: "operate",
        label: "Operate",
        blurb: "Put the model in front of real images and keep watching it.",
    },
    {
        // Overview and Team are not pipeline steps — they are always available
        // and never "complete". Treating them as stages is why both carried a
        // permanent `pending` marker.
        id: "project",
        label: "Project",
        ambient: true,
    },
];

// `id` doubles as the ?tab= value, so these stay stable even where the label
// reads better changed (generate → "Version", versions → "Registry").
//
// `requires` names the steps that must be done first; it is what turns a
// missing prerequisite into a sentence a person can act on rather than a step
// that silently isn't there.
//
// `minRole` mirrors the server's per-project hierarchy in core/access.py
// (owner > admin > annotator > viewer).
export const STEPS = [
    {
        id: "overview",
        label: "Overview",
        phase: "project",
        icon: LayoutDashboard,
        requires: [],
        minRole: "viewer",
        blurb: "Where the project stands and what is blocking each phase.",
    },

    {
        id: "upload",
        label: "Upload",
        phase: "data",
        icon: Upload,
        requires: [],
        minRole: "annotator",
        blurb: "Drag in images, import a ZIP, or extract frames from a video.",
    },
    {
        id: "images",
        label: "Images",
        phase: "data",
        icon: Grid,
        requires: ["upload"],
        minRole: "annotator",
        blurb: "Browse, filter and delete what you uploaded.",
    },
    {
        id: "annotate",
        label: "Annotate",
        phase: "data",
        icon: ImageIcon,
        requires: ["upload"],
        minRole: "annotator",
        blurb: "Draw boxes by hand, or auto-label from a model and correct it.",
    },
    {
        id: "health",
        label: "Health",
        phase: "data",
        icon: Activity,
        requires: ["upload"],
        minRole: "annotator",
        blurb: "Class balance, duplicates, blur and corruption, scored over time.",
    },

    {
        id: "generate",
        label: "Version",
        phase: "build",
        icon: Layers,
        requires: ["annotate"],
        minRole: "admin",
        blurb: "Freeze an immutable snapshot with its own preprocessing.",
    },
    {
        id: "train",
        label: "Train",
        phase: "build",
        icon: Cpu,
        requires: ["generate"],
        minRole: "admin",
        blurb: "Run a backend against a frozen version and stream metrics.",
    },
    {
        // Registry holds what training produces, so it follows Train. The old
        // pipeline array listed it first, offering the model registry before
        // the step that makes models.
        id: "versions",
        label: "Registry",
        phase: "build",
        icon: Package,
        requires: ["train"],
        minRole: "admin",
        blurb: "Every version and run, with its metrics.",
    },

    {
        id: "test",
        label: "Test",
        phase: "operate",
        icon: TestTube2,
        requires: ["train"],
        minRole: "admin",
        blurb: "Run the trained model against new images or a webcam.",
    },
    {
        id: "deploy",
        label: "Deploy",
        phase: "operate",
        icon: Code,
        requires: ["train"],
        minRole: "admin",
        blurb: "Export the weights, or call the model through the API.",
    },
    {
        id: "monitoring",
        label: "Monitor",
        phase: "operate",
        icon: BarChart3,
        requires: ["train"],
        minRole: "admin",
        blurb: "Inference volume, confidence distribution and drift.",
    },
    {
        // Not a terminus: its output is annotation work, so it loops back to
        // the Data phase.
        id: "active-learning",
        label: "Active Learning",
        phase: "operate",
        icon: Brain,
        requires: ["train"],
        minRole: "annotator",
        loopsTo: "annotate",
        blurb: "Review low-confidence predictions and feed them back.",
    },

    {
        id: "team",
        label: "Team",
        phase: "project",
        icon: Users,
        requires: [],
        minRole: "viewer",
        blurb: "Per-project roles, invitations and the activity log.",
    },
];

export const STEP_IDS = STEPS.map((s) => s.id);

export function getStep(id) {
    return STEPS.find((s) => s.id === id) || null;
}

export function stepsInPhase(phaseId) {
    return STEPS.filter((s) => s.phase === phaseId);
}

/**
 * The steps grouped for navigation, in pipeline order.
 * Phases with no visible steps are dropped so a filtered nav has no empty headings.
 */
export function navGroups(steps = STEPS) {
    return PHASES.map((phase) => ({
        phase,
        steps: steps.filter((s) => s.phase === phase.id),
    })).filter((g) => g.steps.length > 0);
}
