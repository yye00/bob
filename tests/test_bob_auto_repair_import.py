"""Verify bob.auto_repair module is importable and has required functions."""


def test_bob_auto_repair_importable():
    from bob.auto_repair import semantic_equivalence_check, apply_auto_repair
    assert callable(semantic_equivalence_check)
    assert callable(apply_auto_repair)
