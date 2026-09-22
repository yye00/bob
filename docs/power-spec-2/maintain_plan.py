#!/usr/bin/env python3
"""Maintain local planning artifacts only. Never dispatch, qualify, or access hardware."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON constant: {value}")


def finite_float(value: str) -> float:
    result = float(value)
    require(math.isfinite(result), f"nonfinite JSON number: {value}")
    return result


def parse_json(text: str) -> dict:
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant, parse_float=finite_float)


def load(name: str) -> dict:
    return parse_json((HERE / name).read_text())


def source_rows() -> dict:
    result = {}
    for line in (ROOT / "power-spec-2/implementation_plan.md").read_text().splitlines():
        if not re.match(r"^\| [A-Z]-\d\d \|", line):
            continue
        ident, stage, description, dependencies, deliverable = [
            value.strip() for value in line.strip("|").split("|")
        ]
        require(ident not in result, f"duplicate source task: {ident}")
        result[ident] = {
            "stage": stage,
            "title": re.search(r"\*\*(.*?)\*\*", description).group(1),
            "reuse": description.split("Reuse: ", 1)[1],
            "dependencies": [] if dependencies == "None" else dependencies.split(", "),
            "deliverable": deliverable,
        }
    require(len(result) == 41, "source task set changed: reconcile the planning version")
    return result


def check_snapshot(snapshot: dict) -> None:
    require(snapshot["schema_version"] == "power-spec-2.local-source-snapshot.v1" and snapshot["release"] == "v0.4.1", "unknown snapshot schema/release")
    require(snapshot["complete_release_present"] is False, "incomplete import cannot assert completeness")
    require(snapshot["authority"] == "byte_identity_only_not_release_attestation", "snapshot authority widened")
    paths = [record["path"] for record in snapshot["files"]]
    require(len(paths) == len(set(paths)) == 9, "expected nine unique imported files")
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / "power-spec-2").glob("*.md")}
    require(set(paths) == actual, "import changed; explicitly reconcile source inventory")
    for record in snapshot["files"]:
        path = (ROOT / record["path"]).resolve()
        require(path.is_relative_to(ROOT / "power-spec-2"), "source path escapes spec directory")
        data = path.read_bytes()
        require(len(data) == record["bytes"], f"source size drift: {record['path']}")
        require(hashlib.sha256(data).hexdigest() == record["sha256"], f"source hash drift: {record['path']}")
    actual_links = []
    for record in snapshot["files"]:
        path = ROOT / record["path"]
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            target = target.split("#", 1)[0]
            if target and "://" not in target:
                actual_links.append((record["path"], target))
    require([(r["source"], r["declared_target"]) for r in snapshot["declared_links"]] == actual_links, "source link inventory incomplete")
    require("docs/normative-contract.md" in snapshot["missing_authorities"] and "evidence/backlog.json" in snapshot["missing_authorities"], "missing authorities omitted")
    for missing in snapshot["missing_authorities"]:
        require(not (ROOT / "power-spec-2" / missing).exists(), f"authority availability changed: {missing}")
    for record in snapshot["declared_links"]:
        source = ROOT / record["source"]
        declared = (source.parent / record["declared_target"]).resolve()
        flat = ROOT / "power-spec-2" / Path(record["declared_target"]).name
        status = "present" if declared.exists() else "relocated" if flat.is_file() else "missing"
        require(status == record["status"], f"source availability changed: {record['declared_target']}")
        expected = str((declared if status == "present" else flat).relative_to(ROOT)) if status != "missing" else None
        require(record["local_path"] == expected, "source relocation mismatch")


def unique_index(items: list[dict], name: str) -> dict:
    require(isinstance(items, list) and all(isinstance(item, dict) for item in items), f"invalid {name} list")
    result = {item["id"]: item for item in items}
    require(len(result) == len(items), f"duplicate {name} ID")
    return result


def check_registry(plan: dict) -> None:
    require(plan["schema_version"] == "power-spec-2.local-planning-backlog.v1" and plan["release"] == "v0.4.1", "unknown planning schema/release")
    require(plan["source_snapshot"] == "source-snapshot.json", "unknown source snapshot pointer")
    require(plan["authority"] == "planning_only_not_controller_admission", "plan authority widened")
    require(plan["status"] == "PLANNED" and plan["dispatch_ready"] is False, "plan cannot authorize dispatch")
    tasks = unique_index(plan["tasks"], "task")
    requirements = unique_index(plan["requirements"], "requirement")
    tests = unique_index(plan["test_families"], "test family")
    official = source_rows()
    require(plan["official_task_count"] == len(official) == 41, "official count mismatch")
    require(plan["local_migration_task_count"] == 4, "migration count mismatch")
    require(set(tasks) == set(official) | {f"MIG-{n:02}" for n in range(4)}, "task coverage mismatch")
    require(len(tests) == 17 and len(requirements) == 18, "requirement/test inventory mismatch")
    for requirement in requirements.values():
        path = (ROOT / requirement["source"]).resolve()
        require(path.is_relative_to(ROOT / "power-spec-2") and path.is_file(), f"missing/current-authority source: {requirement['id']}")
        require(set(requirement["test_families"]) <= tests.keys(), f"unknown requirement tests: {requirement['id']}")
    required_fields = {
        "stage", "title", "reuse", "dependencies", "deliverable", "origin", "status",
        "dispatch_ready", "requirements", "test_families", "migration_dependencies",
        "conditional_gates", "implementation_steps", "acceptance", "target_surfaces",
        "input_access", "output_contract", "native_test_rule", "repair_policy", "validator",
        "blocked_on", "acceptance_level", "known_artifact_types", "local_delivery",
    }
    edges = {}
    for ident, task in tasks.items():
        require(required_fields <= task.keys(), f"incomplete task: {ident}")
        require(task["status"] == "PLANNED" and task["dispatch_ready"] is False, f"false readiness: {ident}")
        for field in required_fields - {"dependencies", "migration_dependencies", "conditional_gates", "dispatch_ready", "known_artifact_types"}:
            require(task[field], f"empty {field}: {ident}")
        for field in ["dependencies", "migration_dependencies", "requirements", "test_families", "implementation_steps", "acceptance", "target_surfaces", "blocked_on", "known_artifact_types"]:
            require(isinstance(task[field], list) and all(isinstance(v, str) and v.strip() for v in task[field]), f"invalid string list {field}: {ident}")
        require(isinstance(task["conditional_gates"], list) and all(isinstance(g, dict) for g in task["conditional_gates"]), f"invalid conditional gates: {ident}")
        local = task["local_delivery"]
        require(isinstance(local, dict) and local.get("status") == "PLANNED_NOT_ACCEPTED", f"local evidence cannot accept a task: {ident}")
        require(local.get("location_class") in {"local", "hybrid", "local_after_sources", "target_acquisition", "deployment", "reference_artifacts", "other_architecture", "later_physical", "later_distributed"}, f"unknown location class: {ident}")
        for key in ["before_mi355", "remaining_gate", "evidence_index"]:
            require(isinstance(local.get(key), str) and local[key].strip(), f"incomplete local handoff: {ident}/{key}")
        require(len(task["implementation_steps"]) >= 2 and len(task["acceptance"]) >= 2, f"underspecified task: {ident}")
        require(set(task["requirements"]) <= requirements.keys(), f"unknown requirement: {ident}")
        require(set(task["test_families"]) <= tests.keys(), f"unknown test family: {ident}")
        for requirement in task["requirements"]:
            if requirement != "R-SCOPE":
                require(set(requirements[requirement]["test_families"]) <= set(task["test_families"]), f"unverified requirement: {ident}/{requirement}")
        if ident in official:
            for key, value in official[ident].items():
                require(task[key] == value, f"source {key} mismatch: {ident}")
            require(task["origin"] == "power-spec-2/implementation_plan.md#backlog", f"wrong official origin: {ident}")
            require("MIG-00" in task["migration_dependencies"], f"source intake bypass: {ident}")
        else:
            require(task["origin"] == "local_migration_plan_not_official_backlog", f"false official origin: {ident}")
        dependencies = task["dependencies"] + task["migration_dependencies"]
        require(len(dependencies) == len(set(dependencies)), f"duplicate dependency: {ident}")
        for gate in task["conditional_gates"]:
            require(gate.get("kind") and gate.get("rule"), f"incomplete conditional gate: {ident}")
            dependencies += gate.get("requires", []) + gate.get("candidate_tasks", [])
        require(set(dependencies) <= tasks.keys(), f"unknown dependency: {ident}")
        edges[ident] = set(dependencies)
    require(set().union(*(set(t["requirements"]) for t in tasks.values())) == set(requirements), "uncovered requirement")
    require(set().union(*(set(t["test_families"]) for t in tasks.values())) == set(tests), "uncovered test family")
    visiting, visited = set(), set()

    def visit(ident: str) -> None:
        require(ident not in visiting, f"dependency cycle at {ident}")
        if ident in visited:
            return
        visiting.add(ident)
        for dep in edges[ident]:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)

    for ident in tasks:
        visit(ident)
    require("MIG-01" in tasks["A-01"]["migration_dependencies"], "Bob compatibility gate missing")
    require("MIG-02" in tasks["F-04"]["migration_dependencies"], "dependency inventory gate missing")
    native_gates = [g for g in tasks["V-04"]["conditional_gates"] if g["kind"] == "selected_native_reference"]
    require(len(native_gates) == 1 and set(native_gates[0]["candidate_tasks"]) == {"V-01", "V-02", "V-03"}, "V-04 selected reference gate missing")
    universal = {g["kind"]: g for g in plan["universal_claim_gates"]}
    for kind, dependency in [("selected_region_full_workload_claim", "C-02"), ("derivative_or_approximate_inference_claim", "U-02"), ("numerical_qualification", "Q-01")]:
        require(universal.get(kind, {}).get("requires") == [dependency], f"universal claim gate missing: {kind}")
    for ident in ["P-01", "P-02", "P-04", "P-05", "B-02", "B-03", "B-04", "H-01", "M-01", "N-01"]:
        gates = {g["kind"]: g for g in tasks[ident]["conditional_gates"]}
        require(gates.get("selected_region_full_workload_claim", {}).get("requires") == ["C-02"], f"reduction gate missing: {ident}")
        require(gates.get("derivative_or_approximate_inference_claim", {}).get("requires") == ["U-02"], f"numerical-method gate missing: {ident}")
    for ident in ["F-08", "K-02", "P-01", "X-05", "P-02", "P-04", "P-05", "B-02", "B-03", "B-04", "H-01", "M-01", "N-01"]:
        require(any(g["kind"] == "numerical_qualification" and g.get("requires") == ["Q-01"] for g in tasks[ident]["conditional_gates"]), f"acceptance policy gate missing: {ident}")


def render(plan: dict) -> str:
    lines = [
        "# Generated planning task packets", "",
        "Generated from `backlog.json` by `maintain_plan.py render`. Do not edit this view.", "",
        "**Planning only: all 41 source tasks and four local migration tasks remain PLANNED; none is dispatch-ready.**",
        "Read [README](README.md), [Bob migration](BOB_MIGRATION.md), [validation families](VALIDATION.md) and [third-party migration](../../../third_party/POWER_SPEC_2_MIGRATION.md).",
        "Requirements and T-* families are local traceability IDs pending recovery of the original normative registry. Source-table dependencies are reproduced exactly; additional gates do not authorize work.", "",
        "## Universal claim gates", "",
    ]
    lines += [f"- {g['kind']} ({', '.join(g['requires'])}): {g['rule']}" for g in plan["universal_claim_gates"]]
    lines += ["", "## Overview", "", "| Task | Stage | Objective | Source dependencies | Migration prerequisites |", "| --- | --- | --- | --- | --- |"]
    tasks = plan["tasks"]
    for task in tasks:
        lines.append(f"| [{task['id']}](#{task['id'].lower()}) | {task['stage']} | {task['title']} | {', '.join(task['dependencies']) or 'None'} | {', '.join(task['migration_dependencies']) or 'None'} |")
    for task in tasks:
        lines += ["", f"## {task['id']}", "", f"**{task['title']}** — {task['stage']}; PLANNED; dispatch-ready: false.", "",
                  f"Source: `{task['origin']}`. Requirements: {', '.join(task['requirements'])}.", "",
                  f"Source dependencies: {', '.join(task['dependencies']) or 'None'}. Migration prerequisites: {', '.join(task['migration_dependencies']) or 'None'}.", "",
                  f"Reuse: {task['reuse']}.", "", "Implementation steps:", ""]
        lines += [f"{i}. {step}." for i, step in enumerate(task["implementation_steps"], 1)]
        lines += ["", "Observable acceptance:", ""]
        lines += [f"- {criterion}." for criterion in task["acceptance"]]
        lines += ["", f"Validation: **{', '.join(task['test_families'])}**; use each family's positive, boundary, failure and deliberate-defect cases in [VALIDATION](VALIDATION.md).", "",
                  f"Before MI355 ({task['local_delivery']['location_class']}): {task['local_delivery']['before_mi355']}", "",
                  f"Remaining external/input gate: {task['local_delivery']['remaining_gate']}", "",
                  f"Native/public tests: {task['native_test_rule']}", "",
                  f"Implementation surfaces (resolve exact child paths before admission): {'; '.join(task['target_surfaces'])}.", "",
                  f"Input access: {task['input_access']}", "", f"Outputs: {task['output_contract']}", "",
                  f"Validator: {task['validator']}. Acceptance level: {task['acceptance_level']}", "",
                  f"Repair/resources: {task['repair_policy']}", "", "Conditional and blocked gates:", ""]
        lines += [f"- {gate['kind']}: {gate['rule']} Dependency IDs: {', '.join(gate.get('requires', []) + gate.get('candidate_tasks', []))}." for gate in task["conditional_gates"]]
        lines += [f"- {block}" for block in task["blocked_on"]]
    return "\n".join(lines) + "\n"


def check_docs(plan: dict) -> None:
    require((HERE / "TASKS.md").read_text() == render(plan), "TASKS.md stale: run render")
    documents = list(HERE.glob("*.md")) + [ROOT / "third_party/POWER_SPEC_2_MIGRATION.md", ROOT / "third_party/README.md"]
    for path in documents:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            target = target.split("#", 1)[0]
            if not target or "://" in target:
                continue
            require((path.parent / target).exists(), f"broken local link: {path.name}: {target}")
    validation = (HERE / "VALIDATION.md").read_text()
    for family in plan["test_families"]:
        require(family["id"] in validation, f"missing detailed validation family: {family['id']}")
    tasks = {t["id"]: t for t in plan["tasks"]}
    for ident, task in tasks.items():
        require((ROOT / task["local_delivery"]["evidence_index"]).is_file(), f"missing local evidence index: {ident}")
    for line in validation.splitlines():
        if not line.startswith("| T-"):
            continue
        family, primary, *_ = [s.strip() for s in line.strip("|").split("|")]
        primary = re.sub(r"([A-Z])-(\d\d) through \1-(\d\d)", lambda m: ", ".join(f"{m[1]}-{n:02}" for n in range(int(m[2]), int(m[3]) + 1)), primary)
        for ident in re.findall(r"[A-Z]-\d\d", primary):
            require(family in tasks[ident]["test_families"], f"task/validation table mismatch: {ident}/{family}")


def self_test(plan: dict, snapshot: dict) -> int:
    # In-memory defects only. A rejection must come from structural validation,
    # not an intentionally stale generated Markdown view.
    def task(data: dict, ident: str) -> dict:
        return next(t for t in data["tasks"] if t["id"] == ident)

    mutations = [
        ("unknown schema", lambda p: p.update(schema_version="unknown.v99")),
        ("missing snapshot pointer", lambda p: p.update(source_snapshot="missing.json")),
        ("scalar steps", lambda p: task(p, "F-01").update(implementation_steps="AB")),
        ("nonexistent requirement source", lambda p: p["requirements"][0].update(source="power-spec-2/missing.md")),
        ("duplicate task", lambda p: p["tasks"].append(copy.deepcopy(p["tasks"][0]))),
        ("missing official task", lambda p: p["tasks"].pop(0)),
        ("false readiness", lambda p: task(p, "F-01").update(dispatch_ready=True)),
        ("false completion", lambda p: task(p, "F-01").update(status="ACCEPTED")),
        ("authority widening", lambda p: p.update(authority="controller_admitted")),
        ("source edge changed", lambda p: task(p, "P-02").update(dependencies=["P-01", "Q-01"])),
        ("unknown dependency", lambda p: task(p, "MIG-00")["dependencies"].append("UNKNOWN")),
        ("cycle", lambda p: task(p, "MIG-00")["dependencies"].append("F-01")),
        ("no validator", lambda p: task(p, "A-02").update(validator="")),
        ("no acceptance", lambda p: task(p, "F-07").update(acceptance=[])),
        ("unknown test family", lambda p: task(p, "X-05")["test_families"].append("T-FAKE")),
        ("unknown requirement", lambda p: task(p, "X-05")["requirements"].append("R-FAKE")),
        ("unverified requirement", lambda p: task(p, "X-05")["test_families"].remove("T-SCORE")),
        ("missing selected reference", lambda p: task(p, "V-04").update(conditional_gates=[])),
        ("missing conditional reduction", lambda p: task(p, "P-02").update(conditional_gates=[g for g in task(p, "P-02")["conditional_gates"] if g["kind"] != "selected_region_full_workload_claim"])),
        ("missing policy gate", lambda p: task(p, "P-04").update(conditional_gates=[])),
        ("missing universal qualification policy", lambda p: p.update(universal_claim_gates=[])),
        ("native smoke falsely accepts task", lambda p: task(p, "F-04")["local_delivery"].update(status="ACCEPTED")),
        ("missing target gate", lambda p: task(p, "X-04")["local_delivery"].update(remaining_gate="")),
    ]
    for name, mutate in mutations:
        broken = copy.deepcopy(plan)
        mutate(broken)
        try:
            check_registry(broken)
        except ValueError:
            continue
        raise ValueError(f"self-test failed to reject: {name}")
    broken_snapshot = copy.deepcopy(snapshot)
    broken_snapshot["files"][0]["sha256"] = "0" * 64
    try:
        check_snapshot(broken_snapshot)
    except ValueError:
        pass
    else:
        raise ValueError("self-test failed to reject source digest corruption")
    broken_snapshot = copy.deepcopy(snapshot)
    broken_snapshot["declared_links"].pop()
    try:
        check_snapshot(broken_snapshot)
    except ValueError:
        pass
    else:
        raise ValueError("self-test failed to reject omitted source gap")
    for invalid in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}']:
        try:
            parse_json(invalid)
        except ValueError:
            continue
        raise ValueError("self-test failed strict JSON parsing")
    return len(mutations) + 6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "render", "self-test"])
    args = parser.parse_args()
    plan, snapshot = load("backlog.json"), load("source-snapshot.json")
    check_snapshot(snapshot)
    check_registry(plan)
    if args.command == "render":
        (HERE / "TASKS.md").write_text(render(plan))
        print("Rendered 45 planning packets; no task dispatched or accepted.")
    elif args.command == "self-test":
        count = self_test(plan, snapshot)
        print(f"PASS: {count} planning-validator rejection cases; no production or hardware qualification.")
    else:
        check_docs(plan)
        missing = sum(item["status"] == "missing" for item in snapshot["declared_links"])
        print(f"PASS: 9 source hashes, 41 official + 4 local tasks, DAG/conditional gates, 18 requirements, 17 test families, generated view and local links.")
        print(f"KNOWN GAP: {missing} referenced source links are absent; complete release/authority and runtime qualification remain unresolved.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
