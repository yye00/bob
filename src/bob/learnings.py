"""Per-skill append-only learning ledger."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SKILLS_DIR = Path(__file__).parent / "skills"

_DEFAULT_PROMOTE_ON_N = 3


def get_promote_on_n() -> int:
    """Return the number of evidence observations required to promote a lesson.

    Reads BOB_PROMOTE_ON_N env var; defaults to 3 when unset. Raises
    ValueError for non-integer values so misconfiguration surfaces loudly.
    """
    raw = os.environ.get("BOB_PROMOTE_ON_N")
    if raw is None:
        return _DEFAULT_PROMOTE_ON_N
    try:
        return int(raw)
    except ValueError:
        raise ValueError(
            f"BOB_PROMOTE_ON_N={raw!r} is not a valid integer. "
            f"Must be a non-negative integer."
        )

_ENTRY_SEPARATOR = "\n---\n"
_ENTRY_START = "## Learning Entry"


def append_learning(
    skill: str,
    lesson: str,
    evidence: dict,
    source_feature_id: str | None,
) -> None:
    """Append a timestamped learning entry to the skill's LEARNINGS.md ledger."""
    skill_dir = SKILLS_DIR / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = skill_dir / "LEARNINGS.md"

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    feat_line = source_feature_id if source_feature_id is not None else "None"
    evidence_json = json.dumps(evidence, ensure_ascii=False)

    entry = (
        f"{_ENTRY_START}\n"
        f"- **timestamp**: {timestamp}\n"
        f"- **source_feature_id**: {feat_line}\n"
        f"- **lesson**: {lesson}\n"
        f"- **evidence**: {evidence_json}\n"
    )

    if ledger_path.exists() and ledger_path.stat().st_size > 0:
        with ledger_path.open("a", encoding="utf-8") as f:
            f.write(_ENTRY_SEPARATOR)
            f.write(entry)
    else:
        ledger_path.write_text(entry, encoding="utf-8")


def read_learnings(skill: str) -> list[dict]:
    """Return all learning entries for a skill as a list of dicts."""
    ledger_path = SKILLS_DIR / skill / "LEARNINGS.md"
    if not ledger_path.exists():
        return []

    content = ledger_path.read_text(encoding="utf-8")
    raw_entries = [block.strip() for block in content.split(_ENTRY_SEPARATOR.strip())]

    results = []
    for block in raw_entries:
        if not block.startswith(_ENTRY_START):
            continue
        entry = _parse_entry(block)
        if entry is not None:
            results.append(entry)
    return results


def _parse_entry(block: str) -> dict | None:
    """Parse a single markdown entry block into a dict."""
    lines = block.splitlines()
    fields: dict = {}
    for line in lines:
        if line.startswith("- **timestamp**:"):
            fields["timestamp"] = line[len("- **timestamp**:"):].strip()
        elif line.startswith("- **source_feature_id**:"):
            raw = line[len("- **source_feature_id**:"):].strip()
            fields["source_feature_id"] = None if raw == "None" else raw
        elif line.startswith("- **lesson**:"):
            fields["lesson"] = line[len("- **lesson**:"):].strip()
        elif line.startswith("- **evidence**:"):
            raw = line[len("- **evidence**:"):].strip()
            try:
                fields["evidence"] = json.loads(raw)
            except json.JSONDecodeError:
                fields["evidence"] = {}

    required = {"timestamp", "lesson", "evidence", "source_feature_id"}
    if not required.issubset(fields):
        return None
    return fields
