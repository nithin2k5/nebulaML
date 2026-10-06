"""
The in-app assistant.

Two things matter here and neither involves the network. The conversation
window has to satisfy the API's "first message must be from the user" rule, or
every request 400s. And the project context has to survive missing or
malformed project data, because it is assembled from four independent sources
and any of them can be absent on a young project.
"""


import pytest

from app.services import assistant
from app.services.assistant import AssistantUnavailable

# --- conversation window ---------------------------------------------------


def test_the_window_keeps_both_roles_in_order():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "why is my mAP low"},
    ]
    assert assistant._conversation(messages) == messages


def test_a_window_starting_on_an_assistant_turn_is_trimmed():
    # The API rejects a conversation whose first message is from the
    # assistant, which is exactly what truncating a long history produces.
    messages = [
        {"role": "assistant", "content": "greeting"},
        {"role": "user", "content": "question"},
    ]
    assert assistant._conversation(messages) == [{"role": "user", "content": "question"}]


def test_only_the_recent_turns_are_sent():
    messages = [{"role": "user", "content": f"q{i}"} for i in range(40)]
    window = assistant._conversation(messages)
    assert len(window) == assistant.MAX_HISTORY_TURNS
    assert window[-1]["content"] == "q39"


def test_the_trimmed_window_still_starts_on_a_user_turn():
    # An even-length window of alternating roles can land on an assistant turn.
    messages = []
    for i in range(40):
        messages.append({"role": "user", "content": f"q{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    window = assistant._conversation(messages)
    assert window[0]["role"] == "user"


def test_blank_and_unknown_roles_are_dropped():
    messages = [
        {"role": "system", "content": "ignore me"},
        {"role": "user", "content": "   "},
        {"role": "user", "content": "real question"},
    ]
    assert assistant._conversation(messages) == [
        {"role": "user", "content": "real question"}
    ]


def test_an_empty_conversation_is_refused_before_any_api_call():
    with pytest.raises(AssistantUnavailable):
        assistant.answer([{"role": "assistant", "content": "only me"}])


# --- class balance summary -------------------------------------------------


def test_class_balance_lists_counts_descending():
    out = assistant._class_balance({"class_distribution": {"cat": 3, "dog": 40}})
    assert out == "Instances per class: dog: 40, cat: 3"


def test_class_balance_accepts_the_alternate_key():
    assert "dog: 2" in assistant._class_balance({"class_counts": {"dog": 2}})


def test_class_balance_trims_a_wide_distribution_to_both_ends():
    # The ends are what a question about imbalance is about; the middle is
    # just tokens.
    counts = {f"c{i}": i for i in range(40)}
    out = assistant._class_balance({"class_distribution": counts}, limit=4)
    assert "showing the 2 most and 2 least common of 40" in out
    assert "c39: 39" in out and "c0: 0" in out
    assert "c20" not in out


def test_class_balance_is_absent_when_there_is_nothing_to_say():
    assert assistant._class_balance({}) is None
    assert assistant._class_balance({"class_distribution": {}}) is None
    assert assistant._class_balance({"class_distribution": "not a dict"}) is None
    assert assistant._class_balance({"class_distribution": {"a": None}}) is None


# --- project context -------------------------------------------------------


@pytest.fixture
def _no_sources(monkeypatch):
    """Silence every context source; individual tests re-enable what they need."""
    monkeypatch.setattr(assistant.AnnotationService, "get_dataset_stats", lambda d: {})
    monkeypatch.setattr(
        assistant.DatasetVersionService, "list_dataset_versions", lambda d: []
    )
    monkeypatch.setattr(
        assistant.QualitySnapshotService, "get_latest_snapshot", lambda d: None
    )
    monkeypatch.setattr(assistant, "_latest_run", lambda d: None)


def _dataset(**overrides):
    base = {
        "id": "ds-1",
        "user_id": 1,
        "name": "Hard Hats",
        "classes": ["helmet", "head"],
        "total_images": 120,
        "annotated_images": 90,
    }
    base.update(overrides)
    return base


def test_context_is_empty_for_a_missing_dataset(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: None)
    assert assistant.build_project_context("nope") == ""


def test_context_reports_the_unlabelled_remainder(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())
    context = assistant.build_project_context("ds-1")
    assert "Hard Hats" in context
    assert "Classes (2): helmet, head" in context
    assert "120 uploaded, 90 annotated, 30 still unlabelled" in context


def test_a_young_project_says_it_has_no_versions_or_runs(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())
    context = assistant.build_project_context("ds-1")
    # Stating the absence is what lets the model answer "you can't train yet"
    # instead of assuming a version exists.
    assert "Frozen versions: none" in context
    assert "Latest run: none yet" in context


def test_context_includes_the_latest_versions_task(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())
    monkeypatch.setattr(
        assistant.DatasetVersionService,
        "list_dataset_versions",
        lambda d: [
            {"version_number": 1, "task": "detect", "total_images": 100},
            {"version_number": 2, "task": "segment", "total_images": 110},
        ],
    )
    context = assistant.build_project_context("ds-1")
    assert "latest is v2 (segment task, 110 images)" in context


def test_context_surfaces_a_completed_runs_metrics_and_weak_classes(
    _no_sources, monkeypatch
):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())
    monkeypatch.setattr(
        assistant,
        "_latest_run",
        lambda d: {
            "model_name": "yolov8s.pt",
            "status": "completed",
            "epochs": 100,
            "results": {
                "metrics": {"map50": 0.812, "recall": 0.74},
                "per_class_metrics": [
                    {"class_name": "helmet", "mAP50": 0.91},
                    {"class_name": "head", "mAP50": 0.31},
                ],
            },
        },
    )
    context = assistant.build_project_context("ds-1")
    assert "yolov8s.pt completed" in context
    assert "map50 0.812" in context
    # The weakest class is the answer to "why is my mAP low", so it is named.
    assert "Weakest classes by mAP50: head 0.310" in context


def test_context_surfaces_a_failed_runs_error(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())
    monkeypatch.setattr(
        assistant,
        "_latest_run",
        lambda d: {
            "model_name": "yolov8s.pt",
            "status": "failed",
            "epochs": 100,
            "results": {},
            "error_message": "CUDA out of memory",
        },
    )
    context = assistant.build_project_context("ds-1")
    assert "FAILED" in context and "CUDA out of memory" in context


def test_context_includes_health_findings(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())
    monkeypatch.setattr(
        assistant.QualitySnapshotService,
        "get_latest_snapshot",
        lambda d: {
            "overall_quality_score": 61.5,
            "duplicate_count": 12,
            "blurry_count": 0,
            "issues": ["class imbalance"],
        },
    )
    context = assistant.build_project_context("ds-1")
    assert "Health score: 61.5" in context
    assert "12 exact duplicates" in context
    # A zero count is not a finding and would only pad the prompt.
    assert "blurry" not in context
    assert "class imbalance" in context


def test_one_failing_source_does_not_lose_the_whole_context(_no_sources, monkeypatch):
    monkeypatch.setattr(assistant.DatasetService, "get_dataset", lambda d: _dataset())

    def boom(dataset_id):
        raise RuntimeError("Database connection unavailable")

    monkeypatch.setattr(assistant.AnnotationService, "get_dataset_stats", boom)
    monkeypatch.setattr(assistant.QualitySnapshotService, "get_latest_snapshot", boom)

    context = assistant.build_project_context("ds-1")
    assert "Hard Hats" in context
    assert "120 uploaded" in context


# --- fallback --------------------------------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("How do I train a model?", "frozen version"),
        ("how do I upload a dataset", "Upload tab"),
        ("annotate images", "Annotate tab"),
        ("deploy via api", "Deploy tab"),
        ("merge a class", "Classes tab"),
        ("my run failed", "Registry tab"),
        ("something else entirely", "uploading, annotating"),
    ],
)
def test_the_fallback_answers_the_questions_it_covers(question, expected):
    assert expected in assistant.rule_based_reply(question)


def test_the_fallback_no_longer_names_tabs_that_do_not_exist():
    # The original mock sent people to a "Monitor tab" for logs and a
    # "Help & Contact" tab, neither of which was ever a thing.
    for question in ["my run failed", "there is an error"]:
        reply = assistant.rule_based_reply(question)
        assert "Help & Contact" not in reply
        assert "Monitor tab" not in reply


def test_the_fallback_carries_no_note_of_its_own():
    # The caller appends the reason, because "no model configured" and "the
    # model could not be reached" are different and one trailing line cannot
    # be true for both.
    assert "(" not in assistant.rule_based_reply("how do I train")


def test_the_fallback_handles_an_empty_question():
    assert assistant.rule_based_reply("")
    assert assistant.rule_based_reply(None)


# --- configuration ---------------------------------------------------------


def test_configuration_is_detected_from_the_environment(monkeypatch):
    monkeypatch.setattr(assistant.settings, "anthropic_api_key", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert assistant.is_configured() is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert assistant.is_configured() is True


def test_configuration_can_come_from_settings(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(assistant.settings, "anthropic_api_key", "sk-ant-test")
    assert assistant.is_configured() is True


# --- request shape ---------------------------------------------------------


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Message:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.content = blocks
        self.stop_reason = stop_reason
        self.stop_details = None


def _captured_request(monkeypatch, response):
    """Call answer() against a stubbed client and return the request kwargs."""
    captured = {}

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return response

    class _Beta:
        messages = _Messages()

    class _Client:
        def __init__(self, **kwargs):
            self.beta = _Beta()

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    return captured


def test_project_context_is_appended_to_the_system_prompt(monkeypatch):
    captured = _captured_request(monkeypatch, _Message([_Block("answer")]))
    out = assistant.answer(
        [{"role": "user", "content": "why is my mAP low"}],
        "Project: Hard Hats\nHealth score: 61.5",
    )
    assert out == "answer"
    assert "PROJECT CONTEXT" in captured["system"]
    assert "Health score: 61.5" in captured["system"]
    # The platform description must survive alongside it.
    assert "NebulaML" in captured["system"]


def test_without_context_the_system_prompt_makes_no_project_claims(monkeypatch):
    # Telling the model to quote a project-context block that is not there
    # invites it to invent one, so the grounding half must be absent and
    # replaced by an instruction to answer generally.
    captured = _captured_request(monkeypatch, _Message([_Block("answer")]))
    assistant.answer([{"role": "user", "content": "what is mAP"}])
    assert "PROJECT CONTEXT" not in captured["system"]
    assert "no data about any specific project" in captured["system"]
    assert "NebulaML" in captured["system"]


def test_a_refusal_does_not_become_an_empty_answer(monkeypatch):
    _captured_request(monkeypatch, _Message([], stop_reason="refusal"))
    with pytest.raises(AssistantUnavailable, match="declined"):
        assistant.answer([{"role": "user", "content": "hi"}])


def test_an_empty_response_is_reported_rather_than_returned(monkeypatch):
    _captured_request(monkeypatch, _Message([_Block("   ")]))
    with pytest.raises(AssistantUnavailable, match="empty"):
        assistant.answer([{"role": "user", "content": "hi"}])


def test_multiple_text_blocks_are_joined(monkeypatch):
    _captured_request(monkeypatch, _Message([_Block("one"), _Block("two")]))
    assert assistant.answer([{"role": "user", "content": "hi"}]) == "one\ntwo"


def test_an_api_error_becomes_a_fallback_signal(monkeypatch):
    import anthropic

    class _Messages:
        def create(self, **kwargs):
            raise anthropic.APIConnectionError(request=None)

    class _Beta:
        messages = _Messages()

    class _Client:
        def __init__(self, **kwargs):
            self.beta = _Beta()

    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    # The endpoint turns this into a canned answer; it must not escape as a 500.
    with pytest.raises(AssistantUnavailable, match="Could not reach"):
        assistant.answer([{"role": "user", "content": "hi"}])
