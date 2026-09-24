"""Access control on the training endpoints.

Every route that starts a job or exposes one has to answer two questions: may
this caller use this dataset, and may they see this job. Three of the four
start paths asked the first; /start-micro did not.
"""

import inspect

import pytest

from app.api.v1.endpoints import training


ALICE = {"id": 1, "username": "alice", "role": "user"}
BOB = {"id": 2, "username": "bob", "role": "user"}
ADMIN = {"id": 9, "username": "root", "role": "admin"}


# ── Job visibility ───────────────────────────────────────────────────────────

def test_owner_sees_their_own_job():
    assert training._job_owner_ok({"user_id": 1}, ALICE) is True


def test_other_users_do_not_see_it():
    assert training._job_owner_ok({"user_id": 1}, BOB) is False


def test_unowned_job_is_not_visible_to_everyone():
    """This returned True — a fail-open default in an auth function."""
    assert training._job_owner_ok({"user_id": None}, ALICE) is False
    assert training._job_owner_ok({}, ALICE) is False


def test_unowned_job_is_still_reachable_by_an_admin():
    """Legacy rows must stay addressable by someone, or they are unmanageable."""
    assert training._job_owner_ok({"user_id": None}, ADMIN) is True


def test_listing_and_single_job_use_the_same_rule():
    """Two copies of an auth rule drift; the listing must call the helper."""
    source = inspect.getsource(training.list_training_jobs)
    assert "_job_owner_ok" in source
    assert "is None" not in source, "listing re-implements the ownership rule"


# ── Start paths ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "endpoint",
    ["start_micro_training", "start_training_from_dataset", "export_and_train"],
)
def test_every_dataset_start_path_checks_dataset_access(endpoint):
    """/start takes an uploaded YAML and has no dataset_id, so it is excluded."""
    source = inspect.getsource(getattr(training, endpoint))
    assert "require_role" in source, f"{endpoint} starts training with no access check"


def test_start_micro_checks_access_before_touching_the_path():
    """dataset_id goes into an f-string path; validate it before using it."""
    source = inspect.getsource(training.start_micro_training)
    assert source.index("require_role") < source.index('f"datasets/{dataset_id}')


def test_start_micro_checks_access_before_consuming_a_queue_slot():
    source = inspect.getsource(training.start_micro_training)
    assert source.index("require_role") < source.index("_assert_capacity()")


@pytest.mark.parametrize(
    "endpoint",
    [
        "start_training",
        "start_micro_training",
        "start_training_from_dataset",
        "export_and_train",
    ],
)
def test_every_start_path_enforces_the_queue_cap(endpoint):
    source = inspect.getsource(getattr(training, endpoint))
    assert "_assert_capacity()" in source


# ── Per-job endpoints ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "endpoint",
    [
        "get_training_status",
        "get_training_job_by_id",
        "cancel_training_job",
        "delete_training_job",
        "get_training_metrics",
        "get_confusion_matrix",
        "get_per_class_metrics",
    ],
)
def test_per_job_endpoints_resolve_through_the_owner_check(endpoint):
    source = inspect.getsource(getattr(training, endpoint))
    assert "_get_owned_job" in source or "_job_owner_ok" in source, (
        f"{endpoint} reads a job without an ownership check"
    )


# ── No anonymous endpoints ───────────────────────────────────────────────────

def test_no_training_endpoint_is_anonymous():
    """Every route on this router should require a caller.

    /model-registry and /presets took no auth dependency. They return static
    catalogue data rather than user data, so nothing leaked — but an
    unauthenticated route on an otherwise authenticated router is a default
    worth not having.
    """
    anonymous = []
    for route in training.router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        params = inspect.signature(endpoint).parameters
        if "current_user" not in params:
            anonymous.append(getattr(route, "path", endpoint.__name__))
    assert not anonymous, f"training endpoints with no caller: {anonymous}"
