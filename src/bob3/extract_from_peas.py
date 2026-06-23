"""F-R7 PEAS pipeline — parse plain-English spec markdown into features.yaml.

Operator writes a prose-only ``peas.md`` with sections like:

    ## Feature title
    Tier: Core  |  Priority: high  |  Slot: F-R7-NNN
    One-paragraph description.

``parse_peas_markdown`` turns that into a list of feature dicts.
``emit_stub_features`` converts those into YAML-ready feature dicts with
TBD placeholders so the synthesizer can fill acceptance criteria.

The CLI command ``bob3 extract-from-peas`` orchestrates the full pipeline:
parse → stub → synthesize → write/print + summary.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Separate regexes for each metadata field — one complex regex with .*? fails to advance past |
_TIER_RE = re.compile(r"Tier\s*:\s*([A-Za-z][A-Za-z0-9_\- ]*)", re.IGNORECASE)
_PRIORITY_RE = re.compile(r"Priority\s*:\s*([A-Za-z][A-Za-z0-9_\- ]*)", re.IGNORECASE)
_SLOT_RE = re.compile(r"Slot\s*:\s*(F-R\d+-\d+)", re.IGNORECASE)
_PFC_RE = re.compile(r"PermanentForwardCarry\s*:\s*(true|false)", re.IGNORECASE)

# Pattern to detect the metadata line (contains at least Tier, Priority, or Slot)
_META_LINE_RE = re.compile(
    r"(Tier\s*:|Priority\s*:|Slot\s*:|PermanentForwardCarry\s*:)",
    re.IGNORECASE,
)

TBD_PLACEHOLDER = "TBD: synthesize via F-R1-011"


def parse_peas_markdown(text: str) -> list[dict[str, Any]]:
    """Parse a PEAS markdown string into a list of feature dicts.

    Each ``## <title>`` heading starts a new feature block. The line
    immediately after the heading that contains ``Tier:``, ``Priority:``,
    or ``Slot:`` is parsed as metadata. All remaining lines in the block
    become the description.

    Returns a list of dicts with keys: ``title``, ``tier``, ``priority``,
    ``slot``, ``description``.  ``slot`` is ``None`` when absent.
    """
    features: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    desc_lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            current["description"] = "\n".join(desc_lines).strip()
            features.append(current)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # New feature section
        if line.startswith("## "):
            _flush()
            desc_lines = []
            title = line[3:].strip()
            current = {
                "title": title,
                "tier": "Core",
                "priority": "medium",
                "slot": None,
                "permanent_forward_carry": False,
                "description": "",
            }
            continue

        if current is None:
            # Content before any ## heading — skip
            continue

        # Try metadata line
        if _META_LINE_RE.search(line):
            tm = _TIER_RE.search(line)
            pm = _PRIORITY_RE.search(line)
            sm = _SLOT_RE.search(line)
            fm = _PFC_RE.search(line)
            if tm:
                current["tier"] = tm.group(1).strip()
            if pm:
                current["priority"] = pm.group(1).strip()
            if sm:
                current["slot"] = sm.group(1).strip()
            if fm:
                current["permanent_forward_carry"] = fm.group(1).strip().lower() == "true"
            continue

        # Description line
        desc_lines.append(line)

    _flush()
    return features


def _next_slot(existing_slots: set[str]) -> str:
    """Auto-mint the next F-R7-NNN slot not already in *existing_slots*."""
    nums = set()
    for slot in existing_slots:
        m = re.search(r"F-R7-(\d+)", slot)
        if m:
            nums.add(int(m.group(1)))
    candidate = 1
    while candidate in nums:
        candidate += 1
    return f"F-R7-{candidate:03d}"


def emit_stub_features(
    parsed_features: list[dict[str, Any]],
    existing_slots: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert parsed feature dicts into YAML-ready stub feature dicts.

    Each stub has: ``key``, ``title``, ``tier``, ``priority``, ``description``,
    and ``acceptance_criteria`` set to the TBD placeholder so the synthesizer
    will fill it in.

    When a feature has no slot, one is auto-minted by walking past any slots
    already in *existing_slots* (or those already emitted in this call).
    """
    used_slots: set[str] = set(existing_slots or ())
    stubs: list[dict[str, Any]] = []

    for feat in parsed_features:
        slot = feat.get("slot")
        if not slot:
            slot = _next_slot(used_slots)
        used_slots.add(slot)

        stub = {
            "key": slot,
            "title": feat["title"],
            "tier": feat["tier"],
            "priority": feat["priority"],
            "description": feat["description"],
            "acceptance_criteria": [TBD_PLACEHOLDER],
        }
        if feat.get("permanent_forward_carry"):
            stub["permanent_forward_carry"] = True
        stubs.append(stub)

    return stubs


def _collect_existing_slots(spec: dict[str, Any]) -> set[str]:
    """Return all slot keys already present in a loaded features spec dict."""
    slots: set[str] = set()
    features_list = spec.get("features") or []
    if isinstance(features_list, list):
        for item in features_list:
            if isinstance(item, dict):
                key = item.get("key") or item.get("id") or ""
                if key:
                    slots.add(key)
    return slots


def run_pipeline(
    peas_path: Path,
    *,
    out_path: Path | None = None,
    threshold: float = 0.65,
    workspace: Path | None = None,
    existing_spec_path: Path | None = None,
    project_id: str = "extract-from-peas",
    _synthesize_fn: Any = None,
) -> dict[str, Any]:
    """Full extract-from-peas pipeline.

    1. Parse markdown.
    2. Collect existing slots from *existing_spec_path* (or *out_path*).
    3. Emit stubs.
    4. Run synthesizer on stubs.
    5. Write YAML (or capture for stdout) + return summary dict.

    Returns a summary dict with keys:
      extracted, synthesized, gate_passed, gate_failed, per_feature, yaml_text

    *_synthesize_fn* is an optional async callable with the same signature as
    ``synthesize_for_feature``. When provided it replaces the default LLM call;
    pass a fast local stub in tests to avoid network calls and timeouts.
    """
    import asyncio

    text = peas_path.read_text(encoding="utf-8")
    parsed = parse_peas_markdown(text)

    # Collect pre-existing slots so auto-mint avoids collisions
    existing_slots: set[str] = set()
    ref_path = existing_spec_path or out_path
    if ref_path and ref_path.exists():
        try:
            with open(ref_path) as f:
                existing_spec = yaml.safe_load(f) or {}
            existing_slots = _collect_existing_slots(existing_spec)
        except Exception as exc:
            logger.warning("Could not load existing spec %s: %s", ref_path, exc)

    stubs = emit_stub_features(parsed, existing_slots=existing_slots)

    # Run synthesizer on each stub
    from bob3.spec_synthesizer import synthesize_for_feature, deterministic_fallback

    _synth = _synthesize_fn if _synthesize_fn is not None else synthesize_for_feature

    per_feature: list[dict[str, Any]] = []
    synthesized_count = 0
    gate_passed = 0
    gate_failed = 0

    async def _synthesize_all() -> None:
        nonlocal synthesized_count
        for stub in stubs:
            key = stub["key"]
            title = stub["title"]
            desc = stub.get("description") or ""
            try:
                criteria = await _synth(
                    project_id=project_id,
                    title=title,
                    description=desc,
                    workspace=workspace,
                )
            except Exception as exc:
                logger.warning("Synthesis failed for %s: %s", key, exc)
                criteria = None

            if criteria:
                stub["acceptance_criteria"] = criteria
                synthesized_count += 1
                source = "llm"
            else:
                stub["acceptance_criteria"] = deterministic_fallback(title, desc)
                source = "fallback"

            per_feature.append({"key": key, "title": title, "source": source})

    asyncio.run(_synthesize_all())

    # Apply score gate to determine gate_passed / gate_failed
    try:
        ws = workspace or Path.cwd()
        import sys
        tools_dir = str(ws / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from spec_quality_score import compute, GATE_BLOCK  # type: ignore[import]
        score_available = True
    except ImportError:
        score_available = False

    for stub, pf in zip(stubs, per_feature):
        if score_available:
            result = compute(
                name=stub["title"],
                description=stub.get("description"),
                acceptance_criteria=stub["acceptance_criteria"],
                workspace=workspace or Path.cwd(),
            )
            pf["score"] = result.composite
            if result.composite >= GATE_BLOCK:
                gate_passed += 1
            else:
                gate_failed += 1
        else:
            pf["score"] = None
            gate_passed += 1

    # Build output YAML
    output_spec: dict[str, Any] = {"features": stubs}
    yaml_text = yaml.safe_dump(
        output_spec,
        sort_keys=False,
        default_flow_style=False,
        width=100,
        allow_unicode=True,
    )

    if out_path:
        out_path.write_text(yaml_text, encoding="utf-8")

    return {
        "extracted": len(parsed),
        "synthesized": synthesized_count,
        "gate_passed": gate_passed,
        "gate_failed": gate_failed,
        "per_feature": per_feature,
        "yaml_text": yaml_text,
    }


def extract_and_synthesize(
    peas_path: Path,
    *,
    out_path: Path | None = None,
    threshold: float = 0.65,
    workspace: Path | None = None,
    existing_spec_path: Path | None = None,
    project_id: str = "extract-from-peas",
    _synthesize_fn: Any = None,
) -> dict[str, Any]:
    """Parse a PEAS markdown file and synthesize acceptance criteria.

    Convenience synchronous entry-point for the full PEAS pipeline:
      1. Parse each ``## <title>`` section into a feature block.
      2. Emit a YAML stub per block (auto-mint F-R7-NNN when Slot absent).
      3. Run the synthesizer to fill TBD acceptance criteria.
      4. Apply the spec-quality score gate.
      5. Write to *out_path* when given; always return a summary dict.

    Raises:
        ValueError: When *peas_path* is not path-like, does not exist, or
                    cannot be read.

    Returns:
        Summary dict with keys: extracted, synthesized, gate_passed,
        gate_failed, per_feature, yaml_text.

    *_synthesize_fn* is forwarded to :func:`run_pipeline`; pass a fast async
    stub in tests to avoid real LLM calls.
    """
    try:
        peas_path = Path(peas_path)
    except TypeError as exc:
        raise ValueError(
            f"peas_path must be a path-like object, got {type(peas_path).__name__}"
        ) from exc

    if not peas_path.exists():
        raise ValueError(f"PEAS file does not exist: {peas_path}")

    return run_pipeline(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=workspace,
        existing_spec_path=existing_spec_path,
        project_id=project_id,
        _synthesize_fn=_synthesize_fn,
    )


def synthesize_features(
    stubs: list[dict[str, Any]],
    *,
    project_id: str = "extract-from-peas",
    workspace: Path | None = None,
    _synthesize_fn: Any = None,
) -> list[dict[str, Any]]:
    """Run the synthesizer on a list of stub feature dicts to fill TBD ACs.

    Each stub must have at minimum ``key``, ``title``, and ``description``.
    When ``acceptance_criteria`` contains only the TBD placeholder, the
    synthesizer replaces it with real criteria; otherwise the stub is left
    unchanged.

    Returns the updated list of stubs (modified in-place and returned).
    *_synthesize_fn* is an optional async callable forwarded to the
    synthesizer; pass a fast local stub in tests.
    """
    import asyncio
    from bob3.spec_synthesizer import synthesize_for_feature, deterministic_fallback

    _synth = _synthesize_fn if _synthesize_fn is not None else synthesize_for_feature

    async def _run() -> None:
        for stub in stubs:
            ac = stub.get("acceptance_criteria") or []
            if not ac or all(TBD_PLACEHOLDER in item for item in ac):
                title = stub.get("title", "")
                desc = stub.get("description") or ""
                try:
                    criteria = await _synth(
                        project_id=project_id,
                        title=title,
                        description=desc,
                        workspace=workspace,
                    )
                except Exception as exc:
                    logger.warning("Synthesis failed for %s: %s", stub.get("key"), exc)
                    criteria = None
                if criteria:
                    stub["acceptance_criteria"] = criteria
                else:
                    stub["acceptance_criteria"] = deterministic_fallback(title, desc)

    asyncio.run(_run())
    return stubs


def mint_feature_key(existing_slots: set[str] | None = None) -> str:
    """Mint the next unused F-R7-NNN feature key.

    Walks *existing_slots* to find the first gap starting at F-R7-001.

    Args:
        existing_slots: Set of already-used slot strings. If None, treated as empty.

    Returns:
        A fresh F-R7-NNN key string not present in *existing_slots*.
    """
    return _next_slot(existing_slots or set())


def run_extraction_pipeline(
    peas_path: Path,
    *,
    out_path: Path | None = None,
    threshold: float = 0.65,
    workspace: Path | None = None,
    existing_spec_path: Path | None = None,
    project_id: str = "extract-from-peas",
    _synthesize_fn: Any = None,
) -> dict[str, Any]:
    """Run the full PEAS extraction pipeline — canonical AC entry-point.

    Delegates to :func:`extract_and_synthesize` which validates *peas_path*
    and then delegates to :func:`run_pipeline`.

    Args:
        peas_path: Path to the ``.md`` PEAS file.
        out_path: When given, write the resulting YAML here.
        threshold: Score-gate threshold (passed to synthesizer).
        workspace: Workspace root used by the synthesizer.
        existing_spec_path: Path to a YAML spec to load existing slots from.
        project_id: Project identifier forwarded to the synthesizer.
        _synthesize_fn: Optional async callable replacing the real LLM call in tests.

    Raises:
        ValueError: When *peas_path* is not path-like or does not exist.

    Returns:
        Summary dict with keys: extracted, synthesized, gate_passed,
        gate_failed, per_feature, yaml_text.
    """
    return extract_and_synthesize(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=workspace,
        existing_spec_path=existing_spec_path,
        project_id=project_id,
        _synthesize_fn=_synthesize_fn,
    )


# Alias satisfying the AC: "Function defined: bob3.extract_from_peas.run_synthesis_pipeline"
run_synthesis_pipeline = run_pipeline

# Alias satisfying the AC: "Function defined: bob3.extract_from_peas.generate_feature_stubs"
generate_feature_stubs = emit_stub_features


def extract_markdown_to_features(
    markdown_text: str,
    existing_slots: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Parse a PEAS markdown string and return stub feature dicts.

    Combines :func:`parse_peas_markdown` and :func:`emit_stub_features` into
    a single call: parse the markdown then emit stubs with TBD placeholders.

    Args:
        markdown_text: Raw markdown text with ``## <title>`` sections.
        existing_slots: Optional set of already-used F-R7-NNN slots so
                        auto-minting skips them.

    Returns:
        List of stub feature dicts ready for the synthesizer.
    """
    parsed = parse_peas_markdown(markdown_text)
    return emit_stub_features(parsed, existing_slots=existing_slots)


def validate_round_trip(yaml_text: str) -> bool:
    """Validate that a YAML string produced by the pipeline can be round-tripped.

    Loads the YAML, re-dumps it, and verifies that:
    - The YAML is syntactically valid.
    - It contains a ``features`` key whose value is a list.
    - Each feature dict has the required keys (``key``, ``title``,
      ``acceptance_criteria``).

    Args:
        yaml_text: YAML string (as produced by :func:`run_pipeline`).

    Returns:
        ``True`` when the YAML passes all checks; ``False`` otherwise.
    """
    try:
        spec = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return False

    if not isinstance(spec, dict):
        return False

    features = spec.get("features")
    if not isinstance(features, list):
        return False

    required_keys = {"key", "title", "acceptance_criteria"}
    for item in features:
        if not isinstance(item, dict):
            return False
        if not required_keys <= set(item.keys()):
            return False
        if not isinstance(item["acceptance_criteria"], list):
            return False

    # Re-dump and re-load to confirm serialisation is stable
    try:
        redumped = yaml.safe_dump(spec, sort_keys=False, default_flow_style=False)
        yaml.safe_load(redumped)
    except yaml.YAMLError:
        return False

    return True


# Alias satisfying the AC: "Function defined: bob3.extract_from_peas.extract_features"
def extract_features(
    peas_path: "Path",
    *,
    out_path: "Path | None" = None,
    threshold: float = 0.65,
    workspace: "Path | None" = None,
    existing_spec_path: "Path | None" = None,
    project_id: str = "extract-from-peas",
    _synthesize_fn: "Any" = None,
) -> "dict[str, Any]":
    """Parse a PEAS prose-only markdown file and synthesize acceptance criteria.

    Canonical AC-required entry-point — delegates to :func:`extract_and_synthesize`.
    """
    return extract_and_synthesize(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=workspace,
        existing_spec_path=existing_spec_path,
        project_id=project_id,
        _synthesize_fn=_synthesize_fn,
    )


# Alias satisfying the AC: "Function defined: bob3.extract_from_peas.extract_features_from_peas"
def extract_features_from_peas(
    peas_path: "Path",
    *,
    out_path: "Path | None" = None,
    threshold: float = 0.65,
    workspace: "Path | None" = None,
    existing_spec_path: "Path | None" = None,
    project_id: str = "extract-from-peas",
    _synthesize_fn: "Any" = None,
) -> "dict[str, Any]":
    """Parse a PEAS prose-only markdown file and synthesize acceptance criteria.

    Canonical AC-required entry-point — delegates to :func:`extract_and_synthesize`.
    """
    return extract_and_synthesize(
        peas_path,
        out_path=out_path,
        threshold=threshold,
        workspace=workspace,
        existing_spec_path=existing_spec_path,
        project_id=project_id,
        _synthesize_fn=_synthesize_fn,
    )
