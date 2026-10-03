"""Unit tests for the embedding primitives behind semantic search.

None of these load CLIP. The model is a runtime download, so a test that
needed it would fail on any machine without network — and the parts worth
guarding (vector packing, similarity ranking, clustering, diversity sampling)
are plain numpy anyway.
"""

import numpy as np
import pytest
from app.services import embeddings


def _unit(*components):
    """Build a normalised row vector from raw components."""
    vector = np.asarray(components, dtype="float32")
    return vector / np.linalg.norm(vector)


# ---------------------------------------------------------------------------
# Vector packing
# ---------------------------------------------------------------------------

def test_vector_survives_a_blob_round_trip():
    original = _unit(0.3, -0.7, 0.2, 0.9)
    restored = embeddings.blob_to_vector(embeddings.vector_to_blob(original))
    assert restored is not None
    np.testing.assert_allclose(restored, original, rtol=1e-6)


def test_empty_blob_decodes_to_none_rather_than_raising():
    """A NULL/empty vector column must not take down a whole dataset load."""
    assert embeddings.blob_to_vector(b"") is None
    assert embeddings.blob_to_vector(None) is None


def test_stack_vectors_drops_rows_from_a_different_model():
    """Mixing dims would make the similarity matmul fail; minority dims lose."""
    rows = [
        ("a", embeddings.vector_to_blob(_unit(1, 0, 0, 0))),
        ("b", embeddings.vector_to_blob(_unit(0, 1, 0, 0))),
        ("c", embeddings.vector_to_blob(_unit(0, 0, 1, 0))),
        # A leftover from a model with a narrower output.
        ("stale", embeddings.vector_to_blob(_unit(1, 0))),
    ]
    ids, matrix = embeddings.stack_vectors(rows)

    assert ids == ["a", "b", "c"]
    assert matrix.shape == (3, 4)
    assert "stale" not in ids


def test_stack_vectors_handles_an_empty_table():
    ids, matrix = embeddings.stack_vectors([])
    assert ids == []
    assert matrix is None


# ---------------------------------------------------------------------------
# Similarity ranking
# ---------------------------------------------------------------------------

def test_rank_by_similarity_orders_by_cosine_descending():
    matrix = np.vstack([
        _unit(1, 0, 0),      # identical to the query
        _unit(0.8, 0.6, 0),  # close
        _unit(0, 1, 0),      # orthogonal
    ])
    ids = ["same", "close", "orthogonal"]

    hits = embeddings.rank_by_similarity(_unit(1, 0, 0), matrix, ids, limit=3)

    assert [h["image_id"] for h in hits] == ["same", "close", "orthogonal"]
    assert hits[0]["score"] == pytest.approx(1.0, abs=1e-4)
    assert hits[2]["score"] == pytest.approx(0.0, abs=1e-4)


def test_rank_by_similarity_respects_limit_and_min_score():
    matrix = np.vstack([_unit(1, 0), _unit(0.7, 0.7), _unit(0, 1)])
    ids = ["a", "b", "c"]

    assert len(embeddings.rank_by_similarity(_unit(1, 0), matrix, ids, limit=2)) == 2

    filtered = embeddings.rank_by_similarity(
        _unit(1, 0), matrix, ids, limit=3, min_score=0.5
    )
    assert [h["image_id"] for h in filtered] == ["a", "b"]


def test_rank_by_similarity_limit_above_corpus_size_is_clamped():
    """argpartition raises if k exceeds the array length, so this is a real edge."""
    matrix = np.vstack([_unit(1, 0), _unit(0, 1)])
    hits = embeddings.rank_by_similarity(_unit(1, 0), matrix, ["a", "b"], limit=500)
    assert len(hits) == 2


def test_rank_by_similarity_on_an_empty_corpus():
    assert embeddings.rank_by_similarity(_unit(1, 0), None, [], limit=5) == []


# ---------------------------------------------------------------------------
# Near-duplicate detection
# ---------------------------------------------------------------------------

def test_near_duplicates_finds_only_pairs_above_threshold():
    matrix = np.vstack([
        _unit(1, 0, 0),
        _unit(0.999, 0.044, 0),  # a hair away from row 0
        _unit(0, 1, 0),          # unrelated
    ])
    ids = ["orig", "dupe", "other"]

    pairs = embeddings.find_near_duplicates(matrix, ids, threshold=0.95)

    assert len(pairs) == 1
    assert {pairs[0]["image_a"], pairs[0]["image_b"]} == {"orig", "dupe"}
    assert pairs[0]["similarity"] >= 0.95


def test_near_duplicates_reports_each_pair_once_and_never_self():
    """Only the upper triangle is scanned, so no (a,a) and no (b,a) echo."""
    matrix = np.vstack([_unit(1, 0)] * 3)
    pairs = embeddings.find_near_duplicates(matrix, ["a", "b", "c"], threshold=0.9)

    assert len(pairs) == 3  # ab, ac, bc
    for pair in pairs:
        assert pair["image_a"] != pair["image_b"]
    seen = {frozenset((p["image_a"], p["image_b"])) for p in pairs}
    assert len(seen) == 3


def test_near_duplicates_honours_max_pairs():
    matrix = np.vstack([_unit(1, 0)] * 10)
    ids = [str(i) for i in range(10)]
    pairs = embeddings.find_near_duplicates(matrix, ids, threshold=0.9, max_pairs=5)
    assert len(pairs) == 5


def test_near_duplicates_crossing_the_block_boundary():
    """Similarity is computed in 512-row blocks. A duplicate pair split across
    two blocks is only found if the scan compares each block against the whole
    matrix rather than against itself."""
    # 600 mutually orthogonal rows, except the last, which repeats the first.
    matrix = np.eye(600, dtype="float32")
    matrix[599] = matrix[0]
    ids = [f"img{i}" for i in range(600)]

    pairs = embeddings.find_near_duplicates(matrix, ids, threshold=0.99)

    # Rows 0 and 599 land in different 512-row blocks.
    assert [{p["image_a"], p["image_b"]} for p in pairs] == [{"img0", "img599"}]


def test_near_duplicates_needs_at_least_two_images():
    assert embeddings.find_near_duplicates(np.vstack([_unit(1, 0)]), ["a"]) == []


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def test_kmeans_separates_two_obvious_groups():
    group_a = np.vstack([_unit(1, 0.01 * i) for i in range(10)])
    group_b = np.vstack([_unit(0.01 * i, 1) for i in range(10)])
    matrix = np.vstack([group_a, group_b]).astype("float32")

    labels, centroids = embeddings.kmeans(matrix, 2, seed=1)

    assert len(centroids) == 2
    # Every member of a group should share a label with the rest of its group.
    assert len(set(labels[:10].tolist())) == 1
    assert len(set(labels[10:].tolist())) == 1
    assert labels[0] != labels[10]


def test_kmeans_clamps_k_to_the_number_of_points():
    matrix = np.vstack([_unit(1, 0), _unit(0, 1)])
    labels, centroids = embeddings.kmeans(matrix, 10)
    assert len(centroids) == 2
    assert len(labels) == 2


def test_kmeans_handles_identical_points_without_nan():
    """All-identical input makes the k-means++ distance weights sum to zero."""
    matrix = np.vstack([_unit(1, 0)] * 5)
    labels, centroids = embeddings.kmeans(matrix, 3)
    assert not np.isnan(centroids).any()
    assert len(labels) == 5


# ---------------------------------------------------------------------------
# Diversity sampling — the active-learning fix
# ---------------------------------------------------------------------------

def test_diverse_sample_spreads_across_clusters():
    """The point of the feature: 9 near-identical images plus 1 outlier must
    not return 2 images from the identical blob and ignore the outlier."""
    blob = np.vstack([_unit(1, 0.001 * i) for i in range(9)])
    outlier = _unit(0, 1).reshape(1, -1)
    matrix = np.vstack([blob, outlier]).astype("float32")
    ids = [f"blob{i}" for i in range(9)] + ["outlier"]

    picks = embeddings.diverse_sample(matrix, ids, 2)

    assert len(picks) == 2
    assert "outlier" in picks


def test_diverse_sample_uses_priority_to_break_ties_within_a_cluster():
    """Given a cluster, the most uncertain member should win."""
    matrix = np.vstack([
        _unit(1, 0.001),
        _unit(1, 0.002),
        _unit(0, 1),
    ]).astype("float32")
    ids = ["low_priority", "high_priority", "far"]
    priority = [0.1, 0.9, 0.5]

    picks = embeddings.diverse_sample(matrix, ids, 2, priority=priority)

    assert "high_priority" in picks
    assert "low_priority" not in picks


def test_diverse_sample_returns_everything_when_asked_for_the_whole_pool():
    matrix = np.vstack([_unit(1, 0), _unit(0, 1)]).astype("float32")
    picks = embeddings.diverse_sample(matrix, ["a", "b"], 2)
    assert sorted(picks) == ["a", "b"]


def test_diverse_sample_never_returns_duplicates():
    """Empty clusters trigger a top-up pass; it must not re-pick a winner."""
    matrix = np.vstack([_unit(1, 0.001 * i) for i in range(12)]).astype("float32")
    ids = [f"img{i}" for i in range(12)]

    picks = embeddings.diverse_sample(matrix, ids, 5, priority=list(range(12)))

    assert len(picks) == len(set(picks))
    assert len(picks) == 5


def test_diverse_sample_on_an_empty_pool():
    assert embeddings.diverse_sample(None, [], 5) == []


# ---------------------------------------------------------------------------
# Representative selection
# ---------------------------------------------------------------------------

def test_nearest_member_picks_the_closest_row_to_a_centroid():
    matrix = np.vstack([_unit(1, 0), _unit(0.7, 0.7), _unit(0, 1)]).astype("float32")
    centroid = _unit(0, 1)

    assert embeddings.nearest_member(matrix, [0, 1, 2], centroid) == 2
    # Restricted to a subset, the answer must come from that subset.
    assert embeddings.nearest_member(matrix, [0, 1], centroid) == 1


def test_nearest_member_on_an_empty_cluster():
    matrix = np.vstack([_unit(1, 0)]).astype("float32")
    assert embeddings.nearest_member(matrix, [], _unit(1, 0)) is None
