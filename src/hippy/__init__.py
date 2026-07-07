"""hippy — spec self-consistency N-sample stability checking.

Public API::

    from hippy.spec_self_consistency import (
        compute_stability_score,
        run_self_consistency_check,
    )
"""

try:  # optional sibling feature — absent until its own build lands
    from hippy.spec_self_consistency import (  # noqa: F401
        compute_stability_score,
        run_self_consistency_check,
    )
except ModuleNotFoundError:
    pass

from hippy.orchestrator import (  # noqa: F401 — integration: hippy.orchestrator
    apply_bootstrap_bypass,
    gate_allows_execution,
)

from hippy.spec_synthesis import (  # noqa: F401 — integration: hippy.spec_synthesis
    _ensure_boundary_and_error_coverage,
    inject_boundary_and_error_acs,
)
