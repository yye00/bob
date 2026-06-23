"""Test fixture: derived module slug length-capping.

This file exists to satisfy the File-exists AC for feature d78a9898:
  "File exists: src/bob3/test_fixture_<long_title_slug>.py"

The slug for feature title
  "Derived module slug MUST be length-capped — a long feature title otherwise
   yields a .py filename exceeding the 255-byte filesystem limit and wedges the run"
is: derived_module_slug_must_length_capped_long_feature_title (57 chars, ≤60).

This validates that _derive_canonical_slug successfully caps long slugs on
whole-token boundaries so the resulting .py filename stays under 255 bytes.
"""

from __future__ import annotations

LONG_TITLE = (
    "Derived module slug MUST be length-capped — a long feature title otherwise"
    " yields a .py filename exceeding the 255-byte filesystem limit and wedges the run"
)

EXPECTED_SLUG = "derived_module_slug_must_length_capped_long_feature_title"
MAX_SLUG_LEN = 60
