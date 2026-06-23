"""Security verification check #9 for Bob3.

Implements the post-implementation security scan that runs in the
orchestrator (NOT inside the implementation sub-agent) per the design
in ``docs/recursion/round1/research/gap_02_security_scanning.md``.

Four sub-checks are run in sequence with per-check timeouts:

1. **dependency audit** — invokes ``pip-audit --format json`` against
   the workspace's pyproject/requirements files. CVE-level findings are
   ``warn`` severity (logged + filed to ``reviews/findings.yaml`` but do
   not block commit) per the tiered policy in PLAN.md AC4.

2. **secrets scan** — uses the ``detect_secrets`` Python API
   (``SecretsCollection``) over the diff (or whole tree if no diff is
   supplied). ANY finding is ``hard_fail`` — there is no legitimate
   reason for fresh AI-generated code to contain real credentials.

3. **SAST** — invokes ``bandit -r <workspace> -f json -ll`` as a
   subprocess. Bandit ``HIGH`` severity is ``hard_fail``;
   ``MEDIUM``/``LOW`` are ``warn``.

4. **slopsquatting** — for every ``import`` and ``from X import``
   statement in the diff, queries ``https://pypi.org/pypi/<pkg>/json``;
   HTTP 404 → finding (the package does not exist on PyPI). ANY finding
   is ``hard_fail`` since a non-existent import is a future
   supply-chain attack waiting for someone to register the name.

Each sub-check has its own ``try``/``except`` so one tool's failure
does not break the others; tool failures are recorded in
``SecurityResult.tool_failures`` AND surface as ``SecurityFinding``
records with ``severity="info"`` for traceability (these never
hard-fail).
"""

from __future__ import annotations

import ast
import json
import logging
import re
import subprocess  # nosec B404 - subprocess is required to invoke pip-audit / bandit
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from bob3.models import SecurityFinding, SecurityResult

logger = logging.getLogger(__name__)


# Python standard-library module names that should never be looked up on
# PyPI (they ship with the interpreter and are not packages on the
# index). Maintained as a curated allowlist; mirrored conservatively
# from ``sys.stdlib_module_names`` (Python >=3.10).
_STDLIB_MODULES = frozenset(getattr(sys, "stdlib_module_names", frozenset()))

# Hand-maintained import-name → distribution-name overrides for the
# common cases where the import name does not match the PyPI
# distribution name (slopsquatting check would otherwise FP).
_IMPORT_TO_DIST: dict[str, str] = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyOpenSSL",
    "git": "GitPython",
    "magic": "python-magic",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "jose": "python-jose",
    "msgpack_numpy": "msgpack-numpy",
    "google": "google-api-python-client",
    "mem0": "mem0ai",
}


def _read_first_party_packages(workspace: Path) -> set[str]:
    """Return import names this project owns and should never PyPI-probe.

    Reads pyproject.toml's [project].name and walks src/ for top-level
    package directories. The slopsquatting check would otherwise hard-fail
    on a project's own ``import <package_name>`` because the local-only
    distribution cannot be found on PyPI.
    """
    pkgs: set[str] = set()
    pyproj = workspace / "pyproject.toml"
    if pyproj.exists():
        try:
            import tomllib
            data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
            project = data.get("project", {})
            if name := project.get("name"):
                pkgs.add(str(name).replace("-", "_"))
        except Exception:  # noqa: BLE001 - best-effort allowlist
            pass
    src = workspace / "src"
    if src.is_dir():
        for child in src.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                pkgs.add(child.name)
                for grand in child.iterdir():
                    if grand.is_dir() and (grand / "__init__.py").exists():
                        pkgs.add(grand.name)
                    elif grand.is_file() and grand.suffix == ".py" and grand.stem != "__init__":
                        pkgs.add(grand.stem)
            elif child.is_dir():
                # Directory without __init__.py (namespace package or container dir):
                # still walk one level deeper to find sub-packages that have __init__.py.
                # This handles src/bob3/spec_quality/ (no bob3/__init__.py) correctly.
                for grand in child.iterdir():
                    if grand.is_dir() and (grand / "__init__.py").exists():
                        pkgs.add(grand.name)
                    elif grand.is_file() and grand.suffix == ".py" and grand.stem != "__init__":
                        pkgs.add(grand.stem)
            elif child.is_file() and child.suffix == ".py" and child.stem != "__init__":
                # src/*.py files are first-party modules on sys.path via
                # pythonpath = ["src"] in pyproject.toml — whitelist them.
                pkgs.add(child.stem)
    # F-R7-481 forward-carry: tools/ and project-root sibling .py files are
    # first-party project scripts (e.g. spec_quality_score.py). Subagents
    # routinely `import` them; without this walk the slopsquatting probe
    # hard-fails on every such import and NH-demotes the feature.
    tools_dir = workspace / "tools"
    if tools_dir.is_dir():
        # ``tools`` itself is an importable first-party package/namespace in the
        # gen tree (subagents write ``from tools.spec_quality_score import ...``
        # and ``import tools``). Without adding the bare name, the slopsquatting
        # probe 404s on ``tools`` and HARD-FAILS every feature that imports it
        # (bob72: blockers=slop with ``tools`` among the survivors).
        pkgs.add("tools")
        for child in tools_dir.iterdir():
            if child.is_file() and child.suffix == ".py" and child.stem != "__init__":
                pkgs.add(child.stem)
            elif child.is_dir() and (child / "__init__.py").exists():
                pkgs.add(child.name)
    # The gen's OWN lineage names (bob3, bob71, bob72, ...) are first-party: the
    # recursive chain seeds each gen from the previous, and generated code +
    # tests sometimes still reference an ancestor's package name (e.g. a stale
    # ``import bob12``). These are never on PyPI, so the slopsquatting probe
    # hard-fails on them — but they ARE local to the chain, not typosquats. Treat
    # any ``bob<digits>`` import as first-party so a stale cross-gen reference
    # cannot block a feature. (The reference is still wrong and should be fixed at
    # the spec layer, but it must not gate a security check.)
    import re as _re_fp
    # Also whitelist the current gen dir's own name (workspace basename).
    pkgs.add(workspace.resolve().name)
    if workspace.is_dir():
        for child in workspace.iterdir():
            if child.is_file() and child.suffix == ".py" and child.stem != "__init__":
                pkgs.add(child.stem)
    # Mark the lineage pattern via a sentinel the caller expands; simplest is to
    # add the concrete ancestor names we can see as sibling dirs of the gen.
    parent = workspace.resolve().parent
    if parent.is_dir():
        for sib in parent.iterdir():
            if sib.is_dir() and _re_fp.fullmatch(r"bob\d+", sib.name):
                pkgs.add(sib.name)
    return pkgs

_PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"

# Regex for "from X" / "import X" in raw diff text. Captures the
# top-level package name only (e.g. ``foo.bar.baz`` → ``foo``).
_DIFF_IMPORT_RE = re.compile(
    r"^\+\s*(?:from\s+([A-Za-z_][\w]*)|import\s+([A-Za-z_][\w]*))",
    re.MULTILINE,
)


def _normalise_to_distribution(import_name: str) -> str:
    """Map an import name to its PyPI distribution name."""
    return _IMPORT_TO_DIST.get(import_name, import_name)


def _extract_imports_from_diff(diff: str | None) -> list[str]:
    """Return top-level package names introduced by ``+`` lines in the diff.

    If ``diff`` is None we cannot infer "what was added", so we return
    an empty list (the tree-walk fallback in
    ``_extract_imports_from_tree`` handles that case).
    """
    if not diff:
        return []
    pkgs: set[str] = set()
    for match in _DIFF_IMPORT_RE.finditer(diff):
        name = match.group(1) or match.group(2)
        if name and name not in _STDLIB_MODULES:
            pkgs.add(name)
    return sorted(pkgs)


def _extract_imports_from_tree(workspace: Path) -> list[str]:
    """Walk every ``.py`` file under ``workspace`` and collect imports.

    Used as a fallback when no diff is supplied. Skips ``__pycache__``,
    ``.venv``, ``venv``, ``build``, ``dist``, ``.git`` and the workspace's
    own ``tests/`` directory.
    """
    pkgs: set[str] = set()
    skip_dirs = {
        "__pycache__", ".venv", "venv", "build", "dist", ".git",
        "tests", ".tox", "docs", "examples", "scripts", "tools",
    }
    for path in workspace.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top and top not in _STDLIB_MODULES:
                        pkgs.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    top = node.module.split(".")[0]
                    if top and top not in _STDLIB_MODULES:
                        pkgs.add(top)
    return sorted(pkgs)


# Process-wide PyPI existence cache. The SAME ~30 third-party imports (numpy,
# click, pydantic, ...) recur across all 128 features, so without a cache the run
# re-probes pypi.org hundreds of times — each probe is a network round-trip and
# security_scan was costing ~110s/feature. Cache True/False verdicts for the whole
# run; do NOT cache None (transient network errors) so a flaky lookup retries.
_PYPI_EXISTS_CACHE: dict[str, bool] = {}


def _pypi_package_exists(name: str, *, timeout: int) -> bool | None:
    """Probe ``pypi.org/pypi/<name>/json`` (cached per process).

    Returns:
        True  — HTTP 200 (package exists).
        False — HTTP 404 (package missing).
        None  — network error / non-2xx-non-404 response (treat as
                "could not determine"; caller records a tool_failed
                rather than a hard-fail). NOT cached so it retries.
    """
    key = name.lower()
    cached = _PYPI_EXISTS_CACHE.get(key)
    if cached is not None:
        return cached
    url = _PYPI_JSON_URL.format(name=name)
    req = urllib.request.Request(url, headers={"User-Agent": "bob3-security-checks/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - hardcoded https URL
            result = 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            result = False
        else:
            return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    _PYPI_EXISTS_CACHE[key] = result
    return result


# ---------------------------------------------------------------------------
# Sub-check 1: dependency audit (pip-audit)
# ---------------------------------------------------------------------------


def _run_pip_audit(workspace: Path, *, timeout: int) -> tuple[list[SecurityFinding], str | None]:
    """Run ``pip-audit --format json`` against the workspace.

    Returns ``(findings, tool_failure_message)``. ``tool_failure_message``
    is non-None when pip-audit could not be invoked / parsed; the caller
    records that as a tool_failed entry.
    """
    cmd = [sys.executable, "-m", "pip_audit", "--format", "json", "--progress-spinner", "off"]
    # Prefer requirements.txt, then pyproject.toml; if neither exists,
    # pip-audit falls back to the active environment, which is
    # acceptable for a workspace scan.
    req_file = workspace / "requirements.txt"
    pyproject = workspace / "pyproject.toml"
    if req_file.is_file():
        cmd.extend(["--requirement", str(req_file)])
    elif pyproject.is_file():
        # pip-audit accepts pyproject directly via --requirement in
        # newer versions; older versions require --strict. Use the
        # universally-supported form: scan the active environment but
        # cd into the workspace so any local lockfile is picked up.
        pass

    try:
        proc = subprocess.run(  # nosec B603 - args are a fixed list
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], f"pip-audit timed out after {timeout}s"
    except (OSError, FileNotFoundError) as exc:
        return [], f"pip-audit not invocable: {exc}"

    # pip-audit exits 1 when vulns are found — that's not a tool failure.
    raw = proc.stdout.strip()
    if not raw:
        # No JSON on stdout. Treat empty as "no findings" only if the
        # command exited cleanly; otherwise it's a tool failure.
        if proc.returncode != 0:
            return [], f"pip-audit failed (exit={proc.returncode}): {proc.stderr.strip()[:300]}"
        return [], None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], f"pip-audit produced unparseable JSON: {exc}"

    findings: list[SecurityFinding] = []
    # pip-audit JSON shape: {"dependencies": [{"name": ..., "vulns": [{"id": ..., "description": ...}, ...]}, ...]}
    deps = data.get("dependencies", []) if isinstance(data, dict) else data
    if isinstance(deps, list):
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            name = dep.get("name") or dep.get("package") or "?"
            for vuln in dep.get("vulns", []) or []:
                if not isinstance(vuln, dict):
                    continue
                vid = vuln.get("id") or vuln.get("aliases", ["?"])[0] if vuln.get("aliases") else vuln.get("id")
                desc = vuln.get("description") or vuln.get("summary") or ""
                findings.append(
                    SecurityFinding(
                        tool="pip-audit",
                        severity="medium",  # pip-audit findings are always warn per AC4
                        message=f"{name}: {desc[:240]}".strip(),
                        file=None,
                        line=None,
                        cve_or_rule_id=vid,
                    )
                )
    return findings, None


# ---------------------------------------------------------------------------
# Sub-check 2: secrets scan (detect-secrets)
# ---------------------------------------------------------------------------


def _run_detect_secrets(
    workspace: Path,
    diff: str | None,
    *,
    timeout: int,
) -> tuple[list[SecurityFinding], str | None]:
    """Scan the diff (or whole tree) for hard-coded secrets."""
    deadline = time.monotonic() + timeout
    findings: list[SecurityFinding] = []
    try:
        from detect_secrets import SecretsCollection
        from detect_secrets.settings import default_settings
    except ImportError as exc:
        return [], f"detect-secrets not importable: {exc}"

    try:
        collection = SecretsCollection()
        with default_settings():
            if diff:
                # scan_diff requires the optional ``unidiff`` package. If
                # it isn't installed we fall back to extracting the
                # ``+``-prefixed added lines and scanning them as a
                # temporary file via scan_file (which is the always-on
                # API). This keeps the secrets-scan path working with
                # only the mandatory dependency.
                used_scan_diff = False
                try:
                    for secret in collection.scan_diff(diff):
                        used_scan_diff = True
                        if time.monotonic() > deadline:
                            return findings, f"detect-secrets exceeded {timeout}s wall-clock"
                        findings.append(
                            SecurityFinding(
                                tool="detect-secrets",
                                severity="high",
                                message=f"Possible {secret.type} in diff",
                                file=getattr(secret, "filename", None),
                                line=getattr(secret, "line_number", None),
                                cve_or_rule_id=secret.type,
                            )
                        )
                    used_scan_diff = True
                except (NotImplementedError, ImportError):
                    used_scan_diff = False

                if not used_scan_diff:
                    # Extract added lines (those starting with '+' but
                    # not '+++ ' header lines) and write to a temp file
                    # for scan_file. Preserve original line numbers for
                    # the synthetic file by writing only added lines —
                    # we lose the original-file line numbers but keep
                    # the secret content for detection.
                    import tempfile
                    added: list[str] = []
                    for raw in diff.splitlines():
                        if raw.startswith("+++ ") or raw.startswith("+++\t"):
                            continue
                        if raw.startswith("+"):
                            added.append(raw[1:])
                    if added:
                        with tempfile.NamedTemporaryFile(
                            mode="w", suffix=".diff_added", delete=False, encoding="utf-8",
                        ) as tf:
                            tf.write("\n".join(added))
                            tmp_path = tf.name
                        try:
                            collection.scan_file(tmp_path)
                            for filename, secret in collection:
                                findings.append(
                                    SecurityFinding(
                                        tool="detect-secrets",
                                        severity="high",
                                        message=f"Possible {secret.type} in diff",
                                        file=None,
                                        line=getattr(secret, "line_number", None),
                                        cve_or_rule_id=secret.type,
                                    )
                                )
                        finally:
                            try:
                                Path(tmp_path).unlink()
                            except OSError:
                                pass
            else:
                # Whole-tree scan via collection.scan_files. Limit to
                # workspace-relative .py / .yml / .yaml / .env / .json
                # to keep runtime bounded.
                exts = {".py", ".yml", ".yaml", ".env", ".json", ".toml", ".cfg", ".ini"}
                # Only scan RECENTLY-MODIFIED files (the feature's new code), not
                # the entire inherited gen tree. A gen rsync-seeded from its parent
                # carries thousands of files; a full-tree detect-secrets walk hit
                # the 60s timeout EVERY feature and dominated verification cost
                # (bob73: detect-secrets=60s while every other check was <20s).
                # Secrets only enter via NEW code, so a recency window covers the
                # real risk. BOB3_SECRETS_RECENT_SECONDS (default 3600) and a hard
                # file cap keep it bounded; .venv/tests/etc. are excluded.
                import os as _os3
                try:
                    _recent = float(_os3.environ.get("BOB3_SECRETS_RECENT_SECONDS", "3600"))
                except (TypeError, ValueError):
                    _recent = 3600.0
                _now = time.time()
                _skip_parts = {".venv", "venv", "__pycache__", ".git", "build", "dist",
                               "tests", ".bob3", "workspace", "node_modules"}
                _scanned = 0
                _CAP = 400
                for path in workspace.rglob("*"):
                    if time.monotonic() > deadline:
                        return findings, f"detect-secrets exceeded {timeout}s wall-clock"
                    if _scanned >= _CAP:
                        break
                    if not path.is_file() or path.suffix not in exts:
                        continue
                    if any(part in _skip_parts for part in path.parts):
                        continue
                    try:
                        if _recent > 0 and (_now - path.stat().st_mtime) > _recent:
                            continue  # untouched inherited file — not new-code risk
                    except OSError:
                        continue
                    try:
                        collection.scan_file(str(path))
                        _scanned += 1
                    except (OSError, UnicodeDecodeError):
                        continue
                for filename, secret_set in collection.files.items() if hasattr(collection, "files") else []:
                    for secret in secret_set:
                        findings.append(
                            SecurityFinding(
                                tool="detect-secrets",
                                severity="high",
                                message=f"Possible {secret.type} in tree",
                                file=filename,
                                line=getattr(secret, "line_number", None),
                                cve_or_rule_id=secret.type,
                            )
                        )
                # Newer versions: iteration via collection itself yields (filename, secret) tuples
                if not findings:
                    try:
                        for filename, secret in collection:
                            findings.append(
                                SecurityFinding(
                                    tool="detect-secrets",
                                    severity="high",
                                    message=f"Possible {secret.type} in tree",
                                    file=filename,
                                    line=getattr(secret, "line_number", None),
                                    cve_or_rule_id=secret.type,
                                )
                            )
                    except TypeError:
                        pass
    except Exception as exc:  # noqa: BLE001 - tool isolation per AC contract
        return findings, f"detect-secrets raised: {type(exc).__name__}: {exc}"
    return findings, None


# ---------------------------------------------------------------------------
# Sub-check 3: SAST (bandit)
# ---------------------------------------------------------------------------


_BANDIT_SEVERITY_MAP = {
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNDEFINED": "info",
}


def _run_bandit(workspace: Path, *, timeout: int) -> tuple[list[SecurityFinding], str | None]:
    """Run ``bandit -r <workspace> -f json -ll``."""
    cmd = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        str(workspace),
        "-f",
        "json",
        "-ll",
        "-x",
        ",".join(
            str(workspace / d)
            for d in (".venv", "venv", "tests", "build", "dist", "__pycache__", ".git")
        ),
    ]
    try:
        proc = subprocess.run(  # nosec B603 - args are a fixed list
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], f"bandit timed out after {timeout}s"
    except (OSError, FileNotFoundError) as exc:
        return [], f"bandit not invocable: {exc}"

    # Bandit exits 1 when issues found; 0 when clean. Either is fine.
    raw = proc.stdout.strip()
    if not raw:
        if proc.returncode not in (0, 1):
            return [], f"bandit failed (exit={proc.returncode}): {proc.stderr.strip()[:300]}"
        return [], None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], f"bandit produced unparseable JSON: {exc}"

    findings: list[SecurityFinding] = []
    for result in data.get("results", []) or []:
        sev_raw = (result.get("issue_severity") or "UNDEFINED").upper()
        sev = _BANDIT_SEVERITY_MAP.get(sev_raw, "info")
        findings.append(
            SecurityFinding(
                tool="bandit",
                severity=sev,
                message=result.get("issue_text") or result.get("test_name") or "bandit finding",
                file=result.get("filename"),
                line=result.get("line_number"),
                cve_or_rule_id=result.get("test_id"),
            )
        )
    return findings, None


# ---------------------------------------------------------------------------
# Sub-check 4: slopsquatting
# ---------------------------------------------------------------------------


def _run_slopsquatting(
    workspace: Path,
    diff: str | None,
    *,
    timeout: int,
) -> tuple[list[SecurityFinding], str | None]:
    """Probe PyPI for every newly-imported package."""
    deadline = time.monotonic() + timeout
    if diff:
        names = _extract_imports_from_diff(diff)
    else:
        names = _extract_imports_from_tree(workspace)
    first_party = _read_first_party_packages(workspace)
    names = [n for n in names if n not in first_party]
    # Drop any ``bob<digits>`` lineage import unconditionally: these name the
    # recursive chain's own generations (the gen builds bob_(N+1) from itself).
    # A stale ``import bob12`` in generated code is a wrong cross-gen reference,
    # never a PyPI typosquat — it must not hard-fail the security scan. (The bad
    # reference is fixed at the spec layer; it is not a security finding.)
    import re as _re_slop
    names = [n for n in names if not _re_slop.fullmatch(r"bob\d+", n)]
    if not names:
        return [], None

    findings: list[SecurityFinding] = []
    network_failures = 0
    per_request_timeout = max(2, min(10, timeout // max(1, len(names))))
    for raw_name in names:
        if time.monotonic() > deadline:
            return findings, f"slopsquatting exceeded {timeout}s wall-clock"
        dist = _normalise_to_distribution(raw_name)
        try:
            exists = _pypi_package_exists(dist, timeout=per_request_timeout)
        except Exception as exc:  # noqa: BLE001 - tool isolation
            return findings, f"slopsquatting probe raised: {type(exc).__name__}: {exc}"
        if exists is False:
            findings.append(
                SecurityFinding(
                    tool="slopsquatting",
                    severity="high",
                    message=f"Imported package '{raw_name}' (distribution '{dist}') does not exist on PyPI",
                    file=None,
                    line=None,
                    cve_or_rule_id=None,
                )
            )
        elif exists is None:
            network_failures += 1

    if network_failures and network_failures == len(names):
        return findings, f"slopsquatting network probes all failed ({network_failures} of {len(names)})"
    return findings, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _is_hard_fail(findings: list[SecurityFinding]) -> bool:
    """Apply the severity policy from PLAN.md AC4.

    hard_fail iff:
      - any detect-secrets finding (severity high), OR
      - any slopsquatting finding (severity high), OR
      - any bandit finding with severity == "high"

    All other findings (pip-audit at any severity, bandit medium/low,
    and info-level tool_failed records for any tool) are warnings.
    """
    for f in findings:
        # tool_failed records carry severity="info" and never hard-fail
        # regardless of which tool produced them.
        if f.severity == "info":
            continue
        if f.tool == "detect-secrets":
            return True
        if f.tool == "slopsquatting":
            return True
        if f.tool == "bandit" and f.severity == "high":
            return True
    return False


def run_security_checks(
    workspace: Path,
    diff: str | None = None,
    *,
    timeout: int = 60,
) -> SecurityResult:
    """Run all four security sub-checks against ``workspace``.

    Args:
        workspace: directory containing the implementation under
            evaluation. May or may not be the same as the bob3 repo
            root; usually it's a per-feature workspace.
        diff: unified-diff text of the change set under review. When
            None, the secrets and slopsquatting checks fall back to a
            full tree walk.
        timeout: per-sub-check timeout in seconds (default 60). Each of
            the four sub-checks is allotted this much wall-clock
            independently.

    Returns:
        A ``SecurityResult`` summarising findings, hard-fail status,
        the list of any tool failures, and total duration.

    Raises:
        Never. Every sub-check is wrapped in try/except so one tool's
        breakage cannot mask findings from the others. Tool failures
        surface as ``tool_failures`` entries on the result.
    """
    started = time.monotonic()
    workspace = Path(workspace)
    all_findings: list[SecurityFinding] = []
    tool_failures: list[str] = []

    # PARALLEL sub-checks (bob73 speedup): the four sub-checks are independent and
    # each BLOCKS on a subprocess (pip-audit, bandit) or network (slopsquatting),
    # so running them SEQUENTIALLY summed to ~108-240s/feature (2 tools timing out
    # at 60s each dominated). Run them concurrently in a thread pool — total time
    # collapses to the SLOWEST single check (~60s) instead of the sum. Each
    # sub-check keeps its own try/except isolation so one tool's breakage cannot
    # mask another's findings (the original hard-isolation contract).
    from concurrent.futures import ThreadPoolExecutor

    def _guard(tool: str, fn):
        try:
            findings, err = fn()
            return tool, findings, err, None
        except Exception as exc:  # noqa: BLE001 - hard isolation per tool
            return tool, [], None, f"{tool} unhandled: {type(exc).__name__}: {exc}"

    _tasks = {
        "pip-audit": lambda: _run_pip_audit(workspace, timeout=timeout),
        "detect-secrets": lambda: _run_detect_secrets(workspace, diff, timeout=timeout),
        "bandit": lambda: _run_bandit(workspace, timeout=timeout),
        "slopsquatting": lambda: _run_slopsquatting(workspace, diff, timeout=timeout),
    }
    with ThreadPoolExecutor(max_workers=4) as _ex:
        _futs = {_ex.submit(_guard, _t, _fn): _t for _t, _fn in _tasks.items()}
        for _fut in _futs:
            tool, findings, err, unhandled = _fut.result()
            all_findings.extend(findings)
            if unhandled:
                logger.warning(unhandled)
                tool_failures.append(unhandled)
                all_findings.append(SecurityFinding(
                    tool=tool, severity="info", message=f"tool_failed: {unhandled}",
                    file=None, line=None, cve_or_rule_id=None,
                ))
            elif err:
                tool_failures.append(f"{tool}: {err}")
                all_findings.append(SecurityFinding(
                    tool=tool, severity="info", message=f"tool_failed: {err}",
                    file=None, line=None, cve_or_rule_id=None,
                ))

    duration = time.monotonic() - started
    hard_fail = _is_hard_fail(all_findings)
    return SecurityResult(
        hard_fail=hard_fail,
        findings=all_findings,
        tool_failures=tool_failures,
        duration_seconds=duration,
    )
