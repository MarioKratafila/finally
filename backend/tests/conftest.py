import random

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _deterministic_seed():
    """Seed both RNGs so statistical tests are reproducible across runs."""
    random.seed(1234)
    np.random.seed(1234)
