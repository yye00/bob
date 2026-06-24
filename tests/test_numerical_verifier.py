"""Tests for bob.numerical_verifier."""

from __future__ import annotations

import math
import pytest

from bob.numerical_verifier import (
    _compute_l2_error,
    _fit_loglog_slope,
    parse_conserves_criterion,
    parse_mms_criterion,
    verify_conservation,
    verify_mms,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestFitLoglogSlope:
    def test_exact_first_order(self):
        # errors proportional to h^1 -> slope == 1
        hs = [0.5, 0.25, 0.125]
        es = [h ** 1.0 for h in hs]
        slope = _fit_loglog_slope(hs, es)
        assert abs(slope - 1.0) < 1e-10

    def test_exact_second_order(self):
        hs = [0.5, 0.25, 0.125, 0.0625]
        es = [h ** 2.0 for h in hs]
        slope = _fit_loglog_slope(hs, es)
        assert abs(slope - 2.0) < 1e-10

    def test_exact_fourth_order(self):
        hs = [1.0, 0.5, 0.25, 0.125]
        es = [h ** 4.0 for h in hs]
        slope = _fit_loglog_slope(hs, es)
        assert abs(slope - 4.0) < 1e-10

    def test_raises_with_one_point(self):
        with pytest.raises(ValueError, match="at least 2 valid"):
            _fit_loglog_slope([0.1], [0.01])

    def test_raises_with_zero_h(self):
        # zero h filtered, leaving only 1 valid point
        with pytest.raises(ValueError, match="at least 2 valid"):
            _fit_loglog_slope([0.0, 0.1], [0.0, 0.01])

    def test_raises_with_zero_error(self):
        # zero error filtered out -> fewer than 2 valid points
        with pytest.raises(ValueError, match="at least 2 valid"):
            _fit_loglog_slope([0.5, 0.25], [0.0, 0.0])


class TestComputeL2Error:
    def test_zero_error_on_exact(self):
        exact = math.sin
        xs = [0.0, 0.5, 1.0]
        approx = [math.sin(x) for x in xs]
        err = _compute_l2_error(exact, approx, xs)
        assert err == 0.0

    def test_nonzero_error(self):
        exact = lambda x: 1.0
        xs = [0.0, 0.5, 1.0]
        approx = [0.0, 0.0, 0.0]
        # L2 = sqrt(sum(1^2) / 3) = 1.0
        err = _compute_l2_error(exact, approx, xs)
        assert abs(err - 1.0) < 1e-12

    def test_raises_mismatched_lengths(self):
        with pytest.raises(ValueError, match="same length"):
            _compute_l2_error(lambda x: x, [1.0, 2.0], [0.0])

    def test_raises_empty_grid(self):
        with pytest.raises(ValueError, match="Empty grid"):
            _compute_l2_error(lambda x: x, [], [])


# ---------------------------------------------------------------------------
# verify_mms
# ---------------------------------------------------------------------------

def _make_second_order_solver():
    """Return a solver with exact second-order L2 convergence for sin(pi*x)."""
    def solver(h, **kw):
        n = max(2, round(1.0 / h))
        xs = [i / n for i in range(n + 1)]
        # Perturb with h^2 error so convergence order == 2
        approx = [math.sin(math.pi * x) + h ** 2 * 0.1 for x in xs]
        return xs, approx
    return solver


def _exact_sin_pi(x):
    return math.sin(math.pi * x)


class TestVerifyMms:
    def test_second_order_passes(self):
        solver = _make_second_order_solver()
        passed, msg = verify_mms(
            solver=solver,
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8, 1 / 16, 1 / 32],
            expected_order=2.0,
            norm="L2",
            tolerance=0.1,
        )
        assert passed, f"Expected pass; got: {msg}"
        assert "observed order" in msg

    def test_first_order_fails_when_second_required(self):
        def first_order_solver(h, **kw):
            n = max(2, round(1.0 / h))
            xs = [i / n for i in range(n + 1)]
            approx = [math.sin(math.pi * x) + h * 0.5 for x in xs]
            return xs, approx

        passed, msg = verify_mms(
            solver=first_order_solver,
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8, 1 / 16, 1 / 32],
            expected_order=2.0,
            norm="L2",
            tolerance=0.1,
        )
        assert not passed, f"Expected failure; got: {msg}"
        assert "observed order" in msg

    def test_unsupported_norm_fails(self):
        passed, msg = verify_mms(
            solver=_make_second_order_solver(),
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8],
            expected_order=2.0,
            norm="Linf",
        )
        assert not passed
        assert "unsupported norm" in msg

    def test_too_few_spacings_fails(self):
        passed, msg = verify_mms(
            solver=_make_second_order_solver(),
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4],
            expected_order=2.0,
        )
        assert not passed
        assert "at least 2" in msg

    def test_solver_exception_propagates(self):
        def bad_solver(h, **kw):
            raise RuntimeError("boom")

        passed, msg = verify_mms(
            solver=bad_solver,
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8],
            expected_order=2.0,
        )
        assert not passed
        assert "solver raised" in msg

    def test_tolerance_respected(self):
        # Solver gives order ~1.8 — passes with tol=0.3 but fails with tol=0.0
        def order_1_8_solver(h, **kw):
            n = max(2, round(1.0 / h))
            xs = [i / n for i in range(n + 1)]
            approx = [math.sin(math.pi * x) + h ** 1.8 * 0.5 for x in xs]
            return xs, approx

        passed_loose, _ = verify_mms(
            solver=order_1_8_solver,
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8, 1 / 16, 1 / 32],
            expected_order=2.0,
            tolerance=0.3,
        )
        passed_strict, _ = verify_mms(
            solver=order_1_8_solver,
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8, 1 / 16, 1 / 32],
            expected_order=2.0,
            tolerance=0.0,
        )
        assert passed_loose
        assert not passed_strict

    def test_solver_kwargs_forwarded(self):
        received_kwargs = {}

        def solver_with_kwargs(h, **kw):
            received_kwargs.update(kw)
            n = max(2, round(1.0 / h))
            xs = [i / n for i in range(n + 1)]
            approx = [math.sin(math.pi * x) + h ** 2 for x in xs]
            return xs, approx

        verify_mms(
            solver=solver_with_kwargs,
            exact_fn=_exact_sin_pi,
            mesh_spacings=[1 / 4, 1 / 8],
            expected_order=2.0,
            solver_kwargs={"alpha": 42},
        )
        assert received_kwargs.get("alpha") == 42


# ---------------------------------------------------------------------------
# verify_conservation
# ---------------------------------------------------------------------------

def _energy_stepper(state, **kw):
    """Advance state by one step; energy is conserved (total = sum of squares)."""
    # Rotate the state vector to conserve sum-of-squares
    a, b = state
    theta = 0.01
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    return (cos_t * a - sin_t * b, sin_t * a + cos_t * b)


def _energy_quantity(state):
    a, b = state
    return a ** 2 + b ** 2


def _leaky_stepper(state, **kw):
    """Stepper that leaks energy — quantity grows each step."""
    a, b = state
    return (a * 1.01, b * 1.01)


class TestVerifyConservation:
    def test_conservation_passes_when_conserved(self):
        initial = (3.0, 4.0)  # energy = 25.0
        passed, msg = verify_conservation(
            stepper=_energy_stepper,
            quantity_fn=_energy_quantity,
            initial_state=initial,
            n_steps=100,
            drift_bound=1e-9,
        )
        assert passed, f"Expected pass; got: {msg}"
        assert "max drift" in msg

    def test_conservation_fails_when_leaky(self):
        initial = (3.0, 4.0)
        passed, msg = verify_conservation(
            stepper=_leaky_stepper,
            quantity_fn=_energy_quantity,
            initial_state=initial,
            n_steps=10,
            drift_bound=1e-9,
        )
        assert not passed
        assert ">" in msg

    def test_zero_steps_fails(self):
        passed, msg = verify_conservation(
            stepper=_energy_stepper,
            quantity_fn=_energy_quantity,
            initial_state=(1.0, 0.0),
            n_steps=0,
            drift_bound=1e-9,
        )
        assert not passed
        assert "n_steps" in msg

    def test_stepper_exception_propagates(self):
        def bad_stepper(state, **kw):
            raise ValueError("explode")

        passed, msg = verify_conservation(
            stepper=bad_stepper,
            quantity_fn=_energy_quantity,
            initial_state=(1.0, 0.0),
            n_steps=5,
            drift_bound=1e-9,
        )
        assert not passed
        assert "stepper raised" in msg

    def test_quantity_fn_exception_on_initial(self):
        def bad_qty(state):
            raise RuntimeError("no qty")

        passed, msg = verify_conservation(
            stepper=_energy_stepper,
            quantity_fn=bad_qty,
            initial_state=(1.0, 0.0),
            n_steps=5,
            drift_bound=1e-9,
        )
        assert not passed
        assert "initial state" in msg

    def test_drift_exactly_at_bound_passes(self):
        # Stepper produces exactly drift_bound drift at every step.
        def drift_stepper(state, **kw):
            return state + 1e-10  # scalar for simplicity

        passed, msg = verify_conservation(
            stepper=drift_stepper,
            quantity_fn=lambda s: s,
            initial_state=0.0,
            n_steps=5,
            drift_bound=5e-10,  # bound >= max drift
        )
        assert passed

    def test_stepper_kwargs_forwarded(self):
        received = {}

        def recording_stepper(state, **kw):
            received.update(kw)
            return state

        verify_conservation(
            stepper=recording_stepper,
            quantity_fn=lambda s: float(s),
            initial_state=1.0,
            n_steps=3,
            drift_bound=1.0,
            stepper_kwargs={"dt": 0.01},
        )
        assert received.get("dt") == 0.01


# ---------------------------------------------------------------------------
# parse_mms_criterion
# ---------------------------------------------------------------------------

class TestParseMmsCriterion:
    def test_parses_order_and_norm(self):
        args = parse_mms_criterion("order=2 norm=L2")
        assert args["order"] == 2.0
        assert args["norm"] == "L2"

    def test_parses_module_solver_exact(self):
        args = parse_mms_criterion(
            'module=my.mod solver=solve exact=exact_fn spacings=0.5,0.25,0.125'
        )
        assert args["module"] == "my.mod"
        assert args["solver"] == "solve"
        assert args["exact"] == "exact_fn"
        assert args["spacings"] == [0.5, 0.25, 0.125]

    def test_parses_tolerance(self):
        args = parse_mms_criterion("order=3 tolerance=0.05")
        assert args["tolerance"] == pytest.approx(0.05)

    def test_missing_keys_not_present(self):
        args = parse_mms_criterion("order=2")
        assert "module" not in args
        assert "spacings" not in args


# ---------------------------------------------------------------------------
# parse_conserves_criterion
# ---------------------------------------------------------------------------

class TestParseConservesCriterion:
    def test_parses_quantity_and_drift(self):
        args = parse_conserves_criterion("quantity=mass drift<=1e-9")
        assert args["quantity"] == "mass"
        assert args["drift_bound"] == pytest.approx(1e-9)

    def test_parses_module_stepper_qty(self):
        args = parse_conserves_criterion(
            "module=sim stepper=advance quantity_fn=get_mass "
            "initial=state0 n_steps=50 drift<=1e-6"
        )
        assert args["module"] == "sim"
        assert args["stepper"] == "advance"
        assert args["quantity_fn"] == "get_mass"
        assert args["initial"] == "state0"
        assert args["n_steps"] == 50
        assert args["drift_bound"] == pytest.approx(1e-6)

    def test_missing_drift_not_present(self):
        args = parse_conserves_criterion("quantity=energy")
        assert "drift_bound" not in args
