"""Numerical correctness verifier for scientific-compute acceptance criteria.

Provides two criterion types:
- ``mms: order=N norm=L2`` — manufactured-solution convergence: fits a log-log
  slope of error vs mesh-spacing and asserts slope >= N - tolerance.
- ``conserves: quantity=mass drift<=1e-9`` — runs the implementation forward
  and asserts the named conserved quantity drifts no more than the bound.
"""

from __future__ import annotations

import importlib
import math
import re
from typing import Any, Callable, Sequence


# ---------------------------------------------------------------------------
# MMS (Manufactured-solution convergence) verifier
# ---------------------------------------------------------------------------

def _fit_loglog_slope(h_values: Sequence[float], e_values: Sequence[float]) -> float:
    """Fit log-log slope of error vs mesh spacing via least-squares.

    Args:
        h_values: Mesh spacings (positive floats).
        e_values: Error norms corresponding to each spacing.

    Returns:
        The fitted convergence order (slope of log e vs log h).

    Raises:
        ValueError: If fewer than 2 valid data points are provided.
    """
    points = [
        (math.log(h), math.log(e))
        for h, e in zip(h_values, e_values)
        if h > 0 and e > 0
    ]
    if len(points) < 2:
        raise ValueError(
            f"Need at least 2 valid (h, e) pairs for slope fit, got {len(points)}"
        )

    n = len(points)
    sum_x = sum(x for x, _ in points)
    sum_y = sum(y for _, y in points)
    sum_xx = sum(x * x for x, _ in points)
    sum_xy = sum(x * y for x, y in points)

    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-15:
        raise ValueError("Degenerate mesh spacing values — cannot fit slope")

    return (n * sum_xy - sum_x * sum_y) / denom


def _compute_l2_error(
    exact_fn: Callable[[float], float],
    approx_values: Sequence[float],
    grid_points: Sequence[float],
) -> float:
    """Compute discrete L2 norm of error between exact and approximate values."""
    if len(approx_values) != len(grid_points):
        raise ValueError("approx_values and grid_points must have the same length")
    n = len(grid_points)
    if n == 0:
        raise ValueError("Empty grid")
    sq_sum = sum((exact_fn(x) - v) ** 2 for x, v in zip(grid_points, approx_values))
    return math.sqrt(sq_sum / n)


def verify_mms(
    *,
    solver: Callable[..., tuple[Sequence[float], Sequence[float]]],
    exact_fn: Callable[[float], float],
    mesh_spacings: Sequence[float],
    expected_order: float,
    norm: str = "L2",
    tolerance: float = 0.1,
    solver_kwargs: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Verify manufactured-solution convergence order.

    Calls *solver* for each mesh spacing in *mesh_spacings*, computes the
    error norm against *exact_fn*, fits the log-log slope, and asserts that
    the observed slope >= *expected_order* - *tolerance*.

    Args:
        solver:          Callable ``solver(h, **solver_kwargs)`` returning
                         ``(grid_points, approx_values)`` — two equal-length
                         sequences of floats.
        exact_fn:        The manufactured-solution exact function ``f(x) -> float``.
        mesh_spacings:   Decreasing sequence of mesh spacings to test (e.g.
                         ``[1/8, 1/16, 1/32]``).
        expected_order:  Required convergence order N (e.g. 2 for second-order).
        norm:            Error norm to use.  Currently only ``"L2"`` is supported.
        tolerance:       Allowed deficit below *expected_order* (default 0.1).
        solver_kwargs:   Extra keyword arguments forwarded to *solver*.

    Returns:
        ``(True, details)`` when the observed order satisfies the assertion,
        ``(False, reason)`` otherwise.
    """
    if norm.upper() != "L2":
        return False, f"mms: unsupported norm {norm!r}; only 'L2' is implemented"

    if len(mesh_spacings) < 2:
        return False, "mms: need at least 2 mesh spacings to fit convergence slope"

    kw = solver_kwargs or {}
    errors: list[float] = []
    hs: list[float] = []

    for h in mesh_spacings:
        try:
            grid_points, approx_values = solver(h, **kw)
        except Exception as exc:
            return False, f"mms: solver raised at h={h}: {exc}"
        try:
            err = _compute_l2_error(exact_fn, approx_values, grid_points)
        except Exception as exc:
            return False, f"mms: error computation failed at h={h}: {exc}"
        if err == 0.0:
            # Exact solution — count as machine precision, still valid.
            err = 1e-15
        errors.append(err)
        hs.append(float(h))

    try:
        observed_order = _fit_loglog_slope(hs, errors)
    except ValueError as exc:
        return False, f"mms: slope fitting failed: {exc}"

    threshold = expected_order - tolerance
    if observed_order >= threshold:
        return True, (
            f"mms: observed order {observed_order:.3f} >= required "
            f"{threshold:.3f} (expected={expected_order}, tol={tolerance})"
        )
    return False, (
        f"mms: observed order {observed_order:.3f} < required "
        f"{threshold:.3f} (expected={expected_order}, tol={tolerance}); "
        f"errors={[f'{e:.2e}' for e in errors]}"
    )


# ---------------------------------------------------------------------------
# Conservation verifier
# ---------------------------------------------------------------------------

def verify_conservation(
    *,
    stepper: Callable[..., Any],
    quantity_fn: Callable[[Any], float],
    initial_state: Any,
    n_steps: int,
    drift_bound: float,
    stepper_kwargs: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Verify that a conserved quantity drifts within the specified bound.

    Steps *stepper* forward *n_steps* times starting from *initial_state*,
    evaluates *quantity_fn* at each step, and checks that the absolute drift
    from the initial value never exceeds *drift_bound*.

    Args:
        stepper:         Callable ``stepper(state, **stepper_kwargs) -> new_state``.
        quantity_fn:     Callable ``quantity_fn(state) -> float`` — evaluates the
                         conserved quantity.
        initial_state:   Starting state passed to *stepper* and *quantity_fn*.
        n_steps:         Number of time steps to advance.
        drift_bound:     Maximum allowed |Q(t) - Q(0)| (absolute, not relative).
        stepper_kwargs:  Extra keyword arguments forwarded to *stepper*.

    Returns:
        ``(True, details)`` when max drift <= *drift_bound*,
        ``(False, reason)`` otherwise.
    """
    if n_steps < 1:
        return False, "conserves: n_steps must be >= 1"

    kw = stepper_kwargs or {}

    try:
        q0 = quantity_fn(initial_state)
    except Exception as exc:
        return False, f"conserves: quantity_fn raised on initial state: {exc}"

    state = initial_state
    max_drift = 0.0
    worst_step = 0

    for step in range(1, n_steps + 1):
        try:
            state = stepper(state, **kw)
        except Exception as exc:
            return False, f"conserves: stepper raised at step {step}: {exc}"
        try:
            q = quantity_fn(state)
        except Exception as exc:
            return False, f"conserves: quantity_fn raised at step {step}: {exc}"

        drift = abs(q - q0)
        if drift > max_drift:
            max_drift = drift
            worst_step = step

    if max_drift <= drift_bound:
        return True, (
            f"conserves: max drift {max_drift:.3e} <= bound {drift_bound:.3e} "
            f"over {n_steps} steps"
        )
    return False, (
        f"conserves: max drift {max_drift:.3e} > bound {drift_bound:.3e} "
        f"(worst at step {worst_step}/{n_steps}, q0={q0:.6e})"
    )


# ---------------------------------------------------------------------------
# Criterion expression parsers (for enhanced_verification integration)
# ---------------------------------------------------------------------------

def parse_mms_criterion(expression: str) -> dict[str, Any]:
    """Parse keyword arguments from an ``mms:`` criterion expression.

    Recognises:
        order=<float>
        norm=<word>          (default: L2)
        tolerance=<float>    (default: 0.1)
        module=<dotted.path> (dotted import path of the solver module)
        solver=<name>        (attribute name in the module)
        exact=<name>         (attribute name for the exact function)
        spacings=<csv>       (comma-separated mesh spacings)

    Returns a dict with the recognised keys (string values for module/solver/exact,
    float for order/tolerance, str for norm, list[float] for spacings).
    """
    result: dict[str, Any] = {}

    m = re.search(r"order\s*=\s*([\d.]+)", expression)
    if m:
        result["order"] = float(m.group(1))

    m = re.search(r"norm\s*=\s*(\w+)", expression)
    if m:
        result["norm"] = m.group(1).upper()

    m = re.search(r"tolerance\s*=\s*([\d.eE+-]+)", expression)
    if m:
        result["tolerance"] = float(m.group(1))

    m = re.search(r'module\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["module"] = m.group(1)

    m = re.search(r'solver\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["solver"] = m.group(1)

    m = re.search(r'exact\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["exact"] = m.group(1)

    m = re.search(r'spacings\s*=\s*"?([^"]+)"?', expression)
    if m:
        raw = m.group(1).strip()
        try:
            result["spacings"] = [float(s.strip()) for s in raw.split(",") if s.strip()]
        except ValueError:
            pass

    return result


def parse_conserves_criterion(expression: str) -> dict[str, Any]:
    """Parse keyword arguments from a ``conserves:`` criterion expression.

    Recognises:
        quantity=<word>       (name of the conserved quantity — informational)
        drift<=<float>        (maximum allowed absolute drift)
        drift=<float>         (alias for drift<= )
        module=<dotted.path>
        stepper=<name>
        quantity_fn=<name>
        n_steps=<int>
        initial=<name>        (attribute in module used as initial state)
    """
    result: dict[str, Any] = {}

    m = re.search(r"quantity\s*=\s*(\w+)", expression)
    if m:
        result["quantity"] = m.group(1)

    m = re.search(r"drift\s*<=?\s*([\d.eE+-]+)", expression)
    if m:
        result["drift_bound"] = float(m.group(1))

    m = re.search(r'module\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["module"] = m.group(1)

    m = re.search(r'stepper\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["stepper"] = m.group(1)

    m = re.search(r'quantity_fn\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["quantity_fn"] = m.group(1)

    m = re.search(r"n_steps\s*=\s*(\d+)", expression)
    if m:
        result["n_steps"] = int(m.group(1))

    m = re.search(r'initial\s*=\s*"?([^"\s,]+)"?', expression)
    if m:
        result["initial"] = m.group(1)

    return result


def check_mms_criterion(
    expression: str,
    workspace: "pathlib.Path | None" = None,  # noqa: F821
) -> tuple[bool, str]:
    """Evaluate an ``mms:`` criterion expression.

    When *module*, *solver*, and *exact* are given, imports them from the
    workspace and runs :func:`verify_mms`.  Returns ``(False, reason)`` for
    any missing or unparseable parameters.
    """
    args = parse_mms_criterion(expression)

    if "module" not in args or "solver" not in args or "exact" not in args:
        return False, (
            "mms: criterion requires module=, solver=, and exact= parameters"
        )
    if "order" not in args:
        return False, "mms: criterion requires order= parameter"
    if "spacings" not in args or len(args["spacings"]) < 2:
        return False, "mms: criterion requires spacings= with at least 2 values"

    try:
        mod = importlib.import_module(args["module"])
    except ImportError as exc:
        return False, f"mms: cannot import module {args['module']!r}: {exc}"

    solver_fn = getattr(mod, args["solver"], None)
    if solver_fn is None:
        return False, f"mms: module {args['module']!r} has no attribute {args['solver']!r}"

    exact_fn = getattr(mod, args["exact"], None)
    if exact_fn is None:
        return False, f"mms: module {args['module']!r} has no attribute {args['exact']!r}"

    return verify_mms(
        solver=solver_fn,
        exact_fn=exact_fn,
        mesh_spacings=args["spacings"],
        expected_order=args["order"],
        norm=args.get("norm", "L2"),
        tolerance=args.get("tolerance", 0.1),
    )


def check_conserves_criterion(
    expression: str,
    workspace: "pathlib.Path | None" = None,  # noqa: F821
) -> tuple[bool, str]:
    """Evaluate a ``conserves:`` criterion expression.

    When *module*, *stepper*, *quantity_fn*, and *initial* are given, imports
    them and runs :func:`verify_conservation`.
    """
    args = parse_conserves_criterion(expression)

    if "drift_bound" not in args:
        return False, "conserves: criterion requires drift<= parameter"

    if "module" not in args or "stepper" not in args or "quantity_fn" not in args:
        return False, (
            "conserves: criterion requires module=, stepper=, and quantity_fn= parameters"
        )

    if "initial" not in args:
        return False, "conserves: criterion requires initial= parameter"

    try:
        mod = importlib.import_module(args["module"])
    except ImportError as exc:
        return False, f"conserves: cannot import module {args['module']!r}: {exc}"

    stepper_fn = getattr(mod, args["stepper"], None)
    if stepper_fn is None:
        return False, f"conserves: module has no attribute {args['stepper']!r}"

    qty_fn = getattr(mod, args["quantity_fn"], None)
    if qty_fn is None:
        return False, f"conserves: module has no attribute {args['quantity_fn']!r}"

    initial_state = getattr(mod, args["initial"], None)
    if initial_state is None:
        return False, f"conserves: module has no attribute {args['initial']!r}"

    n_steps = args.get("n_steps", 100)

    return verify_conservation(
        stepper=stepper_fn,
        quantity_fn=qty_fn,
        initial_state=initial_state,
        n_steps=n_steps,
        drift_bound=args["drift_bound"],
    )
