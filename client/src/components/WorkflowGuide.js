"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  Camera, Upload, Tag, Sliders, Shuffle, GitBranch,
  Download, Cpu, BarChart2, Rocket, Zap, RefreshCw,
  ChevronRight, ChevronDown, BookOpen, ExternalLink,
  CheckCircle, AlertTriangle, Lightbulb, Info
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

const stages = [
  {
    id: 1, icon: Camera, color: "blue",
    title: "Data Collection",
    tagline: "Garbage in, garbage out — quality data is everything.",
    summary: "Gather diverse, balanced images from multiple sources before any ML work begins.",
    what: "Collect images representing every scenario your model will face in production. Include varied lighting, angles, occlusions, and backgrounds.",
    sources: ["Manual capture (phone/camera)", "Web scraping (Google Images, Flickr)", "Public datasets (COCO, Open Images, Kaggle)", "Synthetic data (Blender, Unity Perception)", "Roboflow Universe (250K+ datasets)"],
    tips: ["Aim for ≥200 images per class minimum", "Include negative samples (images with no target objects)", "Capture edge cases: partial occlusion, unusual angles, low light", "Balance classes — avoid 10:1 ratio between largest and smallest"],
    pitfalls: ["Collecting all images from one environment/angle", "Ignoring class imbalance until training", "Using blurry or mislabelled images"],
    analogy: "Think of data as your study material. Studying only sunny-day photos makes you fail on rainy days."
  },
  {
    id: 2, icon: Upload, color: "indigo",
    title: "Upload & Project Setup",
    tagline: "Structure your data before you start labelling.",
    summary: "Create a project, choose its type (detection / segmentation / classification), and upload images via UI, API, or SDK.",
    what: "Roboflow deduplicates via SHA-256 hashing, reads EXIF metadata for auto-orientation, and assigns images to train/valid/test splits (default 70/20/10).",
    sources: ["Web UI drag-and-drop", "Python SDK: project.upload()", "REST API (any language)", "Direct import from CVAT, Label Studio"],
    tips: ["Set train/valid/test splits before annotating", "Use batch naming to track upload sessions", "Choose the right project type upfront — harder to change later"],
    pitfalls: ["Uploading duplicates inflates metrics", "Wrong project type means incompatible annotation tools"],
    analogy: "Setting up a filing system before you start adding documents — saves chaos later."
  },
  {
    id: 3, icon: Tag, color: "purple",
    title: "Annotation (Labeling)",
    tagline: "Annotation quality is the single biggest lever for model performance.",
    summary: "Draw bounding boxes, polygons, or classification tags on every image. Use auto-labeling to speed this up 3–10×.",
    what: "Bounding boxes use (x_center, y_center, width, height) normalized 0–1. Polygons trace exact object boundaries. Roboflow stores all annotations in a normalized JSON format so they survive any resize.",
    sources: ["Bounding boxes — object detection", "Polygons — instance segmentation", "Classification tags — image-level labels", "Keypoints — pose estimation"],
    tips: ["Keep boxes tight — edges should touch the object", "Use keyboard shortcuts (N = next, 1-9 = class keys)", "Use SAM or model-assisted labeling for large datasets", "Create annotation guidelines so teams stay consistent"],
    pitfalls: ["Loose bounding boxes add noise to loss function", "Unlabeled objects teach the model to ignore them", "Inconsistent class names ('Car' vs 'car' vs 'cars')"],
    analogy: "Like highlighting a textbook — too wide a highlight (loose box) makes you re-read irrelevant text."
  },
  {
    id: 4, icon: Sliders, color: "cyan",
    title: "Data Preprocessing",
    tagline: "Neural networks need consistent, standardized input.",
    summary: "Resize, normalize, auto-orient, and optionally tile images before training. Applied at version-generation time, not at upload.",
    what: "Roboflow reads EXIF orientation flags and physically rotates pixels. Letterboxing (adding gray padding) preserves aspect ratio better than stretching. Annotations are recalculated automatically after any resize.",
    sources: ["Auto-orient (EXIF correction)", "Resize with letterbox (recommended)", "Grayscale conversion", "CLAHE contrast enhancement", "Tiling (for small objects in large images)"],
    tips: ["Use letterbox resize, not stretch — preserves aspect ratio", "Tile 4K images into 640×640 patches for small object detection", "640×640 is the YOLO standard; use 1280 for small objects"],
    pitfalls: ["Mixed resolutions in a batch cause silent errors", "Stretching changes aspect ratios (circles become ovals)"],
    analogy: "Like typesetting a book — all pages must be the same size before printing."
  },
  {
    id: 5, icon: Shuffle, color: "emerald",
    title: "Data Augmentation",
    tagline: "Teach the model to generalize, not memorize.",
    summary: "Artificially expand your dataset with flips, rotations, blur, brightness shifts, and more. Annotations are transformed automatically.",
    what: "Augmentations create modified copies during training. A horizontal flip moves a bounding box from x=0.2 to x=0.8. Mosaic combines 4 images into one frame, forcing the model to detect at multiple scales simultaneously.",
    sources: ["Geometric: flip, rotate, crop, shear", "Photometric: brightness, blur, noise, hue", "Advanced: Mosaic, Cutout, Copy-Paste, Mixup", "Test-Time Augmentation (TTA) at inference"],
    tips: ["Mosaic is very effective — disable for final 10 epochs (YOLOv8 does this automatically)", "Avoid horizontal flip for text detection or directional tasks", "Small datasets (<500 images) benefit from heavy augmentation"],
    pitfalls: ["Over-augmenting large datasets wastes training time", "Extreme color shifts confuse color-dependent tasks (ripe fruit detection)"],
    analogy: "Like a student practicing math with varied numbers — not memorizing specific answers."
  },
  {
    id: 6, icon: GitBranch, color: "violet",
    title: "Dataset Versioning",
    tagline: "Reproducibility is not optional in ML.",
    summary: "Every unique combination of preprocessing + augmentation + split creates a new immutable dataset version. Roll back anytime.",
    what: "Each version stores the list of image IDs, pipeline config, and split assignments — not pixel copies. Generated augmented images are cached for fast export. Enables A/B testing of preprocessing strategies.",
    sources: ["Immutable snapshots of pipeline config", "Image ID lists (not pixel duplicates)", "Cached augmented images", "Experiment tracking across versions"],
    tips: ["Increment version when adding new images or changing augmentation", "Name versions descriptively: 'v3-mosaic-640-80-split'", "Compare mAP across versions to isolate what improved performance"],
    pitfalls: ["Retraining on a different version and comparing results is meaningless", "Forgetting which version produced your best model"],
    analogy: "Like Git commits for your data — you can always checkout v2 and see exactly what trained your best model."
  },
  {
    id: 7, icon: Download, color: "sky",
    title: "Export & Format Conversion",
    tagline: "Different frameworks speak different annotation dialects.",
    summary: "Export datasets as YOLO, COCO JSON, Pascal VOC XML, TFRecord, or CreateML. Roboflow converts coordinate systems and file structures automatically.",
    what: "YOLO uses normalized center-based coords in .txt files. COCO uses a single JSON with image/annotation/category arrays. Pascal VOC uses corner-based coords in XML. Roboflow handles all conversions from its internal normalized format.",
    sources: ["YOLOv5/v7/v8/v11 PyTorch (.txt + data.yaml)", "COCO JSON (single annotations.json)", "Pascal VOC XML (one .xml per image)", "TFRecord (binary protobuf for TensorFlow)", "CreateML JSON (Apple Core ML)"],
    tips: ["Use YOLOv8 format for Ultralytics training — includes data.yaml", "Use COCO JSON for Detectron2 or MMDetection", "Download via API for automated CI/CD pipelines"],
    pitfalls: ["YOLO and VOC use different coordinate origins — mixing them corrupts training", "Forgetting to include the data.yaml class names file"],
    analogy: "Like translating a book — same content, different language syntax."
  },
  {
    id: 8, icon: Cpu, color: "amber",
    title: "Model Training",
    tagline: "Transfer learning: stand on the shoulders of COCO giants.",
    summary: "Train with Roboflow's no-code platform or externally with Ultralytics/PyTorch. Key configs: epochs, batch size, learning rate, image size, model variant.",
    what: "Start from COCO pretrained weights (transfer learning). The backbone extracts features, the neck fuses multi-scale features, the head predicts boxes per grid cell. Loss = box loss (CIoU) + class loss (BCE) + objectness loss.",
    sources: ["YOLOv8n/s/m/l/x variants", "Epochs: 50–300 (use early stopping)", "Batch: 16–64 depending on GPU VRAM", "LR: 0.01 with cosine annealing + warmup", "Image size: 640 (standard), 1280 (small objects)"],
    tips: ["Always start from pretrained weights (yolov8n.pt)", "Use AMP (Automatic Mixed Precision) to halve VRAM usage", "Freeze backbone layers for very small datasets (<200 images)", "Disable mosaic for last 10 epochs for fine-tuning"],
    pitfalls: ["Training from scratch requires 10K+ images", "Batch size too large → CUDA OOM; too small → unstable gradients", "Not using a learning rate scheduler → training plateaus early"],
    analogy: "Pretrained weights are like hiring someone who already knows how to see — you just teach them your specific task."
  },
  {
    id: 9, icon: BarChart2, color: "rose",
    title: "Model Evaluation",
    tagline: "mAP is the headline — the confusion matrix tells the story.",
    summary: "Evaluate with mAP@0.5, precision, recall, and F1-score. Use the confusion matrix to find which classes are confused, missed, or falsely detected.",
    what: "mAP = mean of per-class Average Precision (area under Precision-Recall curve). mAP@0.5:0.95 averages across IoU thresholds for a stricter metric. A detection is 'correct' only if its box overlaps ground truth by ≥ IoU threshold.",
    sources: ["mAP@0.5 — primary detection metric", "mAP@0.5:0.95 — stricter COCO-style metric", "Precision = TP / (TP + FP)", "Recall = TP / (TP + FN)", "F1 = harmonic mean of P and R"],
    tips: ["High train mAP + low val mAP = overfitting → add augmentation or data", "Low recall = model misses objects → add more training data", "Low precision = too many false positives → raise confidence threshold or add negatives"],
    pitfalls: ["Relying on mAP alone — a model can score well on common classes and fail on rare ones", "Not checking per-class AP — average hides per-class failures"],
    analogy: "mAP is like a GPA — it summarizes performance, but you need to check per-subject grades to find weak spots."
  },
  {
    id: 10, icon: Rocket, color: "orange",
    title: "Deployment",
    tagline: "From .pt file to production API in minutes.",
    summary: "Deploy via Roboflow's hosted API, a local inference server, or export to edge formats (TensorRT, TFLite, CoreML, ONNX, browser JS).",
    what: "Roboflow Inference is an open-source server that runs locally (docker or pip). TensorRT optimizes for NVIDIA GPUs with 2–5× speedup. FP16 half-precision halves VRAM with <0.1% accuracy loss. INT8 quantization gives 3–4× speedup with 1–3% accuracy loss.",
    sources: ["Roboflow Hosted API (cloud GPU, ~300ms)", "Local Inference Server (~30–100ms)", "NVIDIA Jetson (TensorRT .engine)", "Raspberry Pi (TFLite)", "Web Browser (roboflow.js + TF.js)", "iOS/Android (CoreML / TFLite)"],
    tips: ["Use TensorRT for NVIDIA GPU deployments — biggest speedup", "Batch multiple images together for offline processing (Nx throughput)", "Local server keeps data private and eliminates API rate limits"],
    pitfalls: ["Preprocessing mismatch between training and inference causes offset predictions", "Not testing on real production hardware before launch"],
    analogy: "Training a chef in a kitchen (GPU server) then deploying them to a food truck (edge device) — same skills, different constraints."
  },
  {
    id: 11, icon: Zap, color: "yellow",
    title: "Inference",
    tagline: "8400 candidate boxes → a handful of confident predictions.",
    summary: "The inference pipeline: preprocess → backbone → neck → head → filter by confidence → Non-Max Suppression → scale back to original image size.",
    what: "YOLOv8 on a 640×640 image produces 8400 raw predictions (6400 at 80×80 grid + 1600 at 40×40 + 400 at 20×20). NMS removes duplicate overlapping boxes by keeping the highest-confidence box and eliminating all others above IoU threshold (~0.45).",
    sources: ["Confidence threshold: 0.3–0.5 (production)", "NMS IoU threshold: 0.45 (standard)", "Each prediction: [x, y, w, h, class_probs...]", "Output: class + confidence + bbox per detection"],
    tips: ["Lower confidence threshold → more detections (higher recall, lower precision)", "For video: add a tracker (ByteTrack, DeepSORT) to reduce jitter", "Test-Time Augmentation adds 1–3% mAP at 2–3× inference time cost"],
    pitfalls: ["Confidence too high → model misses valid detections", "Forgetting NMS → same object detected 20 times", "Not scaling boxes back to original image size after letterbox resize"],
    analogy: "Like a job application filter: thousands of candidates (raw predictions) → shortlisted (confidence filter) → final hires (NMS removes duplicates)."
  },
  {
    id: 12, icon: RefreshCw, color: "teal",
    title: "Monitoring & Iteration",
    tagline: "A deployed model is not the end — it's the beginning.",
    summary: "Monitor production confidence scores, collect failure images, label them (active learning), add to dataset, and retrain. Repeat continuously.",
    what: "Active learning: run inference on new production images, sort by lowest confidence — these are the samples the model struggles with most. Upload, label, and add them to the next dataset version. Retrain from your best checkpoint (not from scratch) to avoid catastrophic forgetting.",
    sources: ["Production monitoring (confidence trends)", "Active learning (low-conf image selection)", "Data drift detection (accuracy degrading over time)", "A/B testing (old vs new model in parallel)", "Automated retraining pipelines"],
    tips: ["Include old training data when retraining — prevents forgetting old classes", "Use dataset versioning to ensure rollback if new model is worse", "Monitor per-class metrics, not just overall mAP — drift is often class-specific"],
    pitfalls: ["Retraining from scratch on new data → model forgets old patterns", "No staging environment → bad model goes straight to production", "Treating deployment as 'done' — data distributions shift over time"],
    analogy: "Like a doctor who keeps studying — the world changes, new cases appear, and you must keep learning."
  }
];

const colorMap = {
  blue:    { bg: "bg-blue-500/10",    border: "border-blue-500/30",    text: "text-blue-400",    ring: "ring-blue-500/20",    dot: "bg-blue-400"    },
  indigo:  { bg: "bg-indigo-500/10",  border: "border-indigo-500/30",  text: "text-indigo-400",  ring: "ring-indigo-500/20",  dot: "bg-indigo-400"  },
  purple:  { bg: "bg-purple-500/10",  border: "border-purple-500/30",  text: "text-purple-400",  ring: "ring-purple-500/20",  dot: "bg-purple-400"  },
  cyan:    { bg: "bg-cyan-500/10",    border: "border-cyan-500/30",    text: "text-cyan-400",    ring: "ring-cyan-500/20",    dot: "bg-cyan-400"    },
  emerald: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400", ring: "ring-emerald-500/20", dot: "bg-emerald-400" },
  violet:  { bg: "bg-violet-500/10",  border: "border-violet-500/30",  text: "text-violet-400",  ring: "ring-violet-500/20",  dot: "bg-violet-400"  },
  sky:     { bg: "bg-sky-500/10",     border: "border-sky-500/30",     text: "text-sky-400",     ring: "ring-sky-500/20",     dot: "bg-sky-400"     },
  amber:   { bg: "bg-amber-500/10",   border: "border-amber-500/30",   text: "text-amber-400",   ring: "ring-amber-500/20",   dot: "bg-amber-400"   },
  rose:    { bg: "bg-rose-500/10",    border: "border-rose-500/30",    text: "text-rose-400",    ring: "ring-rose-500/20",    dot: "bg-rose-400"    },
  orange:  { bg: "bg-orange-500/10",  border: "border-orange-500/30",  text: "text-orange-400",  ring: "ring-orange-500/20",  dot: "bg-orange-400"  },
  yellow:  { bg: "bg-yellow-500/10",  border: "border-yellow-500/30",  text: "text-yellow-400",  ring: "ring-yellow-500/20",  dot: "bg-yellow-400"  },
  teal:    { bg: "bg-teal-500/10",    border: "border-teal-500/30",    text: "text-teal-400",    ring: "ring-teal-500/20",    dot: "bg-teal-400"    },
};

function StageCard({ stage, isActive, onClick }) {
  const c = colorMap[stage.color];
  const Icon = stage.icon;
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 text-left group",
        isActive
          ? `${c.bg} ${c.border} ring-1 ${c.ring}`
          : "border-white/5 hover:border-white/10 hover:bg-white/[0.03]"
      )}
    >
      <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-all", c.bg, isActive ? c.border + " border" : "")}>
        <Icon className={cn("w-4 h-4", c.text)} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={cn("text-[10px] font-mono font-bold", c.text)}>
            {String(stage.id).padStart(2, "0")}
          </span>
          <span className="text-sm font-semibold text-white truncate">{stage.title}</span>
        </div>
        <p className="text-[10px] text-gray-500 truncate mt-0.5">{stage.tagline}</p>
      </div>
      <ChevronRight className={cn("w-3.5 h-3.5 shrink-0 transition-transform", isActive ? `${c.text} rotate-90` : "text-gray-600")} />
    </button>
  );
}

function InfoBlock({ icon: Icon, label, color, items }) {
  const c = colorMap[color] || colorMap.blue;
  return (
    <div className={cn("rounded-xl border p-4 space-y-2", c.bg, c.border)}>
      <div className={cn("flex items-center gap-2 text-xs font-bold uppercase tracking-wider", c.text)}>
        <Icon className="w-3.5 h-3.5" />
        {label}
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-gray-300">
            <div className={cn("w-1 h-1 rounded-full mt-1.5 shrink-0", c.dot)} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function WorkflowGuide() {
  const [activeId, setActiveId] = useState(1);
  const stage = stages.find(s => s.id === activeId);
  const c = colorMap[stage.color];
  const Icon = stage.icon;
  const completed = stages.filter(s => s.id < activeId).length;
  const progress = Math.round((completed / stages.length) * 100);

  return (
    <div className="space-y-6 animate-fade-in text-gray-100">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">
            CV Workflow Guide
          </h2>
          <p className="text-muted-foreground mt-1">
            End-to-end computer vision pipeline — from raw pixels to production.
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-black text-white">{progress}%</div>
          <div className="text-xs text-gray-500">explored</div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 rounded-full bg-white/5 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500"
          animate={{ width: `${Math.max(2, progress)}%` }}
          transition={{ duration: 0.4 }}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stage List */}
        <div className="space-y-1.5 lg:max-h-[70vh] lg:overflow-y-auto custom-scrollbar pr-1">
          {stages.map(s => (
            <StageCard
              key={s.id}
              stage={s}
              isActive={activeId === s.id}
              onClick={() => setActiveId(s.id)}
            />
          ))}
        </div>

        {/* Detail Panel */}
        <div className="lg:col-span-2">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeId}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.2 }}
              className="space-y-4"
            >
              {/* Stage header */}
              <div className={cn("rounded-2xl border p-6", c.bg, c.border)}>
                <div className="flex items-start gap-4">
                  <div className={cn("w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border", c.bg, c.border)}>
                    <Icon className={cn("w-6 h-6", c.text)} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <Badge variant="outline" className={cn("text-[10px] font-mono border", c.border, c.text)}>
                        Stage {String(stage.id).padStart(2, "0")} / 12
                      </Badge>
                    </div>
                    <h3 className="text-xl font-bold text-white">{stage.title}</h3>
                    <p className={cn("text-sm font-medium mt-0.5", c.text)}>{stage.tagline}</p>
                  </div>
                </div>

                <p className="mt-4 text-sm text-gray-300 leading-relaxed">{stage.summary}</p>
              </div>

              {/* What happens internally */}
              <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-gray-400">
                  <Info className="w-3.5 h-3.5" />
                  What Actually Happens
                </div>
                <p className="text-sm text-gray-300 leading-relaxed">{stage.what}</p>
              </div>

              {/* 3-column grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <InfoBlock
                  icon={BookOpen}
                  label="Key Concepts / Types"
                  color={stage.color}
                  items={stage.sources}
                />
                <InfoBlock
                  icon={Lightbulb}
                  label="Best Practices"
                  color="emerald"
                  items={stage.tips}
                />
                <InfoBlock
                  icon={AlertTriangle}
                  label="Common Pitfalls"
                  color="rose"
                  items={stage.pitfalls}
                />
              </div>

              {/* Analogy */}
              <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 p-4 flex items-start gap-3">
                <div className="text-lg shrink-0 mt-0.5">💡</div>
                <div>
                  <div className="text-xs font-bold uppercase tracking-wider text-indigo-400 mb-1">Analogy</div>
                  <p className="text-sm text-gray-300 italic">"{stage.analogy}"</p>
                </div>
              </div>

              {/* Navigation */}
              <div className="flex items-center justify-between pt-2">
                <button
                  disabled={activeId === 1}
                  onClick={() => setActiveId(id => Math.max(1, id - 1))}
                  className="flex items-center gap-2 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="w-4 h-4 rotate-180" />
                  Previous
                </button>
                <div className="flex gap-1">
                  {stages.map(s => (
                    <button
                      key={s.id}
                      onClick={() => setActiveId(s.id)}
                      className={cn(
                        "w-1.5 h-1.5 rounded-full transition-all duration-200",
                        s.id === activeId ? `w-4 ${colorMap[s.color].dot}` : "bg-white/20 hover:bg-white/40"
                      )}
                    />
                  ))}
                </div>
                <button
                  disabled={activeId === 12}
                  onClick={() => setActiveId(id => Math.min(12, id + 1))}
                  className="flex items-center gap-2 text-sm text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
