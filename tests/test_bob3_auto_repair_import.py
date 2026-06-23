"""Verify bob3.auto_repair module is importable and has required functions."""


def test_bob3_auto_repair_importable():
    from bob3.auto_repair import semantic_equivalence_check, apply_auto_repair
    assert callable(semantic_equivalence_check)
    assert callable(apply_auto_repair)
