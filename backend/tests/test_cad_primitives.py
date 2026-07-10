"""Unit tests for cad_primitives.py"""

from app.engine.cad_primitives import metres_to_ftin


# ---------------------------------------------------------------------------
# metres_to_ftin
# ---------------------------------------------------------------------------


def test_metres_to_ftin_whole_feet():
    assert metres_to_ftin(3.048) == "10'-0\""


def test_metres_to_ftin_with_inches():
    assert metres_to_ftin(1.067) == "3'-6\""


def test_metres_to_ftin_zero():
    assert metres_to_ftin(0.0) == "0'-0\""


def test_metres_to_ftin_inch_rollover():
    # 0.3048 = 1 foot exactly; check boundary
    result = metres_to_ftin(0.3048)
    assert result == "1'-0\""
