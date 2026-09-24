"""ZIP dataset import.

DatasetImporter was fully implemented but had no route in front of it, and the
Upload tab called a URL built from two config keys that do not exist. These
cover the archive guards the endpoint now depends on, and pin the wiring so it
cannot come apart again.
"""

import zipfile

import pytest

from app.services import dataset_importer
from app.services.dataset_importer import (

    ZipTooLarge,
    _assert_archive_is_sane,
)

def _archive(entries, path):
    """entries: {name: bytes}"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path

# ── Bomb guards ──────────────────────────────────────────────────────────────

def test_an_ordinary_dataset_archive_passes(tmp_path):
    path = _archive(
        {f"images/img{i}.jpg": b"\xff\xd8" + b"x" * 500 for i in range(20)},
        tmp_path / "ds.zip",
    )
    with zipfile.ZipFile(path) as zf:
        _assert_archive_is_sane(zf)  # must not raise

def test_a_flat_decompression_bomb_is_rejected(tmp_path):
    """A few KB on disk declaring hundreds of MB of zeroes."""
    path = _archive({"bomb.bin": b"\x00" * (200 * 1024 * 1024)}, tmp_path / "bomb.zip")
    assert path.stat().st_size < 1024 * 1024, "test archive should be tiny"
    with zipfile.ZipFile(path) as zf:
        with pytest.raises(ZipTooLarge) as exc:
            _assert_archive_is_sane(zf)
    assert "bomb" in str(exc.value).lower()

def test_too_many_members_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_importer, "MAX_MEMBERS", 5)
    path = _archive({f"f{i}.txt": b"x" for i in range(10)}, tmp_path / "many.zip")
    with zipfile.ZipFile(path) as zf:
        with pytest.raises(ZipTooLarge) as exc:
            _assert_archive_is_sane(zf)
    assert "entries" in str(exc.value)

def test_total_size_cap_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset_importer, "MAX_UNCOMPRESSED_BYTES", 1024)
    path = _archive({"big.bin": b"x" * 8192}, tmp_path / "big.zip")
    with zipfile.ZipFile(path) as zf:
        with pytest.raises(ZipTooLarge):
            _assert_archive_is_sane(zf)

def test_a_small_but_highly_compressible_file_is_not_flagged(tmp_path):
    """The ratio rule must not reject a legitimately compressible small file."""
    path = _archive({"labels.txt": b"0 0.5 0.5 0.1 0.1\n" * 5000}, tmp_path / "s.zip")
    with zipfile.ZipFile(path) as zf:
        _assert_archive_is_sane(zf)  # under the size floor, so ratio is ignored

def test_guard_runs_before_extraction(tmp_path):
    """Checking after extractall would defeat the purpose."""
    import inspect

    source = inspect.getsource(dataset_importer.DatasetImporter.import_zip)
    assert source.index("_assert_archive_is_sane") < source.index("extractall")

def test_a_corrupt_archive_is_reported_as_such():
    """"Not a valid zip archive" beats leaking a raw exception string."""
    import inspect

    source = inspect.getsource(dataset_importer.DatasetImporter.import_zip)
    assert "zipfile.BadZipFile" in source
    assert source.index("ZipTooLarge") < source.index("except Exception")

# ── Wiring ───────────────────────────────────────────────────────────────────

def test_the_import_route_exists():
    """It did not, for the entire life of the Upload tab's import control."""
    from main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/annotations/datasets/{dataset_id}/import" in paths

def test_the_endpoint_checks_dataset_access():
    import inspect

    from app.api.v1.endpoints.annotations import import_dataset

    source = inspect.getsource(import_dataset)
    assert "require_role" in source
    assert source.index("require_role") < source.index("DatasetImporter.import_zip")

def test_the_endpoint_validates_the_format():
    import inspect

    from app.api.v1.endpoints.annotations import import_dataset

    source = inspect.getsource(import_dataset)
    assert '("yolo", "coco")' in source

def test_the_endpoint_always_removes_its_temp_file():
    import inspect

    from app.api.v1.endpoints.annotations import import_dataset

    source = inspect.getsource(import_dataset)
    assert "finally:" in source
    assert source.index("finally:") < source.index("os.unlink")

def test_the_client_url_resolves():
    """Both halves of the old `a || b` fallback were undefined."""
    from pathlib import Path

    config = Path("client/src/lib/config.js").read_text()
    component = Path("client/src/components/project/ProjectUpload.js").read_text()

    assert "IMPORT: (id) =>" in config
    assert "API_ENDPOINTS.DATASETS.IMPORT(dataset.id)" in component
    assert "API_ENDPOINTS.BASE_URL" not in component, "undefined key still referenced"
    assert "DATASETS.BASE " not in component
