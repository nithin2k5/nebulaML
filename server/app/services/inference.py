from ultralytics import YOLO
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
import torch

class YOLOInference:
    """YOLO model inference handler"""
    
    def __init__(self, model_path: str = "yolov8n.pt"):
        """
        Initialize YOLO model
        
        Args:
            model_path: Path to YOLO model weights
        """
        self.model = YOLO(model_path)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
    def predict(
        self, 
        image: Any, 
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        augment: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Run inference on an image
        
        Args:
            image: Path to input image, PIL Image, or numpy array
            conf_threshold: Confidence threshold for detections
            iou_threshold: IoU threshold for NMS
            agnostic_nms: If True, perform class-agnostic NMS
            augment: If True, perform Test Time Augmentation (TTA)
            
        Returns:
            List of detection dictionaries
        """
        results = self.model(
            image, 
            conf=conf_threshold,
            iou=iou_threshold,
            device=self.device,
            agnostic_nms=agnostic_nms,
            augment=augment
        )
        
        detections = []
        for result in results:
            boxes = result.boxes
            masks = getattr(result, 'masks', None)
            
            for idx, box in enumerate(boxes):
                detection = {
                    "class_id": int(box.cls[0]),
                    "class_name": self.model.names[int(box.cls[0])],
                    "confidence": float(box.conf[0]),
                    "bbox": box.xyxy[0].tolist(),
                    "bbox_normalized": box.xywhn[0].tolist()
                }
                
                if masks is not None and idx < len(masks.xy):
                    polygon = masks.xy[idx]
                    if polygon is not None and len(polygon) > 0:
                        detection["polygon"] = polygon.flatten().tolist()
                
                detections.append(detection)
                
        return detections
    
    def predict_batch(
        self, 
        images: List[Any], 
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        agnostic_nms: bool = False,
        augment: bool = False
    ) -> List[List[Dict[str, Any]]]:
        """
        Run inference on multiple images in a true batch
        
        Args:
            images: List of image paths, PIL Images, or numpy arrays
            conf_threshold: Confidence threshold
            iou_threshold: IoU threshold for NMS
            agnostic_nms: If True, perform class-agnostic NMS
            augment: If True, perform Test Time Augmentation (TTA)
            
        Returns:
            List of detection lists for each image
        """
        results = self.model(
            images,
            conf=conf_threshold,
            iou=iou_threshold,
            device=self.device,
            agnostic_nms=agnostic_nms,
            augment=augment
        )
        
        all_detections = []
        for result in results:
            detections = []
            boxes = result.boxes
            masks = getattr(result, 'masks', None)
            
            if boxes:
                for idx, box in enumerate(boxes):
                    detection = {
                        "class_id": int(box.cls[0]),
                        "class_name": self.model.names[int(box.cls[0])],
                        "confidence": float(box.conf[0]),
                        "bbox": box.xyxy[0].tolist(),
                        "bbox_normalized": box.xywhn[0].tolist()
                    }
                    
                    if masks is not None and idx < len(masks.xy):
                        polygon = masks.xy[idx]
                        if polygon is not None and len(polygon) > 0:
                            detection["polygon"] = polygon.flatten().tolist()
                    
                    detections.append(detection)
            all_detections.append(detections)
            
        return all_detections

