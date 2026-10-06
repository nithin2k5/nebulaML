"""
Class planning and box remapping.

Every box stores its class as an index into `datasets.classes`, so a delete or
merge has to shift every index that pointed past the hole. Getting that wrong
does not raise — it silently relabels the dataset — so the planners and the
remapper are tested directly, without a database.
"""

import pytest

from app.services import class_manager
from app.services.class_manager import ClassOperationError

CLASSES = ["cat", "dog", "bird", "fish"]


def _boxes(*class_ids):
    return [
        {"class_id": cid, "class_name": CLASSES[cid], "x": 1, "y": 2, "width": 3, "height": 4}
        for cid in class_ids
    ]


# --- add ------------------------------------------------------------------


def test_add_appends_and_leaves_indices_alone():
    new_classes, mapping = class_manager.plan_add(CLASSES, "horse")
    assert new_classes == ["cat", "dog", "bird", "fish", "horse"]
    assert mapping == {0: 0, 1: 1, 2: 2, 3: 3}


def test_add_trims_whitespace():
    new_classes, _ = class_manager.plan_add(CLASSES, "  horse  ")
    assert new_classes[-1] == "horse"


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_add_rejects_bad_names(name):
    with pytest.raises(ClassOperationError):
        class_manager.plan_add(CLASSES, name)


def test_add_rejects_duplicate_case_insensitively():
    # Two classes with the same name make the training YAML ambiguous.
    with pytest.raises(ClassOperationError, match="already exists"):
        class_manager.plan_add(CLASSES, "DOG")


# --- rename ---------------------------------------------------------------


def test_rename_keeps_indices():
    new_classes, mapping = class_manager.plan_rename(CLASSES, 1, "puppy")
    assert new_classes == ["cat", "puppy", "bird", "fish"]
    assert mapping == {0: 0, 1: 1, 2: 2, 3: 3}


def test_rename_to_its_own_name_is_allowed():
    new_classes, _ = class_manager.plan_rename(CLASSES, 1, "dog")
    assert new_classes == CLASSES


def test_rename_onto_another_class_is_rejected():
    with pytest.raises(ClassOperationError, match="already exists"):
        class_manager.plan_rename(CLASSES, 1, "bird")


def test_rename_propagates_into_stored_box_names():
    new_classes, mapping = class_manager.plan_rename(CLASSES, 1, "puppy")
    remapped, dropped = class_manager.remap_boxes(_boxes(0, 1), mapping, new_classes)
    assert dropped == 0
    assert [b["class_name"] for b in remapped] == ["cat", "puppy"]


# --- delete ---------------------------------------------------------------


def test_delete_closes_the_index_gap():
    new_classes, mapping = class_manager.plan_delete(CLASSES, 1)
    assert new_classes == ["cat", "bird", "fish"]
    # Everything above the hole shifts down by one; the hole itself drops.
    assert mapping == {0: 0, 1: None, 2: 1, 3: 2}


def test_delete_drops_only_that_classs_boxes_and_reindexes_the_rest():
    new_classes, mapping = class_manager.plan_delete(CLASSES, 1)
    remapped, dropped = class_manager.remap_boxes(
        _boxes(0, 1, 2, 3, 1), mapping, new_classes
    )
    assert dropped == 2
    assert [(b["class_id"], b["class_name"]) for b in remapped] == [
        (0, "cat"),
        (1, "bird"),
        (2, "fish"),
    ]


def test_delete_last_remaining_class_is_rejected():
    with pytest.raises(ClassOperationError, match="at least one class"):
        class_manager.plan_delete(["only"], 0)


@pytest.mark.parametrize("index", [-1, 4, 99])
def test_delete_out_of_range_is_rejected(index):
    with pytest.raises(ClassOperationError, match="out of range"):
        class_manager.plan_delete(CLASSES, index)


def test_remap_preserves_box_geometry():
    new_classes, mapping = class_manager.plan_delete(CLASSES, 0)
    remapped, _ = class_manager.remap_boxes(_boxes(2), mapping, new_classes)
    assert remapped[0]["x"] == 1 and remapped[0]["width"] == 3


# --- merge ----------------------------------------------------------------


def test_merge_retargets_sources_and_keeps_their_boxes():
    new_classes, mapping = class_manager.plan_merge(CLASSES, [2], 1)
    assert new_classes == ["cat", "dog", "fish"]
    # bird folds into dog; fish shifts down into the vacated slot.
    assert mapping == {0: 0, 1: 1, 2: 1, 3: 2}

    remapped, dropped = class_manager.remap_boxes(
        _boxes(0, 1, 2, 3), mapping, new_classes
    )
    assert dropped == 0, "a merge must not lose boxes"
    assert [(b["class_id"], b["class_name"]) for b in remapped] == [
        (0, "cat"),
        (1, "dog"),
        (1, "dog"),
        (2, "fish"),
    ]


def test_merge_several_sources_at_once():
    new_classes, mapping = class_manager.plan_merge(CLASSES, [0, 2, 3], 1)
    assert new_classes == ["dog"]
    assert mapping == {0: 0, 1: 0, 2: 0, 3: 0}


def test_merge_target_below_sources_shifts_correctly():
    new_classes, mapping = class_manager.plan_merge(CLASSES, [1], 3)
    assert new_classes == ["cat", "bird", "fish"]
    assert mapping == {0: 0, 1: 2, 2: 1, 3: 2}


def test_merge_ignores_the_target_appearing_in_sources():
    new_classes, mapping = class_manager.plan_merge(CLASSES, [1, 2], 1)
    assert new_classes == ["cat", "dog", "fish"]
    assert mapping == {0: 0, 1: 1, 2: 1, 3: 2}


def test_merge_with_only_the_target_as_source_is_rejected():
    with pytest.raises(ClassOperationError, match="at least one source"):
        class_manager.plan_merge(CLASSES, [1], 1)


def test_merge_everything_into_the_target_collapses_to_one_class():
    # The target counts as a survivor even when it is also listed as a source,
    # so this is a legal "it was all one class really" collapse, not a request
    # to empty the class list.
    new_classes, mapping = class_manager.plan_merge(CLASSES, [0, 1, 2, 3], 0)
    assert new_classes == ["cat"]
    assert mapping == {0: 0, 1: 0, 2: 0, 3: 0}


def test_merge_rejects_out_of_range_source():
    with pytest.raises(ClassOperationError, match="out of range"):
        class_manager.plan_merge(CLASSES, [9], 0)


# --- malformed stored data ------------------------------------------------


def test_remap_drops_boxes_whose_class_is_already_out_of_range():
    # dataset_analyzer reports these as invalid_class_ids; reindexing cannot
    # place one, so it goes with the dropped boxes rather than being kept at a
    # bogus index.
    new_classes, mapping = class_manager.plan_rename(CLASSES, 0, "feline")
    boxes = [{"class_id": 17, "class_name": "ghost"}]
    remapped, dropped = class_manager.remap_boxes(boxes, mapping, new_classes)
    assert remapped == []
    assert dropped == 1


@pytest.mark.parametrize("bad", [None, "two", {}, []])
def test_remap_drops_boxes_with_an_unparseable_class_id(bad):
    new_classes, mapping = class_manager.plan_rename(CLASSES, 0, "feline")
    remapped, dropped = class_manager.remap_boxes(
        [{"class_id": bad}], mapping, new_classes
    )
    assert remapped == []
    assert dropped == 1


def test_remap_accepts_a_numeric_string_class_id():
    # Older rows round-tripped through JSON with string indices.
    new_classes, mapping = class_manager.plan_rename(CLASSES, 1, "puppy")
    remapped, dropped = class_manager.remap_boxes(
        [{"class_id": "1"}], mapping, new_classes
    )
    assert dropped == 0
    assert remapped[0]["class_id"] == 1
    assert remapped[0]["class_name"] == "puppy"


def test_remap_of_empty_boxes_is_a_no_op():
    new_classes, mapping = class_manager.plan_delete(CLASSES, 0)
    assert class_manager.remap_boxes([], mapping, new_classes) == ([], 0)
