"""
DAG Validator — Validates the task dependency graph.
=====================================================

Checks the work unit tree for structural integrity:
1. No cycles in dependency graph
2. All declared dependencies exist
3. All nodes reachable from roots
4. No orphaned nodes
5. Dependency ordering is consistent with tree depth

Called by the DecompositionEngine before and after processing
to catch structural issues early.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DAGValidationResult:
    """Result of DAG validation."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def __str__(self) -> str:
        if self.valid:
            w = f" ({len(self.warnings)} warnings)" if self.warnings else ""
            return f"DAG valid{w}: {self.stats}"
        return (
            f"DAG INVALID: {len(self.errors)} errors, "
            f"{len(self.warnings)} warnings\n"
            + "\n".join(f"  ✗ {e}" for e in self.errors)
        )


def validate_work_unit_dag(
    tree: dict[str, Any],
    check_content_deps: bool = True,
) -> DAGValidationResult:
    """Validate the work unit tree as a DAG.

    Checks:
    1. No cycles via parent_id chain
    2. All parent_ids reference existing nodes
    3. All children reference existing nodes
    4. All nodes reachable from roots (nodes with no parent)
    5. Optional: content.depends_on references are valid task IDs

    Args:
        tree: Dict of unit_id → WorkUnit
        check_content_deps: Also validate content.depends_on references

    Returns:
        DAGValidationResult with errors, warnings, and stats
    """
    result = DAGValidationResult()

    if not tree:
        result.stats = {"nodes": 0}
        return result

    node_ids = set(tree.keys())
    roots = []

    # --- Check 1: Parent references are valid ---
    for uid, unit in tree.items():
        parent_id = getattr(unit, "parent_id", None)
        if parent_id is None:
            roots.append(uid)
        elif parent_id not in node_ids:
            result.add_error(
                f"Node {uid} references non-existent parent {parent_id}"
            )

    if not roots:
        result.add_error("No root nodes found (all nodes have parents)")

    # --- Check 2: Children references are valid ---
    for uid, unit in tree.items():
        children = getattr(unit, "children", [])
        for child_id in children:
            if child_id not in node_ids:
                result.add_error(
                    f"Node {uid} has non-existent child {child_id}"
                )

    # --- Check 3: Cycle detection via parent_id chain ---
    visited_global: set[str] = set()
    for uid in node_ids:
        if uid in visited_global:
            continue
        path: set[str] = set()
        current = uid
        while current is not None:
            if current in path:
                result.add_error(
                    f"Cycle detected: node {current} is in its own "
                    f"ancestor chain (from {uid})"
                )
                break
            if current in visited_global:
                break
            path.add(current)
            unit = tree.get(current)
            if unit is None:
                break
            current = getattr(unit, "parent_id", None)
        visited_global |= path

    # --- Check 4: All nodes reachable from roots ---
    reachable: set[str] = set()

    def _walk(node_id: str) -> None:
        if node_id in reachable:
            return
        reachable.add(node_id)
        unit = tree.get(node_id)
        if unit is None:
            return
        for child_id in getattr(unit, "children", []):
            _walk(child_id)

    for root_id in roots:
        _walk(root_id)

    orphans = node_ids - reachable
    if orphans:
        result.add_warning(
            f"Orphaned nodes (not reachable from roots): {orphans}"
        )

    # --- Check 5: Content depends_on references ---
    if check_content_deps:
        # Build a set of task IDs from content
        task_ids: set[str] = set()
        for unit in tree.values():
            content = getattr(unit, "content", {})
            if isinstance(content, dict):
                tid = content.get("id", "")
                if tid:
                    task_ids.add(tid)

        for unit in tree.values():
            content = getattr(unit, "content", {})
            if not isinstance(content, dict):
                continue
            deps = content.get("depends_on", [])
            tid = content.get("id", "")
            for dep in deps:
                if dep and dep not in task_ids:
                    result.add_warning(
                        f"Task {tid} depends_on '{dep}' which is not "
                        f"a known task ID"
                    )

    # --- Stats ---
    max_depth = max(
        (getattr(u, "depth", 0) for u in tree.values()), default=0
    )
    result.stats = {
        "nodes": len(node_ids),
        "roots": len(roots),
        "orphans": len(orphans),
        "max_depth": max_depth,
    }

    return result


def validate_task_dependencies(tasks: list[dict]) -> DAGValidationResult:
    """Validate a flat list of task dicts (pre-engine, from Phase 0).

    Checks:
    1. No duplicate IDs
    2. All depends_on references exist
    3. No circular dependencies
    4. Topological ordering is possible

    Args:
        tasks: List of task dicts with 'id' and 'depends_on' fields

    Returns:
        DAGValidationResult
    """
    result = DAGValidationResult()

    if not tasks:
        result.stats = {"tasks": 0}
        return result

    # Build ID set and adjacency
    task_ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    duplicates: list[str] = []

    for t in tasks:
        tid = t.get("id", "")
        if not tid:
            result.add_error("Task with missing 'id' field")
            continue
        if tid in task_ids:
            duplicates.append(tid)
        task_ids.add(tid)
        graph[tid] = t.get("depends_on", []) or []

    if duplicates:
        result.add_error(f"Duplicate task IDs: {duplicates}")

    # Check references
    for tid, deps in graph.items():
        for dep in deps:
            if dep not in task_ids:
                result.add_error(
                    f"Task {tid} depends on non-existent task '{dep}'"
                )

    # Topological sort / cycle detection (Kahn's algorithm)
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    for tid, deps in graph.items():
        for dep in deps:
            if dep in task_ids:
                in_degree[tid] = in_degree.get(tid, 0)
                # dep → tid edge (tid depends on dep)

    # Rebuild in-degree from reverse perspective
    in_degree = {tid: 0 for tid in task_ids}
    reverse: dict[str, list[str]] = {tid: [] for tid in task_ids}
    for tid, deps in graph.items():
        for dep in deps:
            if dep in task_ids:
                in_degree[tid] += 1
                reverse[dep].append(tid)

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    sorted_count = 0

    while queue:
        node = queue.pop(0)
        sorted_count += 1
        for neighbor in reverse.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if sorted_count < len(task_ids):
        cycle_nodes = {
            tid for tid, deg in in_degree.items() if deg > 0
        }
        result.add_error(
            f"Circular dependencies detected among: {cycle_nodes}"
        )

    result.stats = {
        "tasks": len(task_ids),
        "dependencies": sum(len(d) for d in graph.values()),
        "has_valid_ordering": sorted_count == len(task_ids),
    }

    return result
