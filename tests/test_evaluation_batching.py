"""Tests for the batched inference path in the evaluation workbench.

Scoring used to call `model.predict` once per image with the YOLO backend
hardcoded. These cover what replaced it: batching with a per-image fallback,
and resolving the backend from the training job.
"""

import inspect

import pytest

from app.api.v1.endpoints import evaluation as ev


class FakeModel:
    """Records how it was called so the batching path can be asserted on."""

    def __init__(self, batch_result=None, batch_error=None, failing_paths=()):
        self.batch_result = batch_result
        self.batch_error = batch_error
        self.failing_paths = set(failing_paths)
        self.batch_calls = []
        self.single_calls = []

    def predict_batch(self, paths, conf_threshold=None, **kwargs):
        self.batch_calls.append((list(paths), conf_threshold))
        if self.batch_error:
            raise self.batch_error
        if self.batch_result is not None:
            return self.batch_result
        return [[{"bbox": [0, 0, 1, 1], "confidence": 0.9, "class_id": 0}] for _ in paths]

    def predict(self, path, conf_threshold=None, **kwargs):
        self.single_calls.append((path, conf_threshold))
        if path in self.failing_paths:
            raise RuntimeError("unreadable")
        return [{"bbox": [1, 1, 2, 2], "confidence": 0.5, "class_id": 1}]


def test_batch_is_one_call_for_the_whole_batch():
    """The point of batching: sixteen images, one forward pass."""
    model = FakeModel()
    paths = [f"/img{i}.jpg" for i in range(4)]

    results = ev._predict_batch(model, paths)

    assert len(results) == 4
    assert len(model.batch_calls) == 1
    assert model.single_calls == []


def test_batch_predicts_at_the_metric_floor_not_the_operating_point():
    """mAP needs the full curve, so inference runs well below conf_threshold."""
    model = FakeModel()
    ev._predict_batch(model, ["/img0.jpg"])
    assert model.batch_calls[0][1] == ev._SCORE_FLOOR
    assert ev._SCORE_FLOOR < 0.25


def test_results_stay_aligned_with_their_paths():
    model = FakeModel(batch_result=[["a"], ["b"], ["c"]])
    assert ev._predict_batch(model, ["/0.jpg", "/1.jpg", "/2.jpg"]) == [["a"], ["b"], ["c"]]


def test_a_short_backend_result_is_padded_not_zipped_short():
    """Zipping a short list against the images would score the wrong files."""
    model = FakeModel(batch_result=[["only-one"]])
    results = ev._predict_batch(model, ["/0.jpg", "/1.jpg", "/2.jpg"])
    assert results == [["only-one"], None, None]


def test_an_overlong_backend_result_is_truncated():
    model = FakeModel(batch_result=[["a"], ["b"], ["c"]])
    assert ev._predict_batch(model, ["/0.jpg"]) == [["a"]]


def test_a_failed_batch_retries_one_image_at_a_time():
    """One unreadable file must not cost the other fifteen images."""
    model = FakeModel(batch_error=RuntimeError("CUDA hiccup"))
    paths = ["/0.jpg", "/1.jpg", "/2.jpg"]

    results = ev._predict_batch(model, paths)

    assert len(model.single_calls) == 3
    assert all(result is not None for result in results)


def test_an_image_that_fails_even_alone_comes_back_as_none():
    model = FakeModel(batch_error=RuntimeError("boom"), failing_paths={"/1.jpg"})
    results = ev._predict_batch(model, ["/0.jpg", "/1.jpg", "/2.jpg"])
    assert results[1] is None
    assert results[0] is not None and results[2] is not None


def test_empty_batch_is_a_no_op():
    model = FakeModel(batch_result=[])
    assert ev._predict_batch(model, []) == []


# ── Backend resolution ───────────────────────────────────────────────────────


def _code_only(source: str) -> str:
    """Drop comment lines, so a comment mentioning a name is not a usage of it."""
    return "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )


def test_scoring_resolves_the_backend_from_the_job():
    """An RT-DETR or torchvision checkpoint is not loadable by YOLOInference.

    Asserted on the source because the alternative — standing up a real
    evaluation — needs a database and a checkpoint. The failure this guards
    against is a silent reintroduction of the hardcoded backend.
    """
    code = _code_only(inspect.getsource(ev._evaluate_task))
    assert "create_inference" in code
    assert "YOLOInference" not in code


def test_the_module_does_not_import_yolo_inference_directly():
    code = _code_only(inspect.getsource(ev))
    assert "from app.services.inference import YOLOInference" not in code


@pytest.mark.parametrize("backend", ["yolo", "rtdetr", "torchvision"])
def test_every_registered_backend_has_an_inference_engine(backend):
    """Resolution is only useful if each backend can actually be built."""
    from app.services.trainer_factory import create_inference

    # Reaching the import of a real engine proves the branch exists; the
    # checkpoint itself is what fails, not the dispatch.
    with pytest.raises(Exception) as excinfo:
        create_inference("/nonexistent/best.pt", backend)
    assert "Unknown model type" not in str(excinfo.value)
