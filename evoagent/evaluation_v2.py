"""Compatibility import for diffledger.evaluation.benchmark."""

import sys
from diffledger.evaluation import benchmark

sys.modules[__name__] = benchmark
