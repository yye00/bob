#!/usr/bin/env python3
"""Check/render local acquisition and implementation planning data; never execute tasks."""
from __future__ import annotations

import argparse
import copy
import re
from pathlib import Path

from maintain_plan import HERE, ROOT, load, parse_json, require

PACKAGES = ROOT / "third_party/planning/power-spec-2/packages.json"
PACKAGE_VIEW = PACKAGES.with_name("PACKAGE_READINESS.md")
QUEUE_VIEW = HERE / "BUILD_QUEUE.md"
ASSET_IDS = set("bob native-tools numerics test-schema hypothesis contracts app-baseline sst-core sst-elements amd-sst ippm accelergy hwcomponents power-content harness perfetto amdsmi amd-devlibs rocprofiler rocm-toolchain papi drampower mgpusim salib transferbench compute-bench vllm pytorch workload-assets aisimulate energaizer accelsim ramulator2 gem5 pymc dakota pymor astra-infragraph vidur attestation isolation sglang cacti-mcpat opensta pwrapi specptdaemon".split())
TASK_IDS = {f"B{i:02}" for i in range(4)} | {f"D{i:02}" for i in range(11)} | {f"S{i:02}" for i in range(8)} | {f"R{i:02}" for i in range(3)}


def indexed(items: list, expected: set, name: str) -> dict:
    require(isinstance(items, list) and all(isinstance(x, dict) for x in items), f"invalid {name}")
    result = {x["id"]: x for x in items}
    require(len(result) == len(items) and set(result) == expected, f"{name} missing, duplicate or unexpected ID")
    return result


def strings(value: object, name: str, allow_empty: bool = False) -> None:
    require(isinstance(value, list) and (allow_empty or value), f"invalid list: {name}")
    require(all(isinstance(s, str) and s.strip() for s in value), f"invalid text: {name}")
    require(len(value) == len(set(value)), f"duplicate list item: {name}")


def validate(packages: dict, queue: dict) -> None:
    require(packages["schema_version"] == "power-spec-2.package-work-plan.v1", "package schema changed")
    require(packages["authority"] == "planning_only_not_dependency_admission", "package authority widened")
    require(queue["schema_version"] == "power-spec-2.local-build-queue.v1", "queue schema changed")
    require(queue["authority"] == "planning_only_not_controller_admission", "queue authority widened")
    require(queue["status"] in {"PLANNED", "LOCAL_IMPLEMENTATION"} and queue["dispatch_ready"] is False, "queue cannot dispatch")
    require(queue["package_plan"] == str(PACKAGES.relative_to(ROOT)), "wrong package registry")
    require(queue["canonical_backlog"] == "bob/docs/power-spec-2/backlog.json", "wrong canonical backlog")
    assets = indexed(packages["assets"], ASSET_IDS, "assets")
    tasks = indexed(queue["tasks"], TASK_IDS, "tasks")
    require(sum(t["status"] == "IN_PROGRESS" for t in tasks.values()) <= 1, "only one slice may be in progress")
    canonical = {t["id"] for t in load("backlog.json")["tasks"]}
    states = {"local_partial", "native_pass_scoped", "not_acquired", "owner_source_missing", "restricted", "source_partial", "installed_partial"}
    priorities = {"bootstrap", "required", "compare", "selected_reference", "conditional", "deferred", "historical"}
    for a in assets.values():
        require(a["observed_state"] in states and a["priority"] in priorities, f"invalid state: {a['id']}")
        require(a["admitted"] is False and a["portable_closure"] is False, "planning cannot assert dependency admission/portable closure")
        require(a["proposed_pin"] is None, "reconcile newly selected pin with acquisition evidence before changing planning baseline")
        for field in ["name", "source_locator", "acquisition_work", "remaining_target_gate"]:
            require(isinstance(a[field], str) and a[field].strip(), f"missing {a['id']} {field}")
        strings(a["local_acceptance"], "asset acceptance")
        strings(a["evidence"], "asset evidence")
        for evidence in a["evidence"]:
            p = (ROOT / evidence).resolve()
            require(p.is_relative_to(ROOT / "third_party/receipts") and p.is_file(), f"invalid evidence path: {evidence}")
    strings(queue["shared_dispatch_requirements"], "dispatch requirements")
    gates = queue["external_gate_definitions"]
    require(all(isinstance(v, str) and v.strip() for v in gates.values()), "empty external gate")
    for profile in queue["budget_profiles"].values():
        for key in ["max_agent_turns", "max_repair_attempts", "wall_seconds", "cpu_threads", "memory_gib"]:
            require(type(profile[key]) is int and profile[key] > 0, "budget must be positive finite integer")
        require(type(profile["max_blind_reveals"]) is int and profile["max_blind_reveals"] == 0, "public queue cannot reveal blind labels")
    for t in tasks.values():
        require(t["status"] in {"PLANNED", "IN_PROGRESS", "LOCAL_DONE", "PARTIAL", "BLOCKED_OWNER"} and t["dispatch_ready"] is False and t["build_before_mi355"] is True, "task cannot widen acceptance/location")
        if t["status"] != "PLANNED":
            execution = t.get("execution")
            require(isinstance(execution, dict), "local status needs an execution record")
            require(execution.get("actor") == "direct_codex" and execution.get("claim") == "public_local_only_not_independent_acceptance", "local status cannot assert Bob authorship or acceptance")
            require(isinstance(execution.get("summary"), str) and execution["summary"].strip(), "local status needs a summary")
            receipt = (ROOT / execution["receipt"]).resolve()
            require(receipt.is_relative_to(ROOT / "third_party/receipts") and receipt.is_file(), "local status needs retained evidence")
        require(t["model_id"] is None and t["max_cost_usd"] is None, "unselected dispatch identity/cost must remain unresolved")
        require(t["budget_profile"] in queue["budget_profiles"], "unknown budget profile")
        require(t["input_class"] == "public_or_authorized_source_only_no_sealed_labels", "input access widened")
        for key in ["parent_tasks", "input_assets", "proposed_outputs", "implementation_steps", "validation"]:
            strings(t[key], key)
        for key in ["requires_tasks", "integration_requires_tasks", "external_gates"]:
            strings(t[key], key, allow_empty=True)
        require(set(t["parent_tasks"]) <= canonical, "unknown canonical parent")
        require(set(t["input_assets"]) <= assets.keys(), "unknown asset")
        require(set(t["requires_tasks"]) <= tasks.keys(), "unknown dependency")
        require(set(t["integration_requires_tasks"]) <= tasks.keys(), "unknown integration dependency")
        require(set(t["external_gates"]) <= gates.keys(), "unknown external gate")
        require(t["acceptance_limit"].strip() and t["title"].strip(), "missing scope/limit")
    visited, active = set(), set()
    def visit(ident: str) -> None:
        require(ident not in active, f"dependency cycle: {ident}")
        if ident in visited:
            return
        active.add(ident)
        for dep in tasks[ident]["requires_tasks"] + tasks[ident]["integration_requires_tasks"]:
            visit(dep)
        active.remove(ident)
        visited.add(ident)
    for ident in tasks:
        visit(ident)
    require(set(tasks["D03"]["input_assets"]) >= {"accelergy", "hwcomponents"}, "open path comparison missing")
    require("ippm" not in tasks["D03"]["input_assets"], "open path cannot require IPPM")
    require("artifact_network" in tasks["D00"]["external_gates"], "acquisition availability gate missing")
    require("complete_contracts" in tasks["S00"]["external_gates"], "missing authority gate")
    require("capable_isolation_host" in tasks["R00"]["external_gates"], "actual deployment gate missing")
    require(set(tasks["R02"]["requires_tasks"]) >= {"R01", "D07", "D10"}, "handoff gate missing")


def package_view(packages: dict) -> str:
    lines = ["# Package and input readiness", "", "Generated from [packages.json](packages.json); change the JSON and run the plan renderer.", "",
             "**46 packages/input groups; planning snapshot from 2026-09-21.** This snapshot makes no dependency-admission or portable-closure claim. Its observed states precede the [2026-09-22 build results](LOCAL_BUILD_RESULTS_2026-09-22.md). This is an acquisition/build work plan, not a transitive source lock; locator URLs need immutable resolution before use.", "",
             "Use the [Bob build queue](../../../bob/docs/power-spec-2/BUILD_QUEUE.md), [acquisition strategy](../../PRE_MI355_ACQUISITION.md) and [probe receipt](../../receipts/local-readiness-2026-09-21/acquisition/README.md).", "",
             "| ID | Package/input | Priority | Observed state |", "| --- | --- | --- | --- |"]
    for a in packages["assets"]:
        lines.append(f"| [{a['id']}](#{a['id']}) | {a['name']} | {a['priority']} | {a['observed_state']} |")
    for a in packages["assets"]:
        lines += ["", f"## {a['id']}", "", f"**{a['name']}** — {a['priority']}; {a['observed_state']}.", "", f"Locator: {a['source_locator']}", "", f"Acquire/prepare: {a['acquisition_work']}", "", "Local exit checks:", ""]
        lines += [f"- {v}" for v in a["local_acceptance"]]
        lines += ["", f"Remaining boundary: {a['remaining_target_gate']}", "", "Evidence: " + ", ".join(f"[{Path(p).name}](../../{p.removeprefix('third_party/')})" for p in a["evidence"]) + "."]
    return "\n".join(lines) + "\n"


def queue_view(queue: dict) -> str:
    lines = ["# Local Bob implementation queue", "", "Generated from [local-build-queue.json](local-build-queue.json). Read [how to run this queue](BOB_LOCAL_BUILD_QUEUE.md) first.", "",
             "**26 software slices; local execution status grants no Bob dispatch or scientific acceptance.** LOCAL_DONE means the documented public software scope passed local checks; PARTIAL retains unresolved scope. APP denotes the application root selected in S00, never Bob core. Local prerequisites do not replace canonical scientific dependencies or qualification gates. Integration dependencies apply when binding standalone components to final app contracts. D00/D02 prerequisites mean the exact dependency subset consumed, not every package candidate.", "",
             "| Slice | Status | Objective | Local prerequisites | Explicit external gates |", "| --- | --- | --- | --- | --- |"]
    for t in queue["tasks"]:
        lines.append(f"| [{t['id']}](#{t['id'].lower()}) | {t['status']} | {t['title']} | {', '.join(t['requires_tasks']) or 'None'} | {', '.join(t['external_gates']) or 'Shared dispatch requirements'} |")
    lines += ["", "## Shared dispatch requirements", ""] + [f"- {r}" for r in queue["shared_dispatch_requirements"]]
    lines += ["", "## External gates", ""] + [f"- **{k}:** {v}" for k, v in queue["external_gate_definitions"].items()]
    for t in queue["tasks"]:
        lines += ["", f"## {t['id']}", "", f"**{t['title']}**", "", f"Canonical parents: {', '.join(t['parent_tasks'])}. Asset IDs: {', '.join(t['input_assets'])}.", "",
                  f"Software prerequisites: {', '.join(t['requires_tasks']) or 'None'}. Explicit external gates: {', '.join(t['external_gates']) or 'Shared dispatch requirements'}.", "",
                  f"Final contract-integration prerequisites: {', '.join(t['integration_requires_tasks']) or 'None beyond software prerequisites'}.", "",
                  "Proposed outputs:", ""] + [f"- {p}" for p in t["proposed_outputs"]]
        lines += ["", "Implementation:", ""] + [f"{i}. {s}" for i, s in enumerate(t["implementation_steps"], 1)]
        lines += ["", "Validation:", ""] + [f"- {s}" for s in t["validation"]]
        lines += ["", f"Acceptance limit: {t['acceptance_limit']}"]
        if "execution" in t:
            e = t["execution"]
            lines += ["", f"Local status: **{t['status']}** — {e['summary']}", "", f"Evidence: [{Path(e['receipt']).name}](../../../{e['receipt']}). Direct Codex work; not Bob-authored or independently accepted."]
    return "\n".join(lines) + "\n"


def self_test(packages: dict, queue: dict) -> int:
    mutations = [
        lambda p,q: p.update(authority="admitted"),
        lambda p,q: p["assets"].pop(),
        lambda p,q: p["assets"].append(copy.deepcopy(p["assets"][0])),
        lambda p,q: p["assets"][0].update(admitted=True),
        lambda p,q: p["assets"][0].update(portable_closure=True),
        lambda p,q: p["assets"][0].update(proposed_pin="main"),
        lambda p,q: p["assets"][0].update(evidence=["/etc/passwd"]),
        lambda p,q: p["assets"][0].update(local_acceptance=[]),
        lambda p,q: q.update(dispatch_ready=True),
        lambda p,q: q["tasks"].pop(),
        lambda p,q: q["tasks"][0].update(requires_tasks=["B00"]),
        lambda p,q: q["tasks"][0].update(integration_requires_tasks=["B00"]),
        lambda p,q: q["tasks"][0].update(integration_requires_tasks=["UNKNOWN"]),
        lambda p,q: q["tasks"][0].update(parent_tasks=["UNKNOWN"]),
        lambda p,q: q["tasks"][0].update(input_assets=["UNKNOWN"]),
        lambda p,q: q["tasks"][0].update(external_gates=["UNKNOWN"]),
        lambda p,q: q["tasks"][0].update(validation=[]),
        lambda p,q: q["tasks"][0].update(input_class="raw_labels"),
        lambda p,q: q["budget_profiles"]["local_public_slice"].update(wall_seconds=0),
        lambda p,q: q["budget_profiles"]["local_public_slice"].update(max_agent_turns=True),
        lambda p,q: q["budget_profiles"]["local_public_slice"].update(max_blind_reveals=1),
        lambda p,q: q["tasks"][-1].update(requires_tasks=[]),
        lambda p,q: q["tasks"][0].update(status="SCIENTIFICALLY_ACCEPTED"),
        lambda p,q: q["tasks"][0].update(status="LOCAL_DONE", execution=None),
        lambda p,q: q["tasks"][0].update(status="LOCAL_DONE", execution={"actor": "Bob"}),
        lambda p,q: (q["tasks"][0].update(status="IN_PROGRESS"), q["tasks"][1].update(status="IN_PROGRESS")),
        lambda p,q: q["tasks"][0].update(status="LOCAL_DONE", execution={"actor": "direct_codex", "claim": "independently_accepted", "summary": "invalid", "receipt": "third_party/receipts/none"}),
        lambda p,q: q["tasks"][0].update(status="LOCAL_DONE", execution={"actor": "direct_codex", "claim": "public_local_only_not_independent_acceptance", "summary": "invalid", "receipt": "/etc/passwd"}),
    ]
    for i, mutation in enumerate(mutations):
        p, q = copy.deepcopy(packages), copy.deepcopy(queue)
        mutation(p, q)
        try:
            validate(p, q)
        except (ValueError, KeyError, TypeError):
            continue
        raise ValueError(f"mutation {i} was accepted")
    return len(mutations)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "render", "self-test"])
    command = parser.parse_args().command
    packages, queue = parse_json(PACKAGES.read_text()), load("local-build-queue.json")
    validate(packages, queue)
    views = [(PACKAGE_VIEW, package_view(packages)), (QUEUE_VIEW, queue_view(queue))]
    if command == "render":
        for path, content in views:
            path.write_text(content)
        print("Rendered 46 asset records and 26 local slices; no task dispatched.")
    elif command == "self-test":
        print(f"PASS: {self_test(packages, queue)} acquisition/queue rejection cases.")
    else:
        for path, content in views:
            require(path.read_text() == content, f"stale generated view: {path}")
        for path in [p for p, _ in views] + [ROOT / "third_party/PRE_MI355_ACQUISITION.md", HERE / "BOB_LOCAL_BUILD_QUEUE.md"]:
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                target = target.split("#", 1)[0]
                if target and "://" not in target:
                    require((path.parent / target).exists(), f"broken link: {path}: {target}")
        print("PASS: 46 assets, 26 slices, canonical parents, DAG, finite proposed budgets, evidence paths and generated views.")
        print("LIMIT: planning checks do not acquire packages, invoke Bob or establish scientific qualification.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
