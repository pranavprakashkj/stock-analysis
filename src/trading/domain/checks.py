"""Construction checks shared by domain value objects: exact types, no implicit conversion.

Types are matched exactly (`type(value) is expected`), so a subclass cannot override comparisons
to slip past an invariant, and bool (an int subclass) is never accepted as a number.
"""

from datetime import date
from decimal import Decimal


def _a(type_name: str) -> str:
    return f"an {type_name}" if type_name[0].lower() in "aeiou" else f"a {type_name}"


def require_instance[T](name: str, value: object, expected: type[T]) -> T:
    """`value` itself if its type is exactly `expected`."""
    if not isinstance(value, expected) or type(value) is not expected:
        raise TypeError(f"{name} must be {_a(expected.__name__)}, not {type(value).__name__}")
    return value


def require_date(name: str, value: object) -> date:
    """A calendar date. A datetime (a date subclass carrying a time) is rejected."""
    return require_instance(name, value, date)


def require_finite_decimal(name: str, value: object) -> Decimal:
    """A finite Decimal. Floats are rejected: they already carry binary rounding error."""
    number = require_instance(name, value, Decimal)
    if not number.is_finite():
        raise ValueError(f"{name} must be finite: {number}")
    return number
