"""Ownership boundaries on the models API.

Trained runs live on disk at runs/detect/job_<job_id> and carry no owner of
their own. Every endpoint here therefore has to resolve the directory name back
to a training_jobs row. Before this was wired up, any signed-in user could list,
download, export and rmtree every model on the box.
"""

from unittest.mock import patch

import pytest

from app.api.v1.endpoints import models


ALICE = {"id": 1, "username": "alice", "role": "user"}
BOB = {"id": 2, "username": "bob", "role": "user"}
ADMIN = {"id": 9, "username": "root", "role": "admin"}


@pytest.fixture
def owned_by_alice():
    """job_aaa belongs to Alice; anything else resolves to no owner."""
    def fake_owner(job_id):
        return 1 if job_id == "aaa" else None

    with patch.object(
        models.TrainingJobService, "get_job_owner", side_effect=fake_owner
    ):
        yield


# ── _owner_of_model ──────────────────────────────────────────────────────────

def test_owner_is_resolved_from_the_run_directory_name(owned_by_alice):
    assert models._owner_of_model("job_aaa") == 1


def test_directory_outside_the_naming_convention_has_no_owner(owned_by_alice):
    """A hand-made or legacy directory must not resolve to somebody."""
    assert models._owner_of_model("some_random_dir") is None
    assert models._owner_of_model("job_") is None


def test_missing_job_row_has_no_owner(owned_by_alice):
    assert models._owner_of_model("job_deleted") is None


# ── _require_model_access ────────────────────────────────────────────────────

def test_owner_may_access_their_own_model(owned_by_alice):
    models._require_model_access("job_aaa", ALICE)  # must not raise


def test_another_user_is_refused(owned_by_alice):
    with pytest.raises(models.HTTPException) as exc:
        models._require_model_access("job_aaa", BOB)
    assert exc.value.status_code == 404


def test_refusal_does_not_confirm_the_model_exists(owned_by_alice):
    """404 not 403: a 403 would leak that the name is real."""
    with pytest.raises(models.HTTPException) as real:
        models._require_model_access("job_aaa", BOB)
    with pytest.raises(models.HTTPException) as fake:
        models._require_model_access("job_nonexistent", BOB)
    assert real.value.status_code == fake.value.status_code == 404
    assert real.value.detail == fake.value.detail


def test_unresolvable_owner_fails_closed(owned_by_alice):
    """An unrecognised directory layout must not become world-readable."""
    with pytest.raises(models.HTTPException):
        models._require_model_access("stray_dir", ALICE)


def test_admin_may_access_anything(owned_by_alice):
    models._require_model_access("job_aaa", ADMIN)
    models._require_model_access("stray_dir", ADMIN)


# ── every destructive endpoint is gated ──────────────────────────────────────

@pytest.mark.parametrize(
    "endpoint", ["download_model", "delete_model", "get_model_info", "export_model"]
)
def test_every_per_model_endpoint_checks_access(endpoint):
    """Guards the wiring itself: a new endpoint that forgets the call fails here."""
    import inspect

    source = inspect.getsource(getattr(models, endpoint))
    assert "_require_model_access(model_name, current_user)" in source, (
        f"{endpoint} touches a model without an ownership check"
    )


def test_access_check_precedes_filesystem_resolution():
    """Checking after rmtree would be no check at all."""
    import inspect

    source = inspect.getsource(models.delete_model)
    assert source.index("_require_model_access") < source.index("get_safe_model_dir")
    assert source.index("_require_model_access") < source.index("rmtree")


def test_listing_filters_by_owner():
    import inspect

    source = inspect.getsource(models.list_models)
    assert "get_job_ids_for_user" in source
    assert "own_job_ids" in source
