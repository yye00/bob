"""Setuptools bridge for Bob's mixed source layout.

Bob has accumulated several historical generation and test-fixture packages
under ``src/``. Discovering that directory without an include policy makes a
wheel silently contain every one of them. The roots below are the transitive
first-party import closure of the ``bob`` runtime package plus the public
``tools`` entry points.

Two canonical resources still live at repository level. ``build_py`` copies
them into the installed ``bob`` package so wheel installs do not depend on a
source checkout. ``MANIFEST.in`` makes the same operation work from an sdist.
"""

from pathlib import Path

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py as _build_py


_RUNTIME_PACKAGE_ROOTS = (
    "ac_grammar",
    "bob",
    "bob72",
    "bob73",
    "bob74",
    "bob75",
    "bob_legacy",
    "bob_orchestrator",
    "claude",
    "ears",
    "f_r7_412",
    "foo",
    "hippy",
    "rca_layer",
    "regression_attribution",
    "spec_linter",
    "spec_quality",
    "spec_synthesis",
    "spec_synthesizer",
    "tests_pass",
)

_RUNTIME_MODULES = (
    "auto_repair",
    "ears_criteria",
    "environment_capability",
    "gpu_triton_kernel_synthesis",
    "pytest_plugins",
    "pytest_snapshot_config",
    "stuck_readiness_decomposition",
)


class _BuildPyWithCanonicalResources(_build_py):
    """Copy repository-owned runtime resources into ``bob`` in the wheel."""

    _RESOURCE_MAP = (
        (Path("schemas/spec.v1.json"), Path("bob/spec.v1.json")),
        (Path("config/spawn_retry.yaml"), Path("bob/spawn_retry.yaml")),
    )

    def run(self) -> None:
        super().run()
        build_root = Path(self.build_lib)
        for source, relative_destination in self._RESOURCE_MAP:
            destination = build_root / relative_destination
            self.mkpath(str(destination.parent))
            self.copy_file(str(source), str(destination))


_package_patterns = tuple(
    pattern
    for root in _RUNTIME_PACKAGE_ROOTS
    for pattern in (root, f"{root}.*")
)


setup(
    packages=[
        *find_packages(where="src", include=_package_patterns),
        "tools",
    ],
    package_dir={"": "src", "tools": "tools"},
    py_modules=list(_RUNTIME_MODULES),
    data_files=[(".claude/hooks", [".claude/hooks/context_budget.py"])],
    cmdclass={"build_py": _BuildPyWithCanonicalResources},
)
