"""
Multi-Format Export Service

Exports dataset annotations in multiple formats:
- COCO JSON
- Pascal VOC XML
- CSV
- CreateML JSON
"""

import json
import os
import zipfile
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import logging

from app.services.database import DatasetService, AnnotationService

logger = logging.getLogger(__name__)


class ExportService:
    """Handles exporting annotations in multiple formats."""

    @staticmethod
    def export_coco(dataset_id: str, images: list, annotations_data: list, classes: list) -> str:
        """
        Export annotations in COCO JSON format.
        Returns path to the generated JSON file.
        """
        coco = {
            "info": {
                "description": f"Dataset {dataset_id} exported from NebulaML",
                "version": "1.0",
                "year": 2026
            },
            "licenses": [],
            "images": [],
            "annotations": [],
            "categories": []
        }

        # Build categories
        for idx, cls_name in enumerate(classes):
            coco["categories"].append({
                "id": idx,
                "name": cls_name,
                "supercategory": "object"
            })

        class_map = {name: idx for idx, name in enumerate(classes)}
        ann_id = 1

        for img in images:
            image_id = img.get("id", "")
            filename = img.get("filename", "")
            # Get annotation for this image
            annotation = AnnotationService.get_annotation(dataset_id, image_id)

            img_width = 640
            img_height = 640
            if annotation:
                img_width = annotation.get("width", 640)
                img_height = annotation.get("height", 640)

            coco["images"].append({
                "id": hash(image_id) % (10**9),
                "file_name": filename,
                "width": img_width,
                "height": img_height
            })

            if annotation and annotation.get("boxes"):
                for box in annotation["boxes"]:
                    x = float(box.get("x", 0))
                    y = float(box.get("y", 0))
                    w = float(box.get("width", 0))
                    h = float(box.get("height", 0))
                    class_name = box.get("class_name", "")
                    cat_id = class_map.get(class_name, 0)

                    coco["annotations"].append({
                        "id": ann_id,
                        "image_id": hash(image_id) % (10**9),
                        "category_id": cat_id,
                        "bbox": [x, y, w, h],
                        "area": w * h,
                        "iscrowd": 0,
                        "segmentation": []
                    })
                    ann_id += 1

        # Write to temp file
        output_path = tempfile.mktemp(suffix="_coco.json")
        with open(output_path, "w") as f:
            json.dump(coco, f, indent=2)

        return output_path

    @staticmethod
    def export_voc(dataset_id: str, images: list, classes: list) -> str:
        """
        Export annotations in Pascal VOC XML format.
        Returns path to a ZIP file containing XML annotation files.
        """
        output_dir = tempfile.mkdtemp(prefix="voc_export_")
        xml_dir = os.path.join(output_dir, "Annotations")
        os.makedirs(xml_dir, exist_ok=True)

        for img in images:
            image_id = img.get("id", "")
            filename = img.get("filename", "")
            annotation = AnnotationService.get_annotation(dataset_id, image_id)

            root = Element("annotation")
            SubElement(root, "folder").text = "images"
            SubElement(root, "filename").text = filename

            size = SubElement(root, "size")
            img_w = annotation.get("width", 640) if annotation else 640
            img_h = annotation.get("height", 640) if annotation else 640
            SubElement(size, "width").text = str(img_w)
            SubElement(size, "height").text = str(img_h)
            SubElement(size, "depth").text = "3"

            SubElement(root, "segmented").text = "0"

            if annotation and annotation.get("boxes"):
                for box in annotation["boxes"]:
                    obj = SubElement(root, "object")
                    SubElement(obj, "name").text = box.get("class_name", "unknown")
                    SubElement(obj, "pose").text = "Unspecified"
                    SubElement(obj, "truncated").text = "0"
                    SubElement(obj, "difficult").text = "0"

                    bndbox = SubElement(obj, "bndbox")
                    x = float(box.get("x", 0))
                    y = float(box.get("y", 0))
                    w = float(box.get("width", 0))
                    h = float(box.get("height", 0))
                    SubElement(bndbox, "xmin").text = str(int(x))
                    SubElement(bndbox, "ymin").text = str(int(y))
                    SubElement(bndbox, "xmax").text = str(int(x + w))
                    SubElement(bndbox, "ymax").text = str(int(y + h))

            # Pretty print XML
            xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="  ")
            xml_filename = os.path.splitext(filename)[0] + ".xml"
            with open(os.path.join(xml_dir, xml_filename), "w") as f:
                f.write(xml_str)

        # Zip the directory
        zip_path = tempfile.mktemp(suffix="_voc.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root_dir, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root_dir, file)
                    arcname = os.path.relpath(file_path, output_dir)
                    zf.write(file_path, arcname)

        return zip_path

    @staticmethod
    def export_csv(dataset_id: str, images: list, classes: list) -> str:
        """
        Export annotations in CSV format.
        Format: filename,class,x,y,width,height,confidence
        """
        output_path = tempfile.mktemp(suffix="_annotations.csv")

        with open(output_path, "w") as f:
            f.write("filename,class_name,x,y,width,height,confidence\n")
            for img in images:
                image_id = img.get("id", "")
                filename = img.get("filename", "")
                annotation = AnnotationService.get_annotation(dataset_id, image_id)

                if annotation and annotation.get("boxes"):
                    for box in annotation["boxes"]:
                        f.write(
                            f"{filename},"
                            f"{box.get('class_name', '')},"
                            f"{box.get('x', 0)},"
                            f"{box.get('y', 0)},"
                            f"{box.get('width', 0)},"
                            f"{box.get('height', 0)},"
                            f"{box.get('confidence', 1.0)}\n"
                        )
                else:
                    f.write(f"{filename},,,,,\n")

        return output_path

    @staticmethod
    def export_createml(dataset_id: str, images: list, classes: list) -> str:
        """
        Export annotations in Apple CreateML JSON format.
        Format: Array of {image, annotations: [{label, coordinates}]}
        """
        createml = []

        for img in images:
            image_id = img.get("id", "")
            filename = img.get("filename", "")
            annotation = AnnotationService.get_annotation(dataset_id, image_id)

            img_entry = {
                "image": filename,
                "annotations": []
            }

            if annotation and annotation.get("boxes"):
                for box in annotation["boxes"]:
                    x = float(box.get("x", 0))
                    y = float(box.get("y", 0))
                    w = float(box.get("width", 0))
                    h = float(box.get("height", 0))

                    img_entry["annotations"].append({
                        "label": box.get("class_name", "unknown"),
                        "coordinates": {
                            "x": x + w / 2,  # CreateML uses center coordinates
                            "y": y + h / 2,
                            "width": w,
                            "height": h
                        }
                    })

            createml.append(img_entry)

        output_path = tempfile.mktemp(suffix="_createml.json")
        with open(output_path, "w") as f:
            json.dump(createml, f, indent=2)

        return output_path
