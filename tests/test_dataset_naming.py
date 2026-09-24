"""Dataset names are labels, but they are also pasted into export filenames.

`Path(dir) / f"{name}_export.zip"` sanitises nothing, so an unvalidated name
was a path-traversal primitive. Two layers are tested here: rejection at the
model boundary, and a safe stem derived at every point of use (needed because
names already in the database never passed through the validator).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.annotations import Dataset, safe_name_stem


# ── safe_name_stem ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "hostile",
    [
        "../../../../tmp/pwned",
        "..\\..\\..\\windows\\temp\\x",
        "/etc/passwd",
        "....//....//etc",
        "..",
        ".",
        "",
        "   ",
        "./../.",
    ],
)
def test_hostile_names_cannot_escape_the_dataset_directory(hostile):
    stem = safe_name_stem(hostile)
    resolved = (Path("datasets/ds-id") / f"{stem}_export.zip").resolve()
    base = Path("datasets/ds-id").resolve()
    assert resolved.parent == base, f"{hostile!r} escaped to {resolved}"


@pytest.mark.parametrize("hostile", ["../../x", "/etc/passwd", "..", ""])
def test_safe_stem_never_contains_a_separator(hostile):
    stem = safe_name_stem(hostile)
    assert "/" not in stem and "\\" not in stem
    assert stem not in ("", ".", "..")


def test_ordinary_names_survive_intact():
    """Sanitising must not mangle the names people actually use."""
    assert safe_name_stem("Traffic Signs") == "Traffic Signs"
    assert safe_name_stem("road-signs_v2") == "road-signs_v2"
    assert safe_name_stem("dataset.2024") == "dataset.2024"


def test_unicode_names_are_kept():
    assert safe_name_stem("données") == "données"
    assert safe_name_stem("데이터셋") == "데이터셋"


def test_empty_result_falls_back_rather_than_producing_a_bare_suffix():
    assert safe_name_stem("...") == "dataset"
    assert safe_name_stem("///") == "dataset"


def test_stem_is_length_bounded():
    assert len(safe_name_stem("x" * 500)) <= 100


def test_null_bytes_are_stripped():
    stem = safe_name_stem("evil\x00.jpg")
    assert "\x00" not in stem


# ── Model validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "bad", ["../evil", "a/b", "a\\b", "", "   ", ".", "..", "x" * 101]
)
def test_dangerous_names_are_rejected_at_the_boundary(bad):
    with pytest.raises(ValidationError):
        Dataset(name=bad, classes=["thing"])


@pytest.mark.parametrize(
    "good", ["Traffic Signs", "road-signs_v2", "dataset.2024", "données"]
)
def test_reasonable_names_are_accepted(good):
    assert Dataset(name=good, classes=["thing"]).name == good


def test_names_are_trimmed():
    assert Dataset(name="  spaced  ", classes=["t"]).name == "spaced"


# ── The two layers agree ─────────────────────────────────────────────────────

def test_a_validated_name_is_unchanged_by_the_stem_helper():
    """Otherwise the write path and the read path would disagree on the file."""
    for name in ["Traffic Signs", "road-signs_v2", "dataset.2024"]:
        validated = Dataset(name=name, classes=["t"]).name
        assert safe_name_stem(validated) == validated
