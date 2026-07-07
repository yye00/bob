"""Vendor/library capability probing for the spec extractor.

A feature whose prose says "X via vendor-lib Y" is BORN infeasible when Y does
not actually expose X. bob already has an environment-capability preflight for
*dependencies* (F-R7-473: "is the dependency importable"). This module extends
that principle to *capabilities*: "does the dependency actually expose the
specific symbol/capability this feature's prose claims."

Two public entry points:

* :func:`probe_vendor_capability` — parse a capability claim ("<op> via <lib>",
  "backed by <lib>", "passthrough to <lib.symbol>") and probe the real
  environment for that specific symbol/capability. Records concrete evidence
  (symbol found / absent / import error) rather than assuming.

* :func:`reclassify_infeasible_passthrough` — given a probe result, leave a
  feature untouched when the capability exists, but re-classify it as
  ``hand-built`` (cite-the-algorithm) when the vendor primitive is absent, so a
  passthrough that cannot exist is never promoted to ready.

Integrated into ``bob.spec_extractor``.
"""

from __future__ import annotations

import importlib
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "probe_vendor_capability",
    "reclassify_infeasible_passthrough",
    "parse_capability_claim",
    "verify_library_capability",
    "reclassify_absent_capability",
]

# "<op> via <lib>", "backed by <lib>", "passthrough to <lib.symbol>"
_CLAIM_PATTERNS = (
    re.compile(r"passthrough\s+to\s+([A-Za-z_][\w.]*)", re.IGNORECASE),
    re.compile(r"backed\s+by\s+([A-Za-z_][\w.]*)", re.IGNORECASE),
    re.compile(r"\bvia\s+([A-Za-z_][\w.]*)", re.IGNORECASE),
)


def parse_capability_claim(text: str) -> Optional[Dict[str, Optional[str]]]:
    """Parse a vendor-capability claim out of a description or AC string.

    Recognises the phrasings ``"<op> via <lib>"``, ``"backed by <lib>"`` and
    ``"passthrough to <lib.symbol>"``. The captured target may be a bare module
    (``hipfft``) or a dotted ``module.symbol`` (``hipfft.dct``); in the latter
    case the trailing component is treated as the required *symbol*.

    Args:
        text: Free-form description or acceptance-criterion string.

    Returns:
        A dict ``{"library": str, "symbol": str | None}`` when a claim is found,
        else ``None`` (no external provider named — pure-Python/algorithmic).

    Raises:
        ValueError: If *text* is not a string.
    """
    if not isinstance(text, str):
        raise ValueError(f"text must be a str, got {type(text).__name__!r}")

    for pattern in _CLAIM_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        target = match.group(1)
        if "." in target:
            library, symbol = target.rsplit(".", 1)
        else:
            library, symbol = target, None
        return {"library": library, "symbol": symbol}
    return None


def probe_vendor_capability(claim: Any) -> Dict[str, Any]:
    """Probe the real environment for a specific vendor capability.

    Accepts either a raw claim string (parsed via :func:`parse_capability_claim`)
    or a pre-parsed dict with a ``library`` key and optional ``symbol`` key. The
    named library is imported; when a ``symbol`` is required, its presence is
    checked via ``hasattr``. Concrete evidence is recorded so the claim is
    grounded rather than assumed.

    Args:
        claim: A claim string, or a dict ``{"library": str, "symbol": str|None}``.

    Returns:
        A dict with keys:
        - ``library``: the probed module name
        - ``symbol``: the required symbol (or None)
        - ``present``: bool — True only when the module imports *and* the symbol
          (if any) exists
        - ``method``: ``"attribute"`` | ``"import"``
        - ``evidence``: human-readable probe outcome
        When *claim* is a string that names no vendor provider, returns a result
        with ``library=None``, ``present=True`` and ``method="none"`` (nothing to
        probe — pure-Python features are unaffected).

    Raises:
        ValueError: If *claim* is not a str/dict, or a dict lacks a non-empty
            ``library``.
    """
    if isinstance(claim, str):
        parsed = parse_capability_claim(claim)
        if parsed is None:
            return {
                "library": None,
                "symbol": None,
                "present": True,
                "method": "none",
                "evidence": "no external vendor provider named in claim",
            }
    elif isinstance(claim, dict):
        library = claim.get("library")
        if not library or not isinstance(library, str):
            raise ValueError("claim dict must have a non-empty string 'library'")
        parsed = {"library": library, "symbol": claim.get("symbol")}
    else:
        raise ValueError(
            f"claim must be a str or dict, got {type(claim).__name__!r}"
        )

    library = parsed["library"]
    symbol = parsed["symbol"]

    try:
        module = importlib.import_module(library)
    except Exception as exc:  # ImportError and any import-time failure
        return {
            "library": library,
            "symbol": symbol,
            "present": False,
            "method": "import",
            "evidence": f"module {library!r} not importable: {exc}",
        }

    if symbol is None:
        return {
            "library": library,
            "symbol": None,
            "present": True,
            "method": "import",
            "evidence": f"module {library!r} imported successfully",
        }

    if hasattr(module, symbol):
        return {
            "library": library,
            "symbol": symbol,
            "present": True,
            "method": "attribute",
            "evidence": f"{library}.{symbol} found",
        }
    return {
        "library": library,
        "symbol": symbol,
        "present": False,
        "method": "attribute",
        "evidence": f"{library}.{symbol} ABSENT (module imported, symbol missing)",
    }


def reclassify_infeasible_passthrough(
    feature: Dict[str, Any],
    probe_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Re-classify a feature when its claimed vendor primitive is absent.

    When *probe_result* shows the capability is present, the feature is returned
    with a ``ready`` classification and the probe evidence attached — the vendor
    passthrough is grounded. When the capability is ABSENT, the feature is
    re-classified as ``hand-built``: a note is appended instructing the builder
    to implement the algorithm from scratch (cite it) rather than emit a
    passthrough that cannot exist. In both cases the probe evidence is recorded
    on the returned feature so the claim is grounded, not assumed.

    The input feature dict is not mutated; a shallow copy is returned.

    Args:
        feature: A feature dict (e.g. with ``id``/``name``/``description``).
        probe_result: A result dict from :func:`probe_vendor_capability`.

    Returns:
        A new feature dict with ``classification`` and ``capability_evidence``
        keys set (and, when re-classified, an appended note in
        ``capability_note``).

    Raises:
        ValueError: If *feature* is not a dict, or *probe_result* is not a dict
            or lacks a ``present`` key.
    """
    if not isinstance(feature, dict):
        raise ValueError(f"feature must be a dict, got {type(feature).__name__!r}")
    if not isinstance(probe_result, dict):
        raise ValueError(
            f"probe_result must be a dict, got {type(probe_result).__name__!r}"
        )
    if "present" not in probe_result:
        raise ValueError("probe_result must have a 'present' key")

    result = dict(feature)
    result["capability_evidence"] = probe_result.get("evidence", "")

    if probe_result["present"]:
        result["classification"] = "ready"
        return result

    library = probe_result.get("library")
    symbol = probe_result.get("symbol")
    target = f"{library}.{symbol}" if symbol else str(library)
    note = (
        f"hand-built (no vendor primitive): {target} is not available in the "
        f"real environment; implement the algorithm from scratch and cite it "
        f"rather than emitting a passthrough."
    )
    result["classification"] = "hand-built"
    result["capability_note"] = note
    logger.warning(
        "Re-classified feature %r as hand-built: %s",
        feature.get("id", feature.get("name", "<unknown>")),
        probe_result.get("evidence", ""),
    )
    return result


def verify_library_capability(claim: Any) -> Dict[str, Any]:
    """Verify that a specific vendor library capability exists (AC entry point).

    Thin alias for :func:`probe_vendor_capability`: parse a capability claim and
    probe the real environment for the specific symbol/capability the feature's
    prose asserts, recording concrete evidence.

    Args:
        claim: A claim string, or a dict ``{"library": str, "symbol": str|None}``.

    Returns:
        The probe-result dict from :func:`probe_vendor_capability`.

    Raises:
        ValueError: Propagated from :func:`probe_vendor_capability` on bad input.
    """
    return probe_vendor_capability(claim)


def reclassify_absent_capability(
    feature: Dict[str, Any],
    probe_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Re-classify a feature whose claimed vendor capability is absent (AC entry).

    Thin alias for :func:`reclassify_infeasible_passthrough`.

    Args:
        feature: A feature dict.
        probe_result: A result dict from :func:`verify_library_capability`.

    Returns:
        The re-classified feature dict.

    Raises:
        ValueError: Propagated from :func:`reclassify_infeasible_passthrough`.
    """
    return reclassify_infeasible_passthrough(feature, probe_result)
