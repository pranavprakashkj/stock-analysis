"""Shared test configuration.

Hypothesis runs derandomised and without an example database, so every run explores the same
examples and writes nothing into the repository. No deadline: timing must not make a run flaky.
"""

from hypothesis import settings

settings.register_profile("deterministic", derandomize=True, database=None, deadline=None)
settings.load_profile("deterministic")
