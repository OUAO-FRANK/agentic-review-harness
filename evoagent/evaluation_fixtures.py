"""Compatibility import for diffledger.evaluation.fixtures."""

import sys
from diffledger.evaluation import fixtures

sys.modules[__name__] = fixtures
