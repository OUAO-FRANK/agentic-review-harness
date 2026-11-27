"""Compatibility import for diffledger.evaluation.experiments."""

import sys
from diffledger.evaluation import experiments

sys.modules[__name__] = experiments
