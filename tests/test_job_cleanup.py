"""Cleanup of the scratch state a job leaves behind.

Two append-only structures and one temp directory, none of which anything ever
removed: a long-running process grew a dict entry per export and per auto-label
run, and /tmp/yolo_training collected a directory per training job — including,
for export-and-train, a whole filtered copy of the dataset.
"""

import tempfile
from pathlib import Path

import pytest

from app.api.v1.endpoints.annotations import _prune_finished_jobs
from app.api.v1.endpoints import training


# ── In-memory job dicts ──────────────────────────────────────────────────────

def _jobs(**statuses):
    return {job_id: {"status": status} for job_id, status in statuses.items()}


def test_running_jobs_are_never_pruned():
    jobs = _jobs(a="running", b="pending", c="completed")
    _prune_finished_jobs(jobs, keep=0)
    assert set(jobs) == {"a", "b"}


def test_finished_jobs_beyond_the_retention_tail_are_dropped():
    jobs = {str(i): {"status": "completed"} for i in range(10)}
    _prune_finished_jobs(jobs, keep=3)
    assert list(jobs) == ["7", "8", "9"], "should keep the most recent three"


def test_a_recent_result_survives_long_enough_to_be_polled():
    """Deleting on completion would race the client's next poll."""
    jobs = {"old": {"status": "completed"}, "just_done": {"status": "completed"}}
    _prune_finished_jobs(jobs, keep=1)
    assert "just_done" in jobs


def test_failed_jobs_are_pruned_like_completed_ones():
    jobs = {str(i): {"status": "failed"} for i in range(5)}
    _prune_finished_jobs(jobs, keep=2)
    assert len(jobs) == 2


def test_pruning_an_empty_or_all_running_dict_is_a_no_op():
    empty = {}
    _prune_finished_jobs(empty)
    assert empty == {}

    busy = _jobs(a="running", b="running")
    _prune_finished_jobs(busy, keep=0)
    assert len(busy) == 2


def test_new_jobs_trigger_a_prune():
    """The prune has to run somewhere; registration is the growth point."""
    import inspect

    from app.api.v1.endpoints import annotations

    for fn in (annotations.export_dataset, annotations.auto_label_images):
        assert "_prune_finished_jobs" in inspect.getsource(fn), (
            f"{fn.__name__} registers a job without pruning"
        )


# ── Training workspace ───────────────────────────────────────────────────────

def test_workspace_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "_JOB_WORKSPACE_ROOT", tmp_path)
    workspace = tmp_path / "job-1"
    (workspace / "nested").mkdir(parents=True)
    (workspace / "data.yaml").write_text("path: /x")
    (workspace / "nested" / "img.jpg").write_bytes(b"\xff\xd8")

    training._cleanup_job_workspace("job-1")
    assert not workspace.exists()


def test_cleanup_of_a_missing_workspace_is_harmless(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "_JOB_WORKSPACE_ROOT", tmp_path)
    training._cleanup_job_workspace("never-existed")


def test_cleanup_does_not_touch_sibling_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "_JOB_WORKSPACE_ROOT", tmp_path)
    (tmp_path / "job-1").mkdir()
    (tmp_path / "job-2").mkdir()
    training._cleanup_job_workspace("job-1")
    assert not (tmp_path / "job-1").exists()
    assert (tmp_path / "job-2").exists()


def test_workspace_root_matches_where_jobs_actually_stage(tmp_path):
    """The cleanup path must be the same one start_training writes to."""
    import inspect

    source = inspect.getsource(training.start_training)
    assert 'Path(tempfile.gettempdir()) / "yolo_training"' in source
    assert training._JOB_WORKSPACE_ROOT == Path(tempfile.gettempdir()) / "yolo_training"


@pytest.mark.parametrize("fn_name", ["run_training", "delete_training_job"])
def test_both_exit_paths_clean_up(fn_name):
    import inspect

    source = inspect.getsource(getattr(training, fn_name))
    assert "_cleanup_job_workspace" in source


def test_run_training_cleans_up_in_the_finally():
    """A crashed run must not keep its scratch copy of the dataset."""
    import inspect

    source = inspect.getsource(training.run_training)
    assert source.index("finally:") < source.index("_cleanup_job_workspace")
