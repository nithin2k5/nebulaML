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
    Target,
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
        // Advisory: worth reading, never the thing to nag someone to finish.
        advisory: true,
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
        advisory: true,
        blurb: "Every version and run, with its metrics.",
    },

    {
        // Between Registry and Test on purpose. Registry lists what training
        // reported about itself; Evaluate re-scores a finished model through
        // one shared metric path, which is what makes two runs comparable.
        // Deciding what to deploy belongs here, before Test's ad-hoc spot
        // checks and Deploy's export.
        id: "evaluate",
        label: "Evaluate",
        phase: "build",
        icon: Target,
        requires: ["train"],
        minRole: "admin",
        blurb: "Score a model on the held-out split and see where it fails.",
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

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

// Mirrors _ROLE_RANK in server/app/core/access.py.
const ROLE_RANK = { owner: 4, admin: 3, annotator: 2, viewer: 1 };

export function roleAtLeast(role, minimum) {
    return (ROLE_RANK[role] ?? 0) >= (ROLE_RANK[minimum] ?? 99);
}

/**
 * The steps a given role should be offered.
 *
 * Steps they cannot act on are dropped rather than shown locked: a lock says
 * "do this first", which is wrong when the answer is "this isn't yours". An
 * unknown role (the field is missing, or an older server) gets everything, so
 * this can only ever narrow a view it understands.
 */
export function visibleSteps(role, steps = STEPS) {
    if (!role || !(role in ROLE_RANK)) return steps;
    return steps.filter((s) => roleAtLeast(role, s.minRole));
}

// ---------------------------------------------------------------------------
// Step state
// ---------------------------------------------------------------------------

export const STATE = {
    // A prerequisite is missing. Carries the reason and the step that clears it.
    LOCKED: "locked",
    // Actionable now. The old model had no word for this, which is why steps
    // you could do were indistinguishable from steps you couldn't.
    READY: "ready",
    // Underway: partly annotated, training running, inference arriving.
    ACTIVE: "active",
    // Someone actually did it.
    DONE: "done",
    // Last run failed.
    FAILED: "failed",
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * Work out where every step stands from facts the project page already has.
 *
 * `done` is only ever asserted from evidence that the work happened. It used to
 * be inferred: test, deploy and active-learning all read
 * `hasModels ? 'complete' : 'pending'`, so all three went green the instant
 * training finished, before anyone had tested, exported or reviewed anything.
 * That also made WizardBanner's "every step complete" check pass at the end of
 * training, at which point it deleted its own localStorage flag for good.
 *
 * Steps whose completion nothing currently records stop at `ready`, which is
 * true, rather than claiming `done`, which wasn't.
 */
export function deriveStates(facts = {}) {
    const {
        totalImages = 0,
        annotatedImages = 0,
        versionCount = 0,
        completedJobs = 0,
        runningJobs = 0,
        failedJobs = 0,
        monitoringTotal = 0,
        evaluationCount = 0,
        runningEvaluations = 0,
    } = facts;

    const hasImages = totalImages > 0;
    const unlabelled = Math.max(0, totalImages - annotatedImages);
    const fullyAnnotated = hasImages && unlabelled === 0;
    const hasVersion = versionCount > 0;
    const hasModel = completedJobs > 0;
    const isTraining = runningJobs > 0;
    const trainFailed = failedJobs > 0 && !hasModel && !isTraining;

    const out = {};
    const set = (id, state, reason, blockedBy = null) => {
        out[id] = { state, reason, blockedBy };
    };

    // Ambient — always available, never "complete".
    set("overview", STATE.READY, null);
    set("team", STATE.READY, null);

    // --- Data -------------------------------------------------------------
    set(
        "upload",
        hasImages ? STATE.DONE : STATE.READY,
        hasImages ? `${plural(totalImages, "image")} uploaded.` : "No images yet."
    );

    if (!hasImages) {
        set("images", STATE.LOCKED, "Nothing uploaded yet.", "upload");
        set("annotate", STATE.LOCKED, "Nothing uploaded yet.", "upload");
        set("health", STATE.LOCKED, "Nothing uploaded yet.", "upload");
    } else {
        set("images", STATE.DONE, `${plural(totalImages, "image")} in the project.`);
        set(
            "annotate",
            fullyAnnotated ? STATE.DONE : annotatedImages > 0 ? STATE.ACTIVE : STATE.READY,
            fullyAnnotated
                ? "Every image has boxes."
                : `${plural(unlabelled, "image")} still need boxes.`
        );
        // A health check is advice, not a task with an end — it never reads done.
        set("health", STATE.READY, "Check class balance, duplicates and blur.");
    }

    // --- Build ------------------------------------------------------------
    if (!fullyAnnotated) {
        set(
            "generate",
            STATE.LOCKED,
            hasImages
                ? `${plural(unlabelled, "image")} still need boxes — freezing now would train against blanks.`
                : "Nothing uploaded yet.",
            hasImages ? "annotate" : "upload"
        );
    } else {
        set(
            "generate",
            hasVersion ? STATE.DONE : STATE.READY,
            hasVersion
                ? `${plural(versionCount, "version")} frozen.`
                : "Freeze a snapshot to train against."
        );
    }

    if (!hasVersion) {
        set(
            "train",
            STATE.LOCKED,
            "Training runs against a frozen version, never the live dataset — that is what makes a run reproducible.",
            "generate"
        );
    } else if (isTraining) {
        set("train", STATE.ACTIVE, `${plural(runningJobs, "job")} running.`);
    } else if (hasModel) {
        set("train", STATE.DONE, `${plural(completedJobs, "model")} trained.`);
    } else if (trainFailed) {
        set("train", STATE.FAILED, "The last run failed — see the log.");
    } else {
        set("train", STATE.READY, "Pick a backend and version, then run preflight.");
    }

    if (!hasModel) {
        set(
            "evaluate",
            STATE.LOCKED,
            "Scoring needs a finished model to score.",
            "train"
        );
    } else if (runningEvaluations > 0) {
        set("evaluate", STATE.ACTIVE, `${plural(runningEvaluations, "run")} scoring.`);
    } else if (evaluationCount > 0) {
        // Unlike test and deploy, this one can honestly reach `done`: a stored
        // run is the evidence that the work happened.
        set("evaluate", STATE.DONE, `${plural(evaluationCount, "evaluation")} recorded.`);
    } else {
        set("evaluate", STATE.READY, "Score a model against the held-out split.");
    }

    set(
        "versions",
        hasModel || isTraining ? STATE.READY : STATE.LOCKED,
        hasModel
            ? `${plural(completedJobs, "run")} with metrics.`
            : isTraining
              ? "A run is in progress."
              : "No runs yet.",
        hasModel || isTraining ? null : "train"
    );

    // --- Operate ----------------------------------------------------------
    const needsModel = "Needs a trained model.";
    if (!hasModel) {
        set("test", STATE.LOCKED, needsModel, "train");
        set("deploy", STATE.LOCKED, needsModel, "train");
        set("monitoring", STATE.LOCKED, needsModel, "train");
        set("active-learning", STATE.LOCKED, needsModel, "train");
    } else {
        // Nothing records a test run per project today, so this stops at ready.
        set("test", STATE.READY, "Run the model against new images or a webcam.");
        // Likewise an export: reaching `done` here needs an export to be
        // written to activity_logs, which nothing does yet.
        set("deploy", STATE.READY, "Export the weights, or call the model over the API.");
        // Monitoring is ongoing, so it reads active rather than done.
        set(
            "monitoring",
            monitoringTotal > 0 ? STATE.ACTIVE : STATE.READY,
            monitoringTotal > 0
                ? `${plural(monitoringTotal, "inference")} logged.`
                : "No inference logged yet."
        );
        set("active-learning", STATE.READY, "Review low-confidence predictions.");
    }

    return out;
}

/**
 * The step a person should do next: the first `ready`, `active` or `failed`
 * step in pipeline order, skipping ambient ones.
 *
 * Returns null only when nothing is actionable at all.
 */
export function nextStep(states, steps = STEPS) {
    const actionable = [STATE.READY, STATE.ACTIVE, STATE.FAILED];
    return (
        steps.find((s) => {
            // Ambient steps are always available and advisory ones (Health,
            // Registry) are for reading, so neither is ever "what to do next".
            if (s.phase === "project" || s.advisory) return false;
            return actionable.includes(states[s.id]?.state);
        }) || null
    );
}
