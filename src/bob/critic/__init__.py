"""bob.critic — adversarial spec-critic and persistent findings registry.

Public API::

    from bob.critic.registry import write_finding, detect_regression, compute_critic_repeat_rate
"""
from bob.critic import registry  # noqa: F401

__all__ = ["registry"]
