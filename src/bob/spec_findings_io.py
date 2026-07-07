"""bob.spec_findings_io — atomic writer + quarantining loader for findings YAML.

Feature a81db7cc-7e62-4135-8875-e4cfda7ddac2

A prior generation's bob process (pid 2551581) launched and exited within 5.6s
with ``yaml.scanner.ScannerError`` at ``reviews/spec_findings.yaml`` line 1239
column 9.  Line 1238 began with the truncated key ``me: perf-orphan-69`` instead
of a record header — evidence of a concurrent or interrupted partial overwrite.
Bob could not boot until the YAML was manually repaired; six watchdog relaunch
attempts all hit the same error and the chain stalled for hours.

This module is the canonical I/O surface every spec that persists YAML state
under ``reviews/`` MUST go through:

- ``atomic_write_findings(data, path)`` — write via tmp+fsync+rename so a
  mid-write SIGTERM/SIGKILL never leaves malformed YAML on the target path.
- ``load_findings_or_quarantine(path)`` — on any ``yaml.YAMLError`` at boot,
  quarantine the corrupt file to ``<path>.corrupt.<unix_ts>`` and return {}.
  Empty findings is recoverable; a boot-loop crash is not.

The heavy lifting is delegated to :mod:`bob.spec_findings`; this module is the
stable, AC-named entry point.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from bob.spec_findings import atomic_write, load_safe

__all__ = ["atomic_write_findings", "load_findings_or_quarantine"]


def atomic_write_findings(data: dict[str, Any], path: Path | str) -> None:
    """Write *data* to *path* as YAML using an atomic tmp+fsync+rename sequence.

    A mid-write crash leaves only ``<path>.tmp`` behind; the target path is
    either absent (first write) or still holds the previous valid version.
    Any failure of the final ``os.rename`` propagates so the caller learns the
    write did not land — it never silently corrupts the target.
    """
    atomic_write(data, path)


def load_findings_or_quarantine(path: Path | str) -> dict[str, Any]:
    """Load findings YAML; quarantine the file and return {} if it is corrupt.

    On any ``yaml.YAMLError`` (including ``yaml.scanner.ScannerError``), the
    corrupt file is renamed to ``<path>.corrupt.<unix_ts>`` and an empty dict is
    returned so boot proceeds instead of crash-looping.  A missing or empty file
    also returns {}.  YAML that parses to a non-dict (e.g. a list) returns {}.
    """
    return load_safe(path)
