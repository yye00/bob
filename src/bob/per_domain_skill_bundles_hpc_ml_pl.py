"""Per-domain skill bundles for HPC, ML, PL, and scientific specializations.

Packages skills into domain bundles (hpc, ml, pl, general, cfd, geomech,
nr, plasma, particle) that are swapped in based on spec metadata fields
(domain: hpc|ml|pl|general|cfd|geomech|nr|plasma|particle).
Reduces irrelevant context injection and improves skill-activation precision.

The HPC bundle additionally integrates with
:mod:`bob.skill_bundles.hpc` which provides skill markdown files for
OpenMP, MPI, CUDA, ROCm/HIP, and SIMD patterns. Use
:func:`get_hpc_skill_content` to load those files when the HPC domain
is active.

Scientific domain bundles integrate with their respective skill_bundles
subpackages:
- :mod:`bob.skill_bundles.cfd`     - FVM/FEM, SIMPLE/PISO, turbulence, BCs
- :mod:`bob.skill_bundles.geomech` - poroelasticity, contact, fault slip, plasticity
- :mod:`bob.skill_bundles.nr`      - BSSN, gauge, initial data, GW extraction, AMR
- :mod:`bob.skill_bundles.plasma`  - PIC, Boris, gather/scatter, MHD, Vlasov-Poisson
- :mod:`bob.skill_bundles.particle`- Geant4 user actions, custom physics lists

Public API:
    DOMAIN_BUNDLES          - Mapping of domain -> list of skill names
    VALID_DOMAINS           - Set of recognized domain identifiers
    get_skills_for_domain(domain) -> list[str]
    select_domain_from_spec(spec) -> str
    get_bundle_for_spec(spec) -> list[str]
    filter_skills_by_domain(all_skills, domain) -> list[str]
    get_hpc_skill_content(spec) -> dict[str, str] | None
    get_cfd_skill_content(spec) -> dict[str, str] | None
    get_geomech_skill_content(spec) -> dict[str, str] | None
    get_nr_skill_content(spec) -> dict[str, str] | None
    get_plasma_skill_content(spec) -> dict[str, str] | None
    get_particle_skill_content(spec) -> dict[str, str] | None
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Domain skill bundle definitions
# ---------------------------------------------------------------------------

#: Skills always injected regardless of domain — foundational workflow skills.
BASE_SKILLS: list[str] = [
    "systematic-debugging",
    "test-driven-development",
    "no-stubs-no-mocks",
    "implementing-acceptance-criteria",
    "using-bob-memory",
    "brainstorming-approaches",
    "checking-review-registry",
    "researching-unknowns",
]

#: Domain-specific skills layered on top of BASE_SKILLS.
_DOMAIN_EXTRA_SKILLS: dict[str, list[str]] = {
    # High-Performance Computing: numerical methods, parallelism, memory layout
    "hpc": [
        "researching-unknowns",  # numerical methods need lookup
        "brainstorming-approaches",  # algorithm trade-offs matter in HPC
    ],
    # Machine Learning: model architecture, training loops, data pipelines
    "ml": [
        "brainstorming-approaches",  # architecture choices are critical
        "researching-unknowns",  # ML APIs evolve rapidly
    ],
    # Programming Languages / compilers / type systems
    "pl": [
        "systematic-debugging",  # type errors require careful root-cause analysis
        "brainstorming-approaches",  # language design involves major trade-offs
    ],
    # Computational Fluid Dynamics: FVM/FEM, pressure-velocity coupling, turbulence
    "cfd": [
        "researching-unknowns",    # numerical schemes need reference lookup
        "brainstorming-approaches",  # solver choice (SIMPLE vs PISO) matters
    ],
    # Geomechanics: poroelasticity, contact, fault slip, plasticity
    "geomech": [
        "researching-unknowns",    # constitutive models need domain knowledge
        "systematic-debugging",    # nonlinear convergence failures need root cause
    ],
    # Numerical Relativity: BSSN, gauge, GW extraction, AMR
    "nr": [
        "researching-unknowns",    # GR formalism requires precise references
        "brainstorming-approaches",  # gauge choice has major stability impact
    ],
    # Plasma Physics: PIC, MHD, Vlasov-Poisson
    "plasma": [
        "researching-unknowns",    # kinetic vs fluid model choice needs context
        "brainstorming-approaches",  # PIC vs MHD vs hybrid trade-offs
    ],
    # Particle Physics: Geant4 user actions, custom physics lists
    "particle": [
        "researching-unknowns",    # physics model selection needs reference
        "systematic-debugging",    # Geant4 process registration bugs are subtle
    ],
    # General-purpose: no domain specialization
    "general": [],
}

#: Full skill bundles per domain (base + domain extras, deduplicated).
DOMAIN_BUNDLES: dict[str, list[str]] = {}
for _domain, _extras in _DOMAIN_EXTRA_SKILLS.items():
    _seen: set[str] = set()
    _bundle: list[str] = []
    for _skill in BASE_SKILLS + _extras:
        if _skill not in _seen:
            _seen.add(_skill)
            _bundle.append(_skill)
    DOMAIN_BUNDLES[_domain] = _bundle

#: Set of all recognized domain identifiers.
VALID_DOMAINS: frozenset[str] = frozenset(DOMAIN_BUNDLES.keys())

#: Default domain when none is specified or recognized.
DEFAULT_DOMAIN: str = "general"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_skills_for_domain(domain: str) -> list[str]:
    """Return the ordered skill list for the given domain.

    Falls back to the ``general`` bundle for unrecognized domains so that
    unknown domain values never result in zero skills injected.

    Args:
        domain: One of "hpc", "ml", "pl", "general", or any string.

    Returns:
        List of skill names in activation priority order.
    """
    normalized = domain.strip().lower() if domain else DEFAULT_DOMAIN
    return list(DOMAIN_BUNDLES.get(normalized, DOMAIN_BUNDLES[DEFAULT_DOMAIN]))


def select_domain_from_spec(spec: dict[str, Any] | None) -> str:
    """Extract the domain identifier from a spec metadata dict.

    Reads ``spec["domain"]`` (top-level) or ``spec["metadata"]["domain"]``.
    Returns ``"general"`` when the key is absent or the value is unrecognized.

    Args:
        spec: Parsed spec dict (e.g. from a YAML feature spec) or None.

    Returns:
        One of the recognized domain strings: "hpc", "ml", "pl", "general".
    """
    if not spec:
        return DEFAULT_DOMAIN

    # Try top-level domain key first, then nested metadata.domain.
    raw: Any = spec.get("domain")
    if raw is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw = metadata.get("domain")

    if raw is None:
        return DEFAULT_DOMAIN

    normalized = str(raw).strip().lower()
    return normalized if normalized in VALID_DOMAINS else DEFAULT_DOMAIN


def get_bundle_for_spec(spec: dict[str, Any] | None) -> list[str]:
    """Return the full skill bundle appropriate for the given feature spec.

    Combines :func:`select_domain_from_spec` and :func:`get_skills_for_domain`
    into a single convenience call.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Ordered list of skill names for the detected domain.
    """
    domain = select_domain_from_spec(spec)
    return get_skills_for_domain(domain)


def filter_skills_by_domain(all_skills: list[str], domain: str) -> list[str]:
    """Filter a list of candidate skills down to those in the domain bundle.

    Returns only skills that appear in the bundle for ``domain``, preserving
    the order from ``all_skills`` (not the bundle order). Skills that are not
    in ``all_skills`` but are in the domain bundle are NOT added — this
    function only filters, never augments.

    Args:
        all_skills: Candidate skill names to filter.
        domain: Target domain identifier.

    Returns:
        Subset of ``all_skills`` that belong to the given domain's bundle.
    """
    bundle_set = set(get_skills_for_domain(domain))
    return [s for s in all_skills if s in bundle_set]


def get_hpc_skill_content(spec: dict[str, Any] | None) -> dict[str, str] | None:
    """Return HPC skill markdown content when the spec activates the HPC bundle.

    Loads the OpenMP, MPI, CUDA, ROCm, and SIMD skill files from
    :mod:`bob.skill_bundles.hpc` and returns them as a filename → text
    mapping.  Returns ``None`` when the spec does not activate the HPC domain
    so callers can gate injection cleanly.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Dict mapping skill filename to markdown text, or None if not HPC.
    """
    from bob.skill_bundles.hpc import is_hpc_spec, load_hpc_skills

    if not is_hpc_spec(spec):
        return None
    return load_hpc_skills()


def get_cfd_skill_content(spec: dict[str, Any] | None) -> dict[str, str] | None:
    """Return CFD skill markdown content when the spec activates the CFD bundle.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Dict mapping skill filename to markdown text, or None if not CFD.
    """
    from bob.skill_bundles.cfd import is_cfd_spec, load_cfd_skills

    if not is_cfd_spec(spec):
        return None
    return load_cfd_skills()


def get_geomech_skill_content(spec: dict[str, Any] | None) -> dict[str, str] | None:
    """Return geomechanics skill markdown content when the spec activates the geomech bundle.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Dict mapping skill filename to markdown text, or None if not geomech.
    """
    from bob.skill_bundles.geomech import is_geomech_spec, load_geomech_skills

    if not is_geomech_spec(spec):
        return None
    return load_geomech_skills()


def get_nr_skill_content(spec: dict[str, Any] | None) -> dict[str, str] | None:
    """Return numerical relativity skill markdown content when the spec activates the NR bundle.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Dict mapping skill filename to markdown text, or None if not NR.
    """
    from bob.skill_bundles.nr import is_nr_spec, load_nr_skills

    if not is_nr_spec(spec):
        return None
    return load_nr_skills()


def get_plasma_skill_content(spec: dict[str, Any] | None) -> dict[str, str] | None:
    """Return plasma physics skill markdown content when the spec activates the plasma bundle.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Dict mapping skill filename to markdown text, or None if not plasma.
    """
    from bob.skill_bundles.plasma import is_plasma_spec, load_plasma_skills

    if not is_plasma_spec(spec):
        return None
    return load_plasma_skills()


def get_particle_skill_content(spec: dict[str, Any] | None) -> dict[str, str] | None:
    """Return particle physics skill markdown content when the spec activates the particle bundle.

    Args:
        spec: Parsed spec dict or None.

    Returns:
        Dict mapping skill filename to markdown text, or None if not particle.
    """
    from bob.skill_bundles.particle import is_particle_spec, load_particle_skills

    if not is_particle_spec(spec):
        return None
    return load_particle_skills()
