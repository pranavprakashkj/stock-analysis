"""Task 1.4: shared construction checks used by the domain value objects."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from trading.domain.checks import require_date, require_finite_decimal, require_instance
from trading.domain.timing import IST


def test_require_instance_returns_the_value_or_names_the_expected_type() -> None:
    assert require_instance("count", 3, int) == 3
    with pytest.raises(TypeError, match="count must be an int, not str"):
        require_instance("count", "3", int)


def test_require_instance_matches_the_exact_type_only() -> None:
    class Sub(Decimal):
        pass

    with pytest.raises(TypeError, match="x must be a Decimal, not Sub"):
        require_instance("x", Sub("1"), Decimal)
    with pytest.raises(TypeError, match="flag must be an int, not bool"):
        require_instance("flag", True, int)
    assert require_instance("flag", True, bool) is True


def test_require_date_accepts_dates_only() -> None:
    assert require_date("day", date(2024, 1, 1)) == date(2024, 1, 1)
    with pytest.raises(TypeError, match="day must be a date, not datetime"):
        require_date("day", datetime(2024, 1, 1, tzinfo=IST))
    with pytest.raises(TypeError, match="day must be a date, not str"):
        require_date("day", "2024-01-01")


def test_require_finite_decimal() -> None:
    assert require_finite_decimal("x", Decimal("-1.5")) == Decimal("-1.5")
    with pytest.raises(TypeError, match="x must be a Decimal, not float"):
        require_finite_decimal("x", 1.5)
    with pytest.raises(ValueError, match="x must be finite"):
        require_finite_decimal("x", Decimal("NaN"))
