"""Fixtures for the LOPA engine tests (plan PR 4)."""

import pytest

from guideword.config import Config, load_config
from guideword.reference import ReferenceSet, load_reference_set


@pytest.fixture(scope="session")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config(global_budget_usd=25.0)
