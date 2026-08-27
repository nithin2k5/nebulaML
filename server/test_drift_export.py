import pytest
import os
import shutil
import uuid
import json
from pathlib import Path

from app.services.database import DatasetService, AnnotationService, DatasetVersionService
from app.services.versioning import VersioningEngine, DatasetDriftError
from app.services.dataset_manifest import compute_manifest, PreflightResultService, prepare_splits
from app.services.preflight import PreflightPipeline

@pytest.fixture
def mock_dataset():
    dataset_id = str(uuid.uuid4())
    img1_id = str(uuid.uuid4())
    img2_id = str(uuid.uuid4())
    
    os.makedirs(f"datasets/{dataset_id}/images", exist_ok=True)
    os.makedirs(f"datasets/{dataset_id}/labels", exist_ok=True)
    
    with open(f"datasets/{dataset_id}/images/{img1_id}.jpg", "wb") as f:
        f.write(os.urandom(1024))
    with open(f"datasets/{dataset_id}/images/{img2_id}.jpg", "wb") as f:
        f.write(os.urandom(1024))
        
    DatasetService.create_dataset(dataset_id, "Test DB", ["class1"], "", 1)
    DatasetService.add_image(dataset_id, img1_id, f"{img1_id}.jpg", "img1.jpg", f"datasets/{dataset_id}/images/{img1_id}.jpg")
    DatasetService.add_image(dataset_id, img2_id, f"{img2_id}.jpg", "img2.jpg", f"datasets/{dataset_id}/images/{img2_id}.jpg")
    
    box1 = [{"class_id": 0, "class_name": "class1", "x": 10, "y": 10, "width": 50, "height": 50}]
    box2 = [{"class_id": 0, "class_name": "class1", "x": 20, "y": 20, "width": 50, "height": 50}]
    
    AnnotationService.save_annotation(f"{dataset_id}_{img1_id}", dataset_id, img1_id, f"{img1_id}.jpg", 640, 640, box1)
    AnnotationService.save_annotation(f"{dataset_id}_{img2_id}", dataset_id, img2_id, f"{img2_id}.jpg", 640, 640, box2)
    
    yield dataset_id, img1_id, img2_id
    
    shutil.rmtree(f"datasets/{dataset_id}")

def test_stage_d_validation_happens_after_split_assignment(mock_dataset):
    dataset_id, img1, img2 = mock_dataset
    
    # Ensure splits are None initially
    dataset = DatasetService.get_dataset(dataset_id)
    images = DatasetService.get_dataset_images(dataset_id)
    assert all(not img.get('split') for img in images)
    
    # Run preflight
    res = PreflightPipeline.run_all(dataset_id)
    
    # Check if DB has splits now
    images_after = DatasetService.get_dataset_images(dataset_id)
    assert all(img.get('split') in ['train', 'val', 'test'] for img in images_after)
    
    # Stage D checks should not fail with "empty_validation_split" falsely if it was randomly assigned nicely
    # (Since there are 2 images, 80/10/10 split might put 1 in train, 0 in val. Let's force a 50/50 split ratio)
    prepare_splits(dataset_id, {"train": 0.5, "val": 0.5})

def test_export_blocked_on_drift(mock_dataset):
    dataset_id, img1, img2 = mock_dataset
    
    # Run preflight
    PreflightPipeline.run_all(dataset_id)
    
    # Introduce drift: add another box
    box1_new = [{"class_id": 0, "class_name": "class1", "x": 10, "y": 10, "width": 50, "height": 50},
                {"class_id": 0, "class_name": "class1", "x": 100, "y": 100, "width": 20, "height": 20}]
    AnnotationService.save_annotation(f"{dataset_id}_{img1}", dataset_id, img1, f"{img1}.jpg", 640, 640, box1_new)
    
    engine = VersioningEngine()
    with pytest.raises(DatasetDriftError):
        engine.generate_version(dataset_id, "Test", {}, {})

def test_export_succeeds_when_manifest_matches(mock_dataset):
    dataset_id, img1, img2 = mock_dataset
    
    # Run preflight
    PreflightPipeline.run_all(dataset_id)
    
    engine = VersioningEngine()
    version_id = engine.generate_version(dataset_id, "Test", {}, {})
    assert version_id is not None

def test_export_succeeds_with_force_produces_tagged_version(mock_dataset):
    dataset_id, img1, img2 = mock_dataset
    
    PreflightPipeline.run_all(dataset_id)
    
    # Introduce drift
    box1_new = [{"class_id": 0, "class_name": "class1", "x": 10, "y": 10, "width": 50, "height": 50},
                {"class_id": 0, "class_name": "class1", "x": 100, "y": 100, "width": 20, "height": 20}]
    AnnotationService.save_annotation(f"{dataset_id}_{img1}", dataset_id, img1, f"{img1}.jpg", 640, 640, box1_new)
    
    engine = VersioningEngine()
    version_id = engine.generate_version(dataset_id, "Test", {}, {}, force=True)
    assert version_id is not None
    
    version = DatasetVersionService.get_version(version_id)
    assert version['augmentations'].get("_exported_without_current_preflight") is True

def test_post_aug_degenerate_box_caught(mock_dataset, monkeypatch):
    dataset_id, img1, img2 = mock_dataset
    
    PreflightPipeline.run_all(dataset_id)
    
    engine = VersioningEngine()
    
    # Monkeypatch pipeline to return a degenerate box
    original_pipeline = engine._build_augmentation_pipeline
    def mock_pipeline(*args, **kwargs):
        return lambda image, bboxes, class_labels: {
            "image": image,
            "bboxes": [[0.5, 0.5, 0.000001, 0.000001]], # Degenerate box
            "class_labels": class_labels
        }
    
    monkeypatch.setattr(engine, "_build_augmentation_pipeline", mock_pipeline)
    
    with pytest.raises(DatasetDriftError) as exc_info:
        engine.generate_version(dataset_id, "Test", {}, {"blur": True})
        
    assert "Post-augmentation structural validation failed" in str(exc_info.value)
