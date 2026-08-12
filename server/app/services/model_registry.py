"""
Model Registry — central catalog of all supported detection model backends.

Each model entry includes:
- display_name: Human-readable name shown in UI
- backend: "yolo" | "rtdetr" | "torchvision"
- license: "AGPL-3.0" | "Apache-2.0" | "BSD-3-Clause"
- params: approximate parameter count string
- description: short description
- default_imgsz: recommended image size
- checkpoint: the checkpoint identifier (e.g. HuggingFace model id or .pt filename)
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class ModelInfo:
    key: str                    # unique key used as model_name in config
    display_name: str
    backend: str                # "yolo", "rtdetr", "torchvision"
    license: str
    params: str                 # e.g. "3.2M"
    description: str
    default_imgsz: int = 640
    checkpoint: str = ""        # backend-specific checkpoint id
    family: str = ""            # grouping label for UI (e.g. "YOLOv8", "RT-DETR", "Faster R-CNN")

MODEL_REGISTRY: Dict[str, ModelInfo] = {}

def _register(info: ModelInfo):
    MODEL_REGISTRY[info.key] = info

# ── YOLO models (AGPL-3.0) ──────────────────────────────────────────
for variant, params in [("n", "3.2M"), ("s", "11.2M"), ("m", "25.9M"), ("l", "43.7M"), ("x", "68.2M")]:
    _register(ModelInfo(
        key=f"yolov8{variant}.pt", display_name=f"YOLOv8 {variant.upper()}",
        backend="yolo", license="AGPL-3.0", params=params,
        description=f"YOLOv8 {variant.upper()} — {'Fastest' if variant=='n' else 'Fast' if variant=='s' else 'Balanced' if variant=='m' else 'Accurate' if variant=='l' else 'Most Accurate'}",
        checkpoint=f"yolov8{variant}.pt", family="YOLOv8"
    ))

for variant, params in [("c", "25.3M"), ("e", "57.3M")]:
    _register(ModelInfo(
        key=f"yolov9{variant}.pt", display_name=f"YOLOv9 {variant.upper()}",
        backend="yolo", license="AGPL-3.0", params=params,
        description=f"YOLOv9 {variant.upper()}",
        checkpoint=f"yolov9{variant}.pt", family="YOLOv9"
    ))

for variant, params in [("n", "2.3M"), ("s", "7.2M"), ("m", "15.4M"), ("l", "24.4M"), ("x", "29.5M")]:
    _register(ModelInfo(
        key=f"yolov10{variant}.pt", display_name=f"YOLOv10 {variant.upper()}",
        backend="yolo", license="AGPL-3.0", params=params,
        description=f"YOLOv10 {variant.upper()}",
        checkpoint=f"yolov10{variant}.pt", family="YOLOv10"
    ))

for variant, params in [("n", "2.6M"), ("s", "9.4M"), ("m", "20.1M"), ("l", "25.3M"), ("x", "56.9M")]:
    _register(ModelInfo(
        key=f"yolo11{variant}.pt", display_name=f"YOLO11 {variant.upper()}",
        backend="yolo", license="AGPL-3.0", params=params,
        description=f"YOLO11 {variant.upper()}",
        checkpoint=f"yolo11{variant}.pt", family="YOLO11"
    ))

# ── RT-DETR models (Apache 2.0) ─────────────────────────────────────
_register(ModelInfo(
    key="rtdetr-r18", display_name="RT-DETR ResNet-18",
    backend="rtdetr", license="Apache-2.0", params="20M",
    description="RT-DETR with ResNet-18 backbone — fastest Transformer detector",
    checkpoint="PekingU/rtdetr_r18vd", family="RT-DETR", default_imgsz=640
))
_register(ModelInfo(
    key="rtdetr-r50", display_name="RT-DETR ResNet-50",
    backend="rtdetr", license="Apache-2.0", params="42M",
    description="RT-DETR with ResNet-50 backbone — balanced speed and accuracy",
    checkpoint="PekingU/rtdetr_r50vd", family="RT-DETR", default_imgsz=640
))
_register(ModelInfo(
    key="rtdetr-r101", display_name="RT-DETR ResNet-101",
    backend="rtdetr", license="Apache-2.0", params="76M",
    description="RT-DETR with ResNet-101 backbone — highest accuracy Transformer",
    checkpoint="PekingU/rtdetr_r101vd", family="RT-DETR", default_imgsz=640
))

# ── TorchVision models (BSD-3-Clause) ────────────────────────────────
_register(ModelInfo(
    key="fasterrcnn-resnet50", display_name="Faster R-CNN ResNet-50",
    backend="torchvision", license="BSD-3-Clause", params="41.8M",
    description="Faster R-CNN with ResNet-50 + FPN backbone",
    checkpoint="fasterrcnn_resnet50_fpn_v2", family="Faster R-CNN", default_imgsz=800
))
_register(ModelInfo(
    key="fasterrcnn-mobilenet", display_name="Faster R-CNN MobileNetV3",
    backend="torchvision", license="BSD-3-Clause", params="19.4M",
    description="Faster R-CNN with MobileNetV3-Large backbone — lightweight",
    checkpoint="fasterrcnn_mobilenet_v3_large_fpn", family="Faster R-CNN", default_imgsz=800
))
_register(ModelInfo(
    key="fcos-resnet50", display_name="FCOS ResNet-50",
    backend="torchvision", license="BSD-3-Clause", params="32.3M",
    description="FCOS anchor-free detector with ResNet-50 + FPN",
    checkpoint="fcos_resnet50_fpn", family="FCOS", default_imgsz=800
))
_register(ModelInfo(
    key="retinanet-resnet50", display_name="RetinaNet ResNet-50",
    backend="torchvision", license="BSD-3-Clause", params="34.0M",
    description="RetinaNet with ResNet-50 + FPN backbone",
    checkpoint="retinanet_resnet50_fpn_v2", family="RetinaNet", default_imgsz=800
))
_register(ModelInfo(
    key="ssd-vgg16", display_name="SSD VGG-16",
    backend="torchvision", license="BSD-3-Clause", params="35.6M",
    description="Single Shot Detector with VGG-16 backbone",
    checkpoint="ssd300_vgg16", family="SSD", default_imgsz=300
))
_register(ModelInfo(
    key="ssdlite-mobilenet", display_name="SSDLite MobileNetV3",
    backend="torchvision", license="BSD-3-Clause", params="3.4M",
    description="SSDLite with MobileNetV3-Large — fastest, edge-friendly",
    checkpoint="ssdlite320_mobilenet_v3_large", family="SSD", default_imgsz=320
))

# ── Helper functions ─────────────────────────────────────────────────

def get_model_info(model_name: str) -> Optional[ModelInfo]:
    """Lookup a model by its key. Returns None if not found."""
    return MODEL_REGISTRY.get(model_name)

def get_backend(model_name: str) -> str:
    """Return the backend type for a model key. Defaults to 'yolo' for .pt files."""
    info = MODEL_REGISTRY.get(model_name)
    if info:
        return info.backend
    # Fallback: if it ends with .pt and isn't registered, assume YOLO
    if model_name.endswith(".pt"):
        return "yolo"
    return "unknown"

def get_allowed_model_keys() -> set:
    """Return the set of all valid model keys."""
    return set(MODEL_REGISTRY.keys())

def get_models_by_backend(backend: str) -> list:
    """Return all models for a given backend."""
    return [m for m in MODEL_REGISTRY.values() if m.backend == backend]

def get_models_grouped_by_family() -> dict:
    """Return models grouped by family for UI display."""
    groups = {}
    for model in MODEL_REGISTRY.values():
        family = model.family or model.backend
        if family not in groups:
            groups[family] = []
        groups[family].append(model)
    return groups

def get_registry_for_api() -> list:
    """Return the full registry as a list of dicts for the API."""
    return [
        {
            "key": m.key,
            "display_name": m.display_name,
            "backend": m.backend,
            "license": m.license,
            "params": m.params,
            "description": m.description,
            "default_imgsz": m.default_imgsz,
            "family": m.family,
        }
        for m in MODEL_REGISTRY.values()
    ]
