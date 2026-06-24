"""Per-task-class calibration buckets for Bob3.

Provides:
- TASK_CLASSES: the five canonical task class labels
- infer_task_class(): keyword heuristic to classify a feature description
- compute_ece_by_bucket(): ECE computation grouped by task class

ECE definition: mean(|predicted_conf - empirical_accuracy|) over all
confidence sub-buckets within a task class.
"""

from __future__ import annotations

from collections import defaultdict

TASK_CLASSES: list[str] = [
    "file_manipulation",
    "algorithm_implementation",
    "integration",
    "refactor",
    "research_synthesis",
]

# Ordered list of (task_class, keywords) — first match wins.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("file_manipulation", ["file", "write", "read", "directory", "path", "disk", "filesystem", "csv", "json", "yaml", "toml", "parse"]),
    ("research_synthesis", ["research", "synthesize", "synthesis", "survey", "analyze", "analyse", "findings", "literature", "review"]),
    ("integration", ["integrat", "api", "endpoint", "webhook", "client", "connect", "service", "http", "rest", "grpc", "sdk"]),
    ("refactor", ["refactor", "restructur", "cleanup", "clean up", "reorganiz", "rename", "extract", "simplif", "modulariz"]),
    ("algorithm_implementation", ["algorithm", "implement", "compute", "calculat", "sort", "search", "graph", "tree", "dynamic"]),
]


def infer_task_class(description: str) -> str:
    """Classify a feature description into one of the five task classes.

    Uses a simple keyword heuristic: iterates through priority-ordered rules
    and returns the first matching class. Falls back to
    ``algorithm_implementation`` when no keywords match.

    Args:
        description: Natural language feature description.

    Returns:
        One of the strings in TASK_CLASSES.
    """
    lower = description.lower()
    for task_class, keywords in _KEYWORD_RULES:
        for kw in keywords:
            if kw in lower:
                return task_class
    return "algorithm_implementation"


def compute_ece_by_bucket(
    samples: list[dict],
) -> dict[str, float]:
    """Compute Expected Calibration Error (ECE) per task class.

    ECE = mean(|predicted_conf - empirical_accuracy|) over all samples
    within each confidence decile bucket, then averaged across buckets.

    Args:
        samples: List of dicts with keys:
            - ``task_class`` (str): one of TASK_CLASSES
            - ``predicted_conf`` (float): confidence in [0, 1]
            - ``passed`` (bool): whether the task passed verification

    Returns:
        Dict mapping task_class → ECE (float in [0, 1]).
        Empty dict when samples is empty.
    """
    if not samples:
        return {}

    # Group samples by (task_class, confidence_bucket)
    # bucket_data[(task_class, bucket)] = (sum_predicted, pass_count, total)
    BucketKey = tuple  # (task_class, bucket_label)
    bucket_totals: dict[BucketKey, dict] = defaultdict(lambda: {"pred_sum": 0.0, "passes": 0, "total": 0})

    for sample in samples:
        tc = sample["task_class"]
        conf = float(sample["predicted_conf"])
        passed = bool(sample["passed"])
        bucket = _conf_to_bucket(conf)
        key = (tc, bucket)
        entry = bucket_totals[key]
        entry["pred_sum"] += conf
        entry["passes"] += 1 if passed else 0
        entry["total"] += 1

    # Compute per-(task_class, bucket) |predicted_avg - empirical| then
    # average across buckets per task class.
    class_bucket_errors: dict[str, list[float]] = defaultdict(list)
    for (tc, _bucket), entry in bucket_totals.items():
        n = entry["total"]
        avg_pred = entry["pred_sum"] / n
        empirical = entry["passes"] / n
        class_bucket_errors[tc].append(abs(avg_pred - empirical))

    return {tc: sum(errors) / len(errors) for tc, errors in class_bucket_errors.items()}


def _conf_to_bucket(confidence: float) -> str:
    """Map a [0,1] confidence score to a decile bucket label."""
    if confidence >= 1.0:
        return "0.9-1.0"
    decile = int(confidence * 10) / 10
    return f"{decile:.1f}-{decile + 0.1:.1f}"
