"""Unit tests for the annotation save endpoint.

The old version of this file imported `app.routes.annotations`, a module path
that no longer exists, and called `sys.exit(1)` at import time when that failed
— which aborted the whole pytest run. It now targets the real handler at
`app.api.v1.endpoints.annotations` and patches the DB services, so it needs no
database.
"""

from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.v1.endpoints import annotations as ann

DATASET_ID = "test_ds"
IMAGE_ID = "img1"
USER = {"id": 1, "role": "admin"}


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Patch the DB layer and run with cwd at tmp_path.

    The handler writes YOLO label files to `datasets/<id>/labels` relative to
    the working directory, so the chdir keeps the test off the real dataset tree.
    """
    saved = {}

    def fake_get_dataset(dataset_id):
        if dataset_id != DATASET_ID:
            return None
        return {
            "id": DATASET_ID,
            "user_id": USER["id"],
            "name": "Test",
            "classes": ["A", "B"],
            "images": [{"id": IMAGE_ID, "annotated": False}],
        }

    def fake_save_annotation(**kwargs):
        saved.update(kwargs)
        return True

    monkeypatch.setattr(ann.DatasetService, "get_dataset", staticmethod(fake_get_dataset))
    monkeypatch.setattr(ann.AnnotationService, "save_annotation", staticmethod(fake_save_annotation))
    # Ownership is exercised by the RBAC tests; here it should always pass.
    monkeypatch.setattr(ann, "require_role", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)
    return saved


def _request(**overrides):
    payload = {
        "dataset_id": DATASET_ID,
        "image_id": IMAGE_ID,
        "image_name": "test.jpg",
        "width": 100,
        "height": 100,
        "boxes": [{"x": 10, "y": 10, "width": 20, "height": 20, "class_id": 0, "class_name": "A"}],
        "split": "train",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_save_writes_normalised_yolo_label(patched, tmp_path):
    await ann.save_annotation(BackgroundTasks(), _request(), current_user=USER)

    label_file = tmp_path / "datasets" / DATASET_ID / "labels" / "test.txt"
    assert label_file.exists(), "handler did not write a YOLO label file"

    # Box (10,10) 20x20 in a 100x100 image → centre (0.2, 0.2), size (0.2, 0.2).
    class_id, cx, cy, w, h = label_file.read_text().split()
    assert class_id == "0"
    assert float(cx) == pytest.approx(0.2)
    assert float(cy) == pytest.approx(0.2)
    assert float(w) == pytest.approx(0.2)
    assert float(h) == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_save_rejects_class_id_outside_dataset_range(patched):
    with pytest.raises(HTTPException) as exc:
        await ann.save_annotation(
            BackgroundTasks(),
            _request(boxes=[{"x": 1, "y": 1, "width": 2, "height": 2, "class_id": 9}]),
            current_user=USER,
        )
    assert exc.value.status_code == 400
    assert "out of range" in exc.value.detail


@pytest.mark.asyncio
async def test_save_rejects_unknown_split(patched):
    with pytest.raises(HTTPException) as exc:
        await ann.save_annotation(BackgroundTasks(), _request(split="holdout"), current_user=USER)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_save_rejects_image_not_in_dataset(patched):
    with pytest.raises(HTTPException) as exc:
        await ann.save_annotation(BackgroundTasks(), _request(image_id="not-mine"), current_user=USER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_save_requires_dataset_and_image_ids(patched):
    with pytest.raises(HTTPException) as exc:
        await ann.save_annotation(BackgroundTasks(), _request(dataset_id=None), current_user=USER)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_save_writes_classification_label_without_coordinates(patched, tmp_path):
    await ann.save_annotation(
        BackgroundTasks(),
        _request(annotation_type="classification", boxes=[{"class_id": 1}]),
        current_user=USER,
    )
    label_file = tmp_path / "datasets" / DATASET_ID / "labels" / "test.txt"
    assert label_file.read_text().strip() == "1"


async def test_save_annotation_declares_background_tasks(patched):
    """The auto-retrain path calls background_tasks.add_task().

    It used to reference a `background_tasks` name the handler never declared
    and a `get_backend` never imported, so the moment auto-retrain fired it
    raised NameError into a bare `except Exception` and the feature silently
    did nothing.
    """
    import inspect

    sig = inspect.signature(ann.save_annotation)
    assert "background_tasks" in sig.parameters
    assert sig.parameters["background_tasks"].annotation is BackgroundTasks


async def test_auto_retrain_helpers_are_importable():
    """get_backend must resolve in this module's namespace at call time."""
    from app.services.model_registry import get_backend

    assert callable(get_backend)
