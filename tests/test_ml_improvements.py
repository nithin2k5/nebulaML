"""Unit tests for the dataset-splitting and trainer/inference interfaces.

Imports resolve via the root conftest.py, which puts `server/` on sys.path.
"""

import inspect
import unittest

from app.services.inference import YOLOInference
from app.services.trainer import YOLOTrainer
from utils.dataset_utils import split_dataset_stratified


class TestMLImprovements(unittest.TestCase):
    def test_stratified_split(self):
        """split_dataset_stratified preserves the class distribution across splits."""
        images = []
        # Class A: 100 images, Class B: 20 images — deliberately imbalanced.
        for i in range(100):
            images.append({"id": f"A_{i}", "annotations": [{"class_name": "A"}]})
        for i in range(20):
            images.append({"id": f"B_{i}", "annotations": [{"class_name": "B"}]})

        splits = split_dataset_stratified(images, train_ratio=0.8, val_ratio=0.2, test_ratio=0.0)

        train_a = sum(1 for img in splits["train"] if img["annotations"][0]["class_name"] == "A")
        train_b = sum(1 for img in splits["train"] if img["annotations"][0]["class_name"] == "B")

        # An 80/20 split of 100 A and 20 B should land near 80 A and 16 B in train.
        self.assertTrue(75 <= train_a <= 85, f"Expected ~80 class A in train, got {train_a}")
        self.assertTrue(15 <= train_b <= 18, f"Expected ~16 class B in train, got {train_b}")

        # Every image lands in exactly one split.
        total = sum(len(v) for v in splits.values())
        self.assertEqual(total, len(images))

    def test_trainer_accepts_augmentations(self):
        sig = inspect.signature(YOLOTrainer.train)
        self.assertIn("augmentations", sig.parameters)

    def test_inference_accepts_nms_and_tta(self):
        sig = inspect.signature(YOLOInference.predict)
        self.assertIn("agnostic_nms", sig.parameters)
        self.assertIn("augment", sig.parameters)
