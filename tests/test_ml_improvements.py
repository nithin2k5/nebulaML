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

    def _imbalanced_images(self):
        images = [{"id": f"A_{i}", "annotations": [{"class_name": "A"}]} for i in range(100)]
        images += [{"id": f"B_{i}", "annotations": [{"class_name": "B"}]} for i in range(20)]
        return images

    def test_split_without_a_test_set(self):
        """train/val only — the stratifier rejects a test_size of 0.0."""
        images = self._imbalanced_images()
        splits = split_dataset_stratified(images, train_ratio=0.8, val_ratio=0.2, test_ratio=0.0)
        self.assertEqual(len(splits["test"]), 0)
        self.assertEqual(len(splits["train"]) + len(splits["val"]), len(images))

    def test_split_without_a_val_set(self):
        """train/test only — the same guard applies to the second split."""
        images = self._imbalanced_images()
        splits = split_dataset_stratified(images, train_ratio=0.8, val_ratio=0.0, test_ratio=0.2)
        self.assertEqual(len(splits["val"]), 0)
        self.assertEqual(len(splits["train"]) + len(splits["test"]), len(images))

    def test_split_all_train(self):
        """Everything in train is a legitimate ask and must not raise."""
        images = self._imbalanced_images()
        splits = split_dataset_stratified(images, train_ratio=1.0, val_ratio=0.0, test_ratio=0.0)
        self.assertEqual(len(splits["train"]), len(images))
        self.assertEqual(len(splits["val"]), 0)
        self.assertEqual(len(splits["test"]), 0)

    def test_split_loses_no_images_across_ratios(self):
        images = self._imbalanced_images()
        for train, val, test in [
            (0.7, 0.2, 0.1),
            (0.8, 0.2, 0.0),
            (0.8, 0.0, 0.2),
            (1.0, 0.0, 0.0),
            (0.5, 0.5, 0.0),
        ]:
            with self.subTest(ratios=(train, val, test)):
                splits = split_dataset_stratified(
                    images, train_ratio=train, val_ratio=val, test_ratio=test
                )
                ids = [img["id"] for group in splits.values() for img in group]
                self.assertEqual(len(ids), len(images))
                self.assertEqual(len(set(ids)), len(images), "an image landed in two splits")

    def test_trainer_accepts_augmentations(self):
        sig = inspect.signature(YOLOTrainer.train)
        self.assertIn("augmentations", sig.parameters)

    def test_inference_accepts_nms_and_tta(self):
        sig = inspect.signature(YOLOInference.predict)
        self.assertIn("agnostic_nms", sig.parameters)
        self.assertIn("augment", sig.parameters)
