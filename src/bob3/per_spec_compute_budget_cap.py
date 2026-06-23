"""Per-spec compute-budget cap for Bob3.

Reads the ``max_cost_usd`` field from a YAML spec file. When the running
cost for a spec exceeds this cap, the orchestrator escalates (human alert
or graceful abort) rather than burning the global budget.

Usage
-----
Load the cap from a spec dict (already parsed YAML)::

    cap = SpecBudgetCap.from_spec(spec_dict)
    action = cap.check(running_cost_usd=12.50)
    if action == BudgetAction.ABORT:
        ...

Or load directly from a YAML file::

    cap = SpecBudgetCap.from_yaml_file("myspec.yaml")
"""

from __future__ import annotations

import enum
import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class BudgetAction(str, enum.Enum):
    """Action to take when a budget threshold is crossed."""

    CONTINUE = "continue"
    WARN = "warn"
    ABORT = "abort"
    HUMAN_ALERT = "human_alert"


# Fraction of max_cost_usd at which a warning is emitted before hard abort.
_WARN_THRESHOLD_FRACTION = 0.80


@dataclass
class SpecBudgetCap:
    """Budget cap parsed from a YAML spec's ``max_cost_usd`` field.

    Args:
        max_cost_usd: Hard cap in USD. ``None`` means no cap is set and
            :meth:`check` always returns :attr:`BudgetAction.CONTINUE`.
        warn_threshold_fraction: Fraction of ``max_cost_usd`` at which a
            warning action is triggered before the hard abort.
        escalation_mode: ``"abort"`` raises a graceful abort;
            ``"human_alert"`` marks the spec as needing human review.
    """

    max_cost_usd: float | None = None
    warn_threshold_fraction: float = _WARN_THRESHOLD_FRACTION
    escalation_mode: str = "abort"

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "SpecBudgetCap":
        """Build a :class:`SpecBudgetCap` from a parsed YAML spec dict.

        Args:
            spec: The top-level YAML mapping.  Reads ``max_cost_usd``,
                optionally ``budget_escalation_mode`` and
                ``budget_warn_threshold``.

        Returns:
            A :class:`SpecBudgetCap` instance.  If ``max_cost_usd`` is
            absent or ``None`` the cap is disabled.
        """
        if not isinstance(spec, dict):
            return cls()

        raw = spec.get("max_cost_usd")
        max_cost: float | None = None
        if raw is not None:
            try:
                val = float(raw)
                if val < 0:
                    logger.warning(
                        "max_cost_usd must be non-negative; got %s — cap disabled",
                        raw,
                    )
                else:
                    max_cost = val
            except (TypeError, ValueError):
                logger.warning(
                    "max_cost_usd is not a valid number (%r) — cap disabled",
                    raw,
                )

        escalation_mode = spec.get("budget_escalation_mode", "abort")
        if escalation_mode not in ("abort", "human_alert"):
            logger.warning(
                "Unknown budget_escalation_mode %r — defaulting to 'abort'",
                escalation_mode,
            )
            escalation_mode = "abort"

        warn_frac = _WARN_THRESHOLD_FRACTION
        raw_warn = spec.get("budget_warn_threshold")
        if raw_warn is not None:
            try:
                wf = float(raw_warn)
                if 0.0 <= wf <= 1.0:
                    warn_frac = wf
                else:
                    logger.warning(
                        "budget_warn_threshold must be in [0, 1]; got %s — using default",
                        raw_warn,
                    )
            except (TypeError, ValueError):
                logger.warning(
                    "budget_warn_threshold is not a valid number (%r) — using default",
                    raw_warn,
                )

        return cls(
            max_cost_usd=max_cost,
            warn_threshold_fraction=warn_frac,
            escalation_mode=escalation_mode,
        )

    @classmethod
    def from_yaml_file(cls, path: str | pathlib.Path) -> "SpecBudgetCap":
        """Build a :class:`SpecBudgetCap` by reading a YAML spec file.

        Args:
            path: Path to the YAML spec file.

        Returns:
            A :class:`SpecBudgetCap` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file is not valid YAML.
        """
        p = pathlib.Path(path)
        with p.open() as fh:
            spec = yaml.safe_load(fh) or {}
        return cls.from_spec(spec)

    # ------------------------------------------------------------------ #
    # Runtime check
    # ------------------------------------------------------------------ #

    @property
    def is_enabled(self) -> bool:
        """Return ``True`` when a hard cap is configured."""
        return self.max_cost_usd is not None

    @property
    def warn_at_usd(self) -> float | None:
        """USD threshold at which a warning is emitted, or ``None`` if disabled."""
        if self.max_cost_usd is None:
            return None
        return self.max_cost_usd * self.warn_threshold_fraction

    def check(self, running_cost_usd: float) -> BudgetAction:
        """Decide what action to take given the current running cost.

        Args:
            running_cost_usd: Cumulative spend so far for the spec, in USD.

        Returns:
            :attr:`BudgetAction.CONTINUE` — under all thresholds.
            :attr:`BudgetAction.WARN` — past the warn threshold but below the cap.
            :attr:`BudgetAction.ABORT` — at or above the cap and escalation is "abort".
            :attr:`BudgetAction.HUMAN_ALERT` — at or above the cap and escalation is
            "human_alert".
        """
        if not self.is_enabled:
            return BudgetAction.CONTINUE

        cap = self.max_cost_usd  # guaranteed non-None by is_enabled
        assert cap is not None  # for type-checkers

        if running_cost_usd >= cap:
            logger.warning(
                "Per-spec compute budget exceeded: running=%.4f cap=%.4f "
                "(escalation_mode=%s)",
                running_cost_usd,
                cap,
                self.escalation_mode,
            )
            if self.escalation_mode == "human_alert":
                return BudgetAction.HUMAN_ALERT
            return BudgetAction.ABORT

        warn_at = self.warn_at_usd
        if warn_at is not None and running_cost_usd >= warn_at:
            logger.warning(
                "Per-spec compute budget warning: running=%.4f warn_threshold=%.4f cap=%.4f",
                running_cost_usd,
                warn_at,
                cap,
            )
            return BudgetAction.WARN

        return BudgetAction.CONTINUE

    def remaining_usd(self, running_cost_usd: float) -> float | None:
        """Return how many USD remain before the cap is hit, or ``None`` if uncapped.

        Args:
            running_cost_usd: Cumulative spend so far for the spec, in USD.

        Returns:
            Remaining budget in USD (may be negative if already exceeded),
            or ``None`` if no cap is configured.
        """
        if self.max_cost_usd is None:
            return None
        return max(0.0, self.max_cost_usd - running_cost_usd)

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary dict for logging and telemetry."""
        return {
            "max_cost_usd": self.max_cost_usd,
            "warn_threshold_fraction": self.warn_threshold_fraction,
            "warn_at_usd": self.warn_at_usd,
            "escalation_mode": self.escalation_mode,
            "enabled": self.is_enabled,
        }
