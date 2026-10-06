"""
Class management for a live dataset.

`datasets.classes` is a JSON array and every annotation box stores its class as
an *index into that array*, so renaming a class is a single-row update but
removing or merging one has to rewrite every box that pointed at or past it.
That is why this is a service and not an inline handler: the index rewrite has
to happen for every annotation in the dataset, atomically, or the dataset is
left with boxes pointing at the wrong class.

The work splits in two. `plan_*` turns an operation into a `(new_classes,
mapping)` pair and touches no database — mapping sends every *old* index to its
new one, or to None for "this class is going away, drop its boxes". `apply`
then walks the dataset once inside a single transaction.

Frozen `dataset_versions` are deliberately left alone. A version is the data a
training run actually consumed and the evaluation workbench scores against it,
so rewriting a snapshot to match a later rename would make finished runs
unreproducible — the thing versioning exists to prevent. A version keeps the
class names it was frozen with, which is also why the public class list and an
old run's class list can legitimately disagree.
"""

import json
import logging
from typing import Dict, List, Optional, Sequence, Tuple

from app.db.session import db_cursor

logger = logging.getLogger(__name__)

# Mapping from an old class index to its new index, or None if the class is
# being removed and its boxes should go with it.
ClassMapping = Dict[int, Optional[int]]

MAX_CLASS_NAME = 100


class ClassOperationError(ValueError):
    """An operation that cannot be applied — surfaced to the caller as a 400."""


def normalise_name(name: str) -> str:
    """Validate and clean a class name."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ClassOperationError("Class name cannot be empty")
    if len(cleaned) > MAX_CLASS_NAME:
        raise ClassOperationError(
            f"Class name must be {MAX_CLASS_NAME} characters or fewer"
        )
    if "\x00" in cleaned:
        raise ClassOperationError("Class name may not contain null bytes")
    return cleaned


def _require_index(classes: Sequence[str], index: int, label: str = "index") -> int:
    if not isinstance(index, int) or isinstance(index, bool):
        raise ClassOperationError(f"{label} must be an integer")
    if index < 0 or index >= len(classes):
        raise ClassOperationError(
            f"{label} {index} is out of range for this dataset ({len(classes)} classes)"
        )
    return index


def _reject_duplicate(classes: Sequence[str], name: str, *, skip: Optional[int] = None) -> None:
    """Class names feed the training YAML, where two identical names are ambiguous."""
    folded = name.casefold()
    for i, existing in enumerate(classes):
        if i == skip:
            continue
        if existing.casefold() == folded:
            raise ClassOperationError(
                f"A class named '{existing}' already exists; merge into it instead"
            )


def _identity(count: int) -> ClassMapping:
    return {i: i for i in range(count)}


def plan_add(classes: Sequence[str], name: str) -> Tuple[List[str], ClassMapping]:
    """Append a class. Existing boxes keep their indices."""
    cleaned = normalise_name(name)
    _reject_duplicate(classes, cleaned)
    return list(classes) + [cleaned], _identity(len(classes))


def plan_rename(
    classes: Sequence[str], index: int, name: str
) -> Tuple[List[str], ClassMapping]:
    """Rename one class in place. Indices do not move, but box `class_name` does."""
    _require_index(classes, index)
    cleaned = normalise_name(name)
    _reject_duplicate(classes, cleaned, skip=index)
    new_classes = list(classes)
    new_classes[index] = cleaned
    return new_classes, _identity(len(classes))


def plan_delete(classes: Sequence[str], index: int) -> Tuple[List[str], ClassMapping]:
    """Remove a class and every box that used it, closing the index gap."""
    _require_index(classes, index)
    if len(classes) == 1:
        raise ClassOperationError("A dataset must keep at least one class")

    new_classes = [c for i, c in enumerate(classes) if i != index]
    mapping: ClassMapping = {}
    for i in range(len(classes)):
        if i == index:
            mapping[i] = None
        else:
            mapping[i] = i if i < index else i - 1
    return new_classes, mapping


def plan_merge(
    classes: Sequence[str], sources: Sequence[int], target: int
) -> Tuple[List[str], ClassMapping]:
    """Fold `sources` into `target`, keeping their boxes and retargeting them.

    Unlike delete, nothing is thrown away: the boxes survive under the target
    class. This is the common "these two labels turned out to be the same
    thing" cleanup.
    """
    _require_index(classes, target, "target")
    source_set = {_require_index(classes, s, "source") for s in sources}
    source_set.discard(target)
    if not source_set:
        raise ClassOperationError("Pick at least one source class other than the target")
    if len(source_set) >= len(classes):
        raise ClassOperationError("A dataset must keep at least one class")

    survivors = [i for i in range(len(classes)) if i not in source_set]
    new_classes = [classes[i] for i in survivors]
    new_position = {old: new for new, old in enumerate(survivors)}

    mapping: ClassMapping = {}
    for i in range(len(classes)):
        mapping[i] = new_position[target] if i in source_set else new_position[i]
    return new_classes, mapping


def remap_boxes(
    boxes: Sequence[Dict], mapping: ClassMapping, new_classes: Sequence[str]
) -> Tuple[List[Dict], int]:
    """Rewrite each box's class index and name. Returns (boxes, dropped count).

    `class_name` is always rewritten from `new_classes`, not just when the
    index moves, so a rename propagates and any box whose stored name had
    drifted out of sync with its index gets corrected on the way through.

    A box whose index is not in `mapping` is already outside the class list —
    `dataset_analyzer` reports these as `invalid_class_ids`. Reindexing cannot
    place it, so it is dropped and counted with the rest.
    """
    kept: List[Dict] = []
    dropped = 0

    for box in boxes:
        raw = box.get("class_id", 0)
        try:
            old_index = int(raw)
        except (TypeError, ValueError):
            dropped += 1
            continue

        new_index = mapping.get(old_index, None)
        if new_index is None:
            dropped += 1
            continue

        updated = dict(box)
        updated["class_id"] = new_index
        updated["class_name"] = new_classes[new_index]
        kept.append(updated)

    return kept, dropped


def _remap_detection_blob(raw, mapping: ClassMapping, new_classes: Sequence[str]):
    """Remap one `uncertain_images` detection list. Returns (list, changed)."""
    try:
        detections = json.loads(raw) if isinstance(raw, (str, bytes)) else (raw or [])
    except (ValueError, TypeError):
        return [], True
    if not isinstance(detections, list):
        return [], True

    remapped, dropped = remap_boxes(detections, mapping, new_classes)
    return remapped, bool(dropped) or remapped != detections


def apply(
    dataset_id: str, new_classes: Sequence[str], mapping: ClassMapping
) -> Dict[str, int]:
    """Write a planned class change across the dataset in one transaction.

    Everything that stores a class index against the *live* dataset moves
    together: the class list itself, every annotation box, and the active
    learning review queue, whose predictions would otherwise point at classes
    that no longer exist. If any part fails the whole change rolls back, so a
    dataset is never left half-reindexed.
    """
    stats = {
        "annotations_rewritten": 0,
        "boxes_dropped": 0,
        "images_unlabelled": 0,
        "uncertain_rows_updated": 0,
        "uncertain_rows_removed": 0,
    }
    classes = list(new_classes)

    with db_cursor(dictionary=True, commit=True) as cursor:
        cursor.execute(
            "SELECT id, image_id, boxes FROM annotations WHERE dataset_id = %s",
            (dataset_id,),
        )
        rows = cursor.fetchall()

        emptied_images: List[str] = []
        for row in rows:
            try:
                boxes = json.loads(row["boxes"]) if row["boxes"] else []
            except (ValueError, TypeError):
                logger.warning(
                    "Malformed boxes JSON on annotation %s; treating as empty", row["id"]
                )
                boxes = []
            if not isinstance(boxes, list):
                boxes = []

            remapped, dropped = remap_boxes(boxes, mapping, classes)
            if dropped == 0 and remapped == boxes:
                continue

            cursor.execute(
                """
                UPDATE annotations
                SET boxes = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (json.dumps(remapped), row["id"]),
            )
            stats["annotations_rewritten"] += 1
            stats["boxes_dropped"] += dropped
            if boxes and not remapped:
                emptied_images.append(row["image_id"])

        # An image whose last box just went away is no longer annotated. The
        # save path keeps this invariant (`annotated` tracks "has labels"), so
        # a class delete has to keep it too or the dashboard counts drift.
        if emptied_images:
            placeholders = ",".join(["%s"] * len(emptied_images))
            cursor.execute(
                f"""
                UPDATE dataset_images
                SET annotated = FALSE
                WHERE dataset_id = %s AND id IN ({placeholders})
                """,
                (dataset_id, *emptied_images),
            )
            stats["images_unlabelled"] = cursor.rowcount or 0

        cursor.execute(
            """
            UPDATE datasets
            SET classes = %s,
                annotated_images = (
                    SELECT COUNT(*) FROM dataset_images
                    WHERE dataset_id = %s AND annotated = TRUE
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (json.dumps(classes), dataset_id, dataset_id),
        )

        _apply_to_review_queue(cursor, dataset_id, mapping, classes, stats)

    logger.info("Class change applied to dataset %s: %s", dataset_id, stats)
    return stats


def _apply_to_review_queue(
    cursor, dataset_id: str, mapping: ClassMapping, classes: Sequence[str], stats: Dict
) -> None:
    """Retarget the active-learning queue, dropping rows left with nothing."""
    cursor.execute(
        """
        SELECT id, low_confidence_detections, high_confidence_detections
        FROM uncertain_images
        WHERE dataset_id = %s
        """,
        (dataset_id,),
    )
    queued = cursor.fetchall()

    for row in queued:
        low, low_changed = _remap_detection_blob(
            row["low_confidence_detections"], mapping, classes
        )
        high, high_changed = _remap_detection_blob(
            row["high_confidence_detections"], mapping, classes
        )
        if not (low_changed or high_changed):
            continue

        if not low and not high:
            cursor.execute("DELETE FROM uncertain_images WHERE id = %s", (row["id"],))
            stats["uncertain_rows_removed"] += 1
            continue

        confidences = [
            d.get("confidence")
            for d in low + high
            if isinstance(d.get("confidence"), (int, float))
        ]
        cursor.execute(
            """
            UPDATE uncertain_images
            SET low_confidence_detections = %s,
                high_confidence_detections = %s,
                total_detections = %s,
                min_confidence = %s
            WHERE id = %s
            """,
            (
                json.dumps(low),
                json.dumps(high),
                len(low) + len(high),
                min(confidences) if confidences else 0,
                row["id"],
            ),
        )
        stats["uncertain_rows_updated"] += 1


def instance_counts(dataset_id: str, class_count: int) -> List[int]:
    """How many boxes use each class index, for the "3 instances" hint in the UI."""
    counts = [0] * class_count
    with db_cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT boxes FROM annotations WHERE dataset_id = %s", (dataset_id,)
        )
        for row in cursor.fetchall():
            try:
                boxes = json.loads(row["boxes"]) if row["boxes"] else []
            except (ValueError, TypeError):
                continue
            if not isinstance(boxes, list):
                continue
            for box in boxes:
                try:
                    index = int(box.get("class_id", -1))
                except (TypeError, ValueError):
                    continue
                if 0 <= index < class_count:
                    counts[index] += 1
    return counts
