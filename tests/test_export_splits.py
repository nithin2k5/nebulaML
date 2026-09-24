"""The export pipeline, driven against a real filesystem.

_export_task builds datasets/<id>/split/{train,val,test} and writes the
data.yaml that /start-micro trains from. It touches no database, so these run
the real code over a temporary directory rather than asserting on source text.

The bug these cover: the split tree was reused between exports and the copies
into it are additive, so an image that moved from train to val stayed in both —
silently validating a model on images it had trained on.
"""

import asyncio
import os

import pytest
from PIL import Image

from app.api.v1.endpoints.annotations import _export_task, export_jobs


DATASET_ID = "ds-test"


def _make_image(path, colour=(255, 0, 0)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), colour).save(path)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A dataset on disk with four annotated images, cwd pointed at it."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "datasets" / DATASET_ID
    for i in range(4):
        _make_image(root / "images" / f"img{i}.jpg")
        (root / "labels").mkdir(parents=True, exist_ok=True)
        (root / "labels" / f"img{i}.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    return root


def _images(splits):
    """splits: {'img0': 'train', ...} -> the list shape _export_task expects."""
    return [
        {"id": name, "filename": f"{name}.jpg", "split": split}
        for name, split in splits.items()
    ]


def _run_export(images, job_id="job-1"):
    export_jobs[job_id] = {"status": "pending", "progress": 0, "dataset_id": DATASET_ID}
    asyncio.run(
        _export_task(
            job_id,
            DATASET_ID,
            0.8,
            {},
            {"name": "testset", "classes": ["thing"]},
            images,
            [i for i in images if i.get("split")],
        )
    )
    return export_jobs[job_id]


def _split_contents(root, split):
    d = root / "split" / split / "images"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


# ── The contamination ────────────────────────────────────────────────────────

def test_moving_an_image_between_splits_does_not_leave_it_in_both(workspace):
    """The regression: re-exporting after a split change used to duplicate."""
    first = _run_export(_images({f"img{i}": "train" for i in range(4)}))
    assert first["status"] == "completed", first.get("error")
    assert _split_contents(workspace, "train") == [
        "img0.jpg", "img1.jpg", "img2.jpg", "img3.jpg"
    ]

    # Move two images to val and export again.
    second = _run_export(
        _images({"img0": "train", "img1": "train", "img2": "val", "img3": "val"}),
        job_id="job-2",
    )
    assert second["status"] == "completed", second.get("error")

    train = _split_contents(workspace, "train")
    val = _split_contents(workspace, "val")
    assert train == ["img0.jpg", "img1.jpg"]
    assert val == ["img2.jpg", "img3.jpg"]
    assert not set(train) & set(val), "an image is in both train and val"


def test_a_deleted_image_does_not_survive_in_the_export(workspace):
    _run_export(_images({f"img{i}": "train" for i in range(4)}))
    # img3 is removed from the dataset.
    second = _run_export(
        _images({"img0": "train", "img1": "train", "img2": "val"}), job_id="job-2"
    )
    assert second["status"] == "completed", second.get("error")
    everything = (
        _split_contents(workspace, "train")
        + _split_contents(workspace, "val")
        + _split_contents(workspace, "test")
    )
    assert "img3.jpg" not in everything


def test_augmented_copies_do_not_outlive_the_setting_that_made_them(workspace):
    images = _images({f"img{i}": "train" for i in range(4)})
    _run_export(images)
    export_jobs["job-aug"] = {"status": "pending", "progress": 0, "dataset_id": DATASET_ID}
    asyncio.run(
        _export_task(
            "job-aug", DATASET_ID, 0.8, {"noise": True},
            {"name": "testset", "classes": ["thing"]},
            images, images,
        )
    )
    assert any(n.startswith("aug_") for n in _split_contents(workspace, "train"))

    # Turn augmentation back off; the generated copies must be gone.
    third = _run_export(images, job_id="job-3")
    assert third["status"] == "completed", third.get("error")
    assert not any(n.startswith("aug_") for n in _split_contents(workspace, "train"))


# ── Ordinary behaviour still holds ───────────────────────────────────────────

def test_every_image_lands_in_exactly_one_split(workspace):
    result = _run_export(
        _images({"img0": "train", "img1": "train", "img2": "val", "img3": "test"})
    )
    assert result["status"] == "completed", result.get("error")
    names = (
        _split_contents(workspace, "train")
        + _split_contents(workspace, "val")
        + _split_contents(workspace, "test")
    )
    assert sorted(names) == ["img0.jpg", "img1.jpg", "img2.jpg", "img3.jpg"]
    assert len(names) == len(set(names))


def test_labels_travel_with_their_images(workspace):
    _run_export(_images({"img0": "train", "img1": "val", "img2": "val", "img3": "val"}))
    for split in ("train", "val"):
        imgs = _split_contents(workspace, split)
        labels = sorted(
            p.stem for p in (workspace / "split" / split / "labels").iterdir()
        )
        assert [os.path.splitext(i)[0] for i in imgs] == labels


def test_export_writes_a_yaml_and_a_zip(workspace):
    result = _run_export(_images({f"img{i}": "train" for i in range(4)}))
    assert (workspace / "data.yaml").exists()
    assert result["zip_path"].endswith(".zip")
    yaml_text = (workspace / "data.yaml").read_text()
    assert "train: train/images" in yaml_text


# ── Export status authorization ──────────────────────────────────────────────

def test_export_status_requires_access_to_the_dataset():
    """The old check compared caller input against caller input.

    `job.dataset_id == dataset_id` says nothing about whether the caller may
    see the dataset — it is satisfied by passing the job's own dataset_id.
    """
    import inspect

    from app.api.v1.endpoints.annotations import get_export_status

    source = inspect.getsource(get_export_status)
    assert "require_role" in source, "export-status performs no access check"
    assert source.index("require_role") < source.index("export_jobs[job_id]")


def test_export_status_does_not_leak_server_paths():
    """yaml_path and zip_path are absolute host paths; clients need neither."""
    import inspect

    from app.api.v1.endpoints.annotations import get_export_status

    source = inspect.getsource(get_export_status)
    assert "yaml_path" not in source.split("return")[-1]
    assert "zip_path" not in source.split("return")[-1]


def test_export_status_still_returns_what_the_client_reads():
    """DatasetsTab polls status, error and progress."""
    import inspect

    from app.api.v1.endpoints.annotations import get_export_status

    returned = inspect.getsource(get_export_status).split("return")[-1]
    for field in ("status", "progress", "error"):
        assert f'"{field}"' in returned
