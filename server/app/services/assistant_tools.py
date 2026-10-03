"""
The tools the in-app assistant can call.

A chat box that only paraphrases the documentation is worse than no chat box,
so the assistant gets real read access to the asking user's own projects: how
many images are labelled, what the last run scored, which classes the model
confuses, which images match a description.

Two rules shape everything here:

* **Read-only.** Every tool observes; none mutates. The assistant has no
  confirmation UI, so it is not the right place to start a training run or
  delete an image — a wrong call would be unrecoverable and unreviewed.
* **Scoped to the caller.** Each tool re-derives access from the `user` passed
  into `run_tool`, exactly as an HTTP endpoint would. The model chooses which
  dataset id to pass, and a model can be talked into passing someone else's,
  so authorisation can never be the model's job.

Tool results come back as JSON strings. Errors are returned as data, not
raised: "that dataset is not yours" is something the assistant should read and
explain, not a 500 for the user.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from app.core.access import effective_role
from app.services.database import AnnotationService, DatasetService

logger = logging.getLogger(__name__)

# Caps on what one tool call may return. The assistant pays for every token of
# tool output, and a 5,000-image dataset listing would crowd out the actual
# conversation.
MAX_PROJECTS = 50
MAX_SEARCH_RESULTS = 20
MAX_RUNS = 20
MAX_CLASSES = 60


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "list_projects",
        "description": (
            "List the user's projects (datasets) with image counts and how many "
            "images are annotated. Call this first when the user refers to a "
            "project by name rather than id, to resolve the id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_project_overview",
        "description": (
            "Counts, class list and per-class annotation distribution for one "
            "project. Use this to answer questions about class balance or how "
            "much labelling is left."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The project id."}
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_training_runs",
        "description": (
            "Training runs for one project, newest first, with their status and "
            "metrics. Use this to answer 'how did my last run do' or to find the "
            "job id of a run the user is asking about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The project id."}
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_evaluation",
        "description": (
            "The most recent evaluation of a training run: overall metrics, "
            "per-class scores, a breakdown of how the model fails (hallucinated "
            "boxes, wrong class, loose boxes, duplicates, misses), which classes "
            "it confuses, and the best confidence threshold. This is the right "
            "tool for 'why is my model bad' — it says where the errors are."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The training job id, from get_training_runs.",
                }
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_dataset_health",
        "description": (
            "The stored dataset health snapshot for a project: quality score, "
            "class balance, duplicate/blur/corruption counts. Reads the last "
            "computed snapshot; it does not trigger a new analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The project id."}
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_images",
        "description": (
            "Find images in a project by describing them in words, using CLIP "
            "embeddings — for example 'blurry close-ups' or 'a red truck at "
            "night'. Requires that the project's search index has been built; "
            "says so if it has not."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "The project id."},
                "query": {
                    "type": "string",
                    "description": "What to look for, in plain language.",
                },
            },
            "required": ["dataset_id", "query"],
            "additionalProperties": False,
        },
    },
]


def _error(message: str) -> str:
    """A tool failure the assistant can read and explain."""
    return json.dumps({"error": message})


def _readable_dataset(dataset_id: str, user: Dict) -> Optional[Dict]:
    """
    Fetch a dataset only if this user may read it.

    The model picks the id, so this is the gate. `effective_role` is the same
    helper the HTTP layer uses, which keeps one definition of access.
    """
    dataset = DatasetService.get_dataset(dataset_id)
    if not dataset:
        return None
    role = effective_role(dataset_id, user["id"], dataset["user_id"])
    return dataset if role else None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _list_projects(_: Dict[str, Any], user: Dict) -> str:
    datasets = DatasetService.list_datasets(user_id=user["id"]) or []
    rows = [
        {
            "dataset_id": dataset.get("id"),
            "name": dataset.get("name"),
            "classes": (dataset.get("classes") or [])[:MAX_CLASSES],
            "total_images": dataset.get("total_images", 0),
            "annotated_images": dataset.get("annotated_images", 0),
        }
        for dataset in datasets[:MAX_PROJECTS]
    ]
    return json.dumps({"projects": rows, "count": len(rows)})


def _get_project_overview(args: Dict[str, Any], user: Dict) -> str:
    dataset_id = args.get("dataset_id", "")
    dataset = _readable_dataset(dataset_id, user)
    if not dataset:
        return _error("No project with that id that you have access to.")

    images = dataset.get("images") or []
    annotated = sum(1 for image in images if image.get("annotated"))

    # Per-class box counts, which is what a "class balance" question means.
    per_class: Dict[str, int] = {}
    for row in AnnotationService.get_all_dataset_annotations(dataset_id) or []:
        for box in row.get("boxes") or []:
            name = box.get("class_name") or f"class_{box.get('class_id', 0)}"
            per_class[name] = per_class.get(name, 0) + 1

    splits: Dict[str, int] = {}
    for image in images:
        splits[image.get("split") or "unassigned"] = (
            splits.get(image.get("split") or "unassigned", 0) + 1
        )

    return json.dumps({
        "dataset_id": dataset_id,
        "name": dataset.get("name"),
        "classes": (dataset.get("classes") or [])[:MAX_CLASSES],
        "total_images": len(images),
        "annotated_images": annotated,
        "unannotated_images": len(images) - annotated,
        "split_distribution": splits,
        "boxes_per_class": dict(
            sorted(per_class.items(), key=lambda kv: -kv[1])[:MAX_CLASSES]
        ),
        "total_boxes": sum(per_class.values()),
    })


def _get_training_runs(args: Dict[str, Any], user: Dict) -> str:
    dataset_id = args.get("dataset_id", "")
    if not _readable_dataset(dataset_id, user):
        return _error("No project with that id that you have access to.")

    from app.db.session import db_cursor

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id, model_name, status, progress, epochs, batch_size, "
                "       results, error_message, created_at "
                "FROM training_jobs WHERE dataset_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (dataset_id, MAX_RUNS),
            )
            rows = cursor.fetchall() or []
    except Exception as e:
        logger.error(f"assistant: could not list runs for {dataset_id}: {e}")
        return _error("Could not read the training runs for this project.")

    runs = []
    for row in rows:
        results = row.get("results")
        if isinstance(results, (str, bytes, bytearray)):
            try:
                results = json.loads(results)
            except (ValueError, TypeError):
                results = None
        runs.append({
            "job_id": row.get("id"),
            "model": row.get("model_name"),
            "status": row.get("status"),
            "epochs": row.get("epochs"),
            "metrics": (results or {}).get("metrics") if isinstance(results, dict) else None,
            "error": row.get("error_message"),
            "created_at": str(row.get("created_at")),
        })

    return json.dumps({"dataset_id": dataset_id, "runs": runs, "count": len(runs)})


def _get_evaluation(args: Dict[str, Any], user: Dict) -> str:
    job_id = args.get("job_id", "")

    from app.db.session import db_cursor

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM evaluations WHERE job_id = %s AND status = 'completed' "
                "ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            )
            row = cursor.fetchone()
    except Exception as e:
        logger.error(f"assistant: could not read evaluation for {job_id}: {e}")
        return _error("Could not read the evaluation for that run.")

    if not row:
        return json.dumps({
            "job_id": job_id,
            "evaluation": None,
            "hint": (
                "This run has not been evaluated yet. The user can run one from "
                "the Evaluate tab, which is what produces the per-image error "
                "breakdown."
            ),
        })

    # The evaluation row carries no owner of its own; its dataset does.
    if not row.get("dataset_id") or not _readable_dataset(row["dataset_id"], user):
        return _error("That run is not one you have access to.")

    def decoded(column: str) -> Any:
        value = row.get(column)
        if isinstance(value, (str, bytes, bytearray)):
            try:
                return json.loads(value)
            except (ValueError, TypeError):
                return None
        return value

    return json.dumps({
        "job_id": job_id,
        "split": row.get("split"),
        "images_evaluated": row.get("images_evaluated"),
        "iou_threshold": row.get("iou_threshold"),
        "conf_threshold": row.get("conf_threshold"),
        "metrics": decoded("metrics"),
        "per_class_metrics": decoded("per_class_metrics"),
        "error_kinds": decoded("error_kinds"),
        "class_confusion": decoded("class_confusion"),
        "best_operating_point": decoded("best_operating_point"),
        "error_kind_meanings": {
            "background": "predicted an object where there is nothing",
            "wrong_class": "found the object but named it wrong",
            "poor_localisation": "right class, box too loose to count",
            "duplicate": "a second box on an object already found",
            "missed": "a labelled object nothing covered",
        },
    })


def _get_dataset_health(args: Dict[str, Any], user: Dict) -> str:
    dataset_id = args.get("dataset_id", "")
    if not _readable_dataset(dataset_id, user):
        return _error("No project with that id that you have access to.")

    from app.db.session import db_cursor

    try:
        with db_cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM dataset_quality_snapshots WHERE dataset_id = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (dataset_id,),
            )
            row = cursor.fetchone()
    except Exception as e:
        logger.error(f"assistant: could not read health for {dataset_id}: {e}")
        return _error("Could not read the health snapshot for this project.")

    if not row:
        return json.dumps({
            "dataset_id": dataset_id,
            "snapshot": None,
            "hint": "No health analysis has been run yet; the Health tab computes one.",
        })

    # Timestamps are not JSON-serialisable, and the assistant only needs them
    # as text.
    snapshot = {
        key: (str(value) if hasattr(value, "isoformat") else value)
        for key, value in row.items()
    }
    return json.dumps({"dataset_id": dataset_id, "snapshot": snapshot})


def _search_images(args: Dict[str, Any], user: Dict) -> str:
    dataset_id = args.get("dataset_id", "")
    query = (args.get("query") or "").strip()
    dataset = _readable_dataset(dataset_id, user)
    if not dataset:
        return _error("No project with that id that you have access to.")
    if not query:
        return _error("A search needs a description to look for.")

    from app.api.v1.endpoints.search import _load_dataset_vectors
    from app.services import embeddings

    if not embeddings.is_available():
        return _error("Semantic search is not available on this server.")

    ids, matrix = _load_dataset_vectors(dataset_id)
    if matrix is None:
        return json.dumps({
            "dataset_id": dataset_id,
            "results": [],
            "hint": (
                "This project has no search index yet. The user can build one "
                "from the Images tab, which enables searching by description."
            ),
        })

    vector = embeddings.embed_text([query])
    if vector is None:
        return _error("The embedding model could not be loaded to run the search.")

    hits = embeddings.rank_by_similarity(
        vector[0], matrix, ids, limit=MAX_SEARCH_RESULTS
    )
    lookup = {image["id"]: image for image in dataset.get("images") or []}

    return json.dumps({
        "dataset_id": dataset_id,
        "query": query,
        "results": [
            {
                "image_id": hit["image_id"],
                "filename": (lookup.get(hit["image_id"]) or {}).get("filename"),
                "similarity": hit["score"],
                "annotated": bool((lookup.get(hit["image_id"]) or {}).get("annotated")),
            }
            for hit in hits
            if hit["image_id"] in lookup
        ],
        "note": (
            "Similarity is a CLIP cosine score, comparable within this result "
            "set but not across different queries."
        ),
    })


_HANDLERS: Dict[str, Callable[[Dict[str, Any], Dict], str]] = {
    "list_projects": _list_projects,
    "get_project_overview": _get_project_overview,
    "get_training_runs": _get_training_runs,
    "get_evaluation": _get_evaluation,
    "get_dataset_health": _get_dataset_health,
    "search_images": _search_images,
}


def run_tool(name: str, args: Dict[str, Any], user: Dict) -> str:
    """
    Execute one tool call on behalf of `user`.

    Never raises: an unknown tool, a bad argument or a thrown exception all
    come back as a JSON error the assistant can read, because the alternative
    is a dead conversation the user cannot recover from.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return _error(f"Unknown tool: {name}")

    try:
        return handler(args or {}, user)
    except Exception as e:
        logger.error(f"assistant tool {name} failed: {e}")
        return _error(f"The {name} tool failed: {e}")
