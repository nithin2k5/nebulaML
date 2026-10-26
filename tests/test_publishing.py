"""Tests for publishing a dataset version behind a public link.

The payload tests matter most. A publication is the only anonymous path into
this application, so what leaves through it is pinned here: the allowlist is
asserted exactly, and a sentinel row carrying private columns proves nothing
rides along uninvited.
"""

import datetime
import json
import zipfile
from pathlib import Path

import pytest

from app.services import publishing

CLASSES = ["cat", "dog"]


def _publication(**overrides):
    row = {
        "id": "pub-internal-id",
        "slug": "s3cr3t-slug",
        "dataset_id": "dataset-uuid",
        "version_id": "version-uuid",
        "title": "Pets v3",
        "description": "Cats and dogs.",
        "license": "CC BY 4.0",
        "status": "live",
        "allow_downloads": True,
        "formats": ["yolo", "coco"],
        "view_count": 17,
        "download_count": 4,
        "published_by": 42,
        "published_at": datetime.datetime(2026, 10, 6, 12, 0, 0),
        "revoked_at": None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def snapshot(monkeypatch):
    """Two images with three boxes between them, no database."""
    rows = [
        {
            "filename": "a.jpg", "path": "/versions/v/train/images/a.jpg",
            "split": "train", "width": 100, "height": 100,
            "boxes": [
                {"class_id": 0, "bbox_normalized": [0.5, 0.5, 0.2, 0.2]},
                {"class_id": 1, "bbox_normalized": [0.25, 0.25, 0.1, 0.1]},
            ],
        },
        {
            "filename": "b.jpg", "path": "/versions/v/val/images/b.jpg",
            "split": "val", "width": 200, "height": 100,
            "boxes": [{"class_id": 0, "bbox_normalized": [0.5, 0.5, 0.5, 0.5]}],
        },
    ]
    monkeypatch.setattr(publishing, "_snapshot_rows", lambda version_id: rows)
    return rows


# ── Slugs ────────────────────────────────────────────────────────────────────


def test_slugs_are_unique_and_long():
    slugs = {publishing.new_slug() for _ in range(200)}
    assert len(slugs) == 200
    # 24 random bytes in urlsafe base64; the slug is the only credential.
    assert all(len(slug) >= 32 for slug in slugs)


def test_a_slug_is_url_safe():
    assert all(c.isalnum() or c in "-_" for c in publishing.new_slug())


def test_a_slug_is_not_derived_from_any_identifier():
    """It must not be a version id, or a leaked id becomes a download."""
    assert publishing.new_slug() != publishing.new_slug()


# ── The public payload ───────────────────────────────────────────────────────


def test_payload_exposes_exactly_the_allowlisted_keys(snapshot):
    payload = publishing.public_payload(_publication(), {"classes": CLASSES})
    assert set(payload) == {
        "slug", "title", "description", "license", "published_at",
        "downloads_enabled", "formats", "summary",
    }


def test_payload_never_carries_internal_identifiers(snapshot):
    payload = publishing.public_payload(_publication(), {"classes": CLASSES})
    flat = json.dumps(payload)
    for secret in ("dataset-uuid", "version-uuid", "pub-internal-id", "42"):
        assert secret not in flat, f"{secret} leaked into the public payload"


def test_a_column_added_later_is_private_by_default(snapshot):
    """The allowlist must not pass through fields nobody vetted."""
    row = _publication(
        internal_notes="the client is unhappy",
        uploader_email="someone@example.com",
    )
    payload = publishing.public_payload(row, {"classes": CLASSES})
    flat = json.dumps(payload)
    assert "unhappy" not in flat
    assert "example.com" not in flat


def test_payload_does_not_leak_the_project_name(snapshot):
    """Only the chosen title is published, not what the project is called."""
    payload = publishing.public_payload(
        _publication(), {"classes": CLASSES, "name": "Internal Client Pets"}
    )
    assert "Internal Client" not in json.dumps(payload)


def test_payload_hides_view_and_download_counts(snapshot):
    payload = publishing.public_payload(_publication(), {"classes": CLASSES})
    assert "view_count" not in payload
    assert "download_count" not in payload


def test_disabling_downloads_offers_no_formats(snapshot):
    payload = publishing.public_payload(
        _publication(allow_downloads=False), {"classes": CLASSES}
    )
    assert payload["downloads_enabled"] is False
    assert payload["formats"] == []


def test_an_unknown_format_is_dropped_from_the_payload(snapshot):
    payload = publishing.public_payload(
        _publication(formats=["yolo", "../../etc/passwd", "parquet"]),
        {"classes": CLASSES},
    )
    assert payload["formats"] == ["yolo"]


def test_formats_stored_as_json_text_are_decoded(snapshot):
    payload = publishing.public_payload(
        _publication(formats='["coco"]'), {"classes": CLASSES}
    )
    assert payload["formats"] == ["coco"]


def test_malformed_formats_degrade_to_none_offered(snapshot):
    payload = publishing.public_payload(
        _publication(formats="{not json"), {"classes": CLASSES}
    )
    assert payload["formats"] == []


# ── Summary ──────────────────────────────────────────────────────────────────


def test_summary_counts_images_boxes_and_splits(snapshot):
    summary = publishing.summarise_version("v", CLASSES)
    assert summary["total_images"] == 2
    assert summary["total_boxes"] == 3
    assert summary["splits"] == {"train": 1, "val": 1}


def test_summary_counts_boxes_per_class(snapshot):
    summary = publishing.summarise_version("v", CLASSES)
    assert summary["classes"] == [
        {"name": "cat", "boxes": 2},
        {"name": "dog", "boxes": 1},
    ]


def test_summary_ignores_a_class_id_outside_the_schema(monkeypatch):
    monkeypatch.setattr(
        publishing, "_snapshot_rows",
        lambda version_id: [{
            "filename": "a.jpg", "path": "/p/a.jpg", "split": "train",
            "width": 10, "height": 10,
            "boxes": [{"class_id": 99, "bbox_normalized": [0.5, 0.5, 0.2, 0.2]}],
        }],
    )
    summary = publishing.summarise_version("v", CLASSES)
    # Counted in the total, attributed to no class.
    assert summary["total_boxes"] == 1
    assert all(entry["boxes"] == 0 for entry in summary["classes"])


def test_preview_count_is_capped(monkeypatch):
    many = [
        {"filename": f"{i}.jpg", "path": f"/p/{i}.jpg", "split": "train",
         "width": 10, "height": 10, "boxes": []}
        for i in range(50)
    ]
    monkeypatch.setattr(publishing, "_snapshot_rows", lambda version_id: many)
    assert publishing.summarise_version("v", CLASSES)["preview_count"] == publishing.MAX_PREVIEWS


# ── Preview images ───────────────────────────────────────────────────────────


def test_an_out_of_range_index_resolves_to_nothing(snapshot):
    assert publishing.image_path_at("v", 99) is None
    assert publishing.image_path_at("v", -1) is None


def test_a_path_outside_the_versions_tree_is_refused(monkeypatch, tmp_path):
    """The rows are ours, but this is where a request becomes a file read."""
    outside = tmp_path / "secrets.env"
    outside.write_text("SECRET_KEY=hunter2")
    monkeypatch.setattr(
        publishing, "_snapshot_rows",
        lambda version_id: [{
            "filename": "a.jpg", "path": str(outside), "split": "train",
            "width": 10, "height": 10, "boxes": [],
        }],
    )
    assert publishing.image_path_at("v", 0) is None


def test_a_real_file_inside_the_tree_resolves(monkeypatch, tmp_path):
    versions = tmp_path / "versions"
    image = versions / "v" / "train" / "images" / "a.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(publishing, "VERSIONS_DIR", versions)
    monkeypatch.setattr(
        publishing, "_snapshot_rows",
        lambda version_id: [{
            "filename": "a.jpg", "path": str(image), "split": "train",
            "width": 10, "height": 10, "boxes": [],
        }],
    )
    assert publishing.image_path_at("v", 0) == image.resolve()


# ── COCO conversion ──────────────────────────────────────────────────────────


def test_coco_converts_normalised_centres_to_absolute_corners(snapshot):
    coco = publishing.coco_from_snapshot("v", CLASSES, "Pets v3")
    first = next(a for a in coco["annotations"] if a["image_id"] == 1)
    # cx .5 cy .5 w .2 h .2 on 100x100 -> x 40, y 40, w 20, h 20.
    assert first["bbox"] == [40.0, 40.0, 20.0, 20.0]
    assert first["area"] == 400.0


def test_coco_converts_against_each_image_own_size(snapshot):
    """A version's images are not all the same shape after preprocessing."""
    coco = publishing.coco_from_snapshot("v", CLASSES, "Pets v3")
    second = next(a for a in coco["annotations"] if a["image_id"] == 2)
    # 200x100 image, w .5 h .5 -> 100 x 50.
    assert second["bbox"] == [50.0, 25.0, 100.0, 50.0]


def test_coco_category_ids_are_one_based(snapshot):
    coco = publishing.coco_from_snapshot("v", CLASSES, "Pets v3")
    assert coco["categories"] == [
        {"id": 1, "name": "cat", "supercategory": "none"},
        {"id": 2, "name": "dog", "supercategory": "none"},
    ]
    # class_id 0 ("cat") must become category 1, not 0.
    assert {a["category_id"] for a in coco["annotations"]} == {1, 2}


def test_coco_annotation_ids_are_unique(snapshot):
    coco = publishing.coco_from_snapshot("v", CLASSES, "Pets v3")
    ids = [a["id"] for a in coco["annotations"]]
    assert len(ids) == len(set(ids)) == 3


def test_coco_keeps_an_image_with_no_boxes(monkeypatch):
    monkeypatch.setattr(
        publishing, "_snapshot_rows",
        lambda version_id: [{
            "filename": "empty.jpg", "path": "/p/empty.jpg", "split": "train",
            "width": 10, "height": 10, "boxes": [],
        }],
    )
    coco = publishing.coco_from_snapshot("v", CLASSES, "t")
    assert len(coco["images"]) == 1
    assert coco["annotations"] == []


# ── Archives ─────────────────────────────────────────────────────────────────


def test_an_unknown_format_builds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(publishing, "VERSIONS_DIR", tmp_path)
    assert publishing.build_archive("s", "v", CLASSES, "t", "parquet") is None


def test_a_missing_snapshot_builds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(publishing, "VERSIONS_DIR", tmp_path)
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")
    assert publishing.build_archive("s", "absent", CLASSES, "t", "yolo") is None


def test_the_yolo_archive_is_the_snapshot_as_it_sits_on_disk(tmp_path, monkeypatch):
    """Published form equals what training consumed — a zip, not a conversion."""
    versions = tmp_path / "versions"
    version_dir = versions / "v"
    (version_dir / "train" / "images").mkdir(parents=True)
    (version_dir / "train" / "labels").mkdir(parents=True)
    (version_dir / "train" / "images" / "a.jpg").write_bytes(b"\xff\xd8\xff")
    (version_dir / "train" / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    (version_dir / "data.yaml").write_text("nc: 2\n")

    monkeypatch.setattr(publishing, "VERSIONS_DIR", versions)
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")

    archive = publishing.build_archive("slug1", "v", CLASSES, "t", "yolo")
    assert archive is not None and archive.exists()
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == [
            "data.yaml", "train/images/a.jpg", "train/labels/a.txt",
        ]


def test_an_archive_is_built_once_and_reused(tmp_path, monkeypatch):
    """A public link can be fetched by anyone, repeatedly."""
    versions = tmp_path / "versions"
    (versions / "v").mkdir(parents=True)
    (versions / "v" / "data.yaml").write_text("nc: 2\n")
    monkeypatch.setattr(publishing, "VERSIONS_DIR", versions)
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")

    first = publishing.build_archive("slug2", "v", CLASSES, "t", "yolo")
    stamp = first.stat().st_mtime_ns
    second = publishing.build_archive("slug2", "v", CLASSES, "t", "yolo")
    assert second == first
    assert second.stat().st_mtime_ns == stamp


def test_no_partial_archive_is_left_in_the_cache(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    (versions / "v").mkdir(parents=True)
    (versions / "v" / "data.yaml").write_text("nc: 1\n")
    monkeypatch.setattr(publishing, "VERSIONS_DIR", versions)
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")

    publishing.build_archive("slug3", "v", CLASSES, "t", "yolo")
    leftovers = list((tmp_path / "pubs" / "slug3").glob("*.partial"))
    assert leftovers == []


def test_the_coco_archive_is_valid_json(tmp_path, monkeypatch, snapshot):
    versions = tmp_path / "versions"
    (versions / "v").mkdir(parents=True)
    monkeypatch.setattr(publishing, "VERSIONS_DIR", versions)
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")

    archive = publishing.build_archive("slug4", "v", CLASSES, "Pets", "coco")
    payload = json.loads(Path(archive).read_text())
    assert payload["info"]["description"] == "Pets"
    assert len(payload["images"]) == 2


def test_revoking_clears_the_cached_archives(tmp_path, monkeypatch):
    versions = tmp_path / "versions"
    (versions / "v").mkdir(parents=True)
    (versions / "v" / "data.yaml").write_text("nc: 1\n")
    monkeypatch.setattr(publishing, "VERSIONS_DIR", versions)
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")

    publishing.build_archive("slug5", "v", CLASSES, "t", "yolo")
    assert (tmp_path / "pubs" / "slug5").exists()

    publishing.discard_archives("slug5")
    assert not (tmp_path / "pubs" / "slug5").exists()


def test_discarding_archives_that_never_existed_is_harmless(tmp_path, monkeypatch):
    monkeypatch.setattr(publishing, "PUBLICATIONS_DIR", tmp_path / "pubs")
    publishing.discard_archives("never-published")
