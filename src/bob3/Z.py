# Implementation module for structural-AC fuzzy fallback tests.
# function_in_z was supposed to be in X.py per the AC, but lives here.
# This demonstrates the mismatch scenario that fuzzy_function_lookup resolves.


def function_in_z(arg):
    """Example function that landed in Z.py instead of X.py."""
    return arg
