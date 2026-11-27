"""Compatibility import for diffledger.evaluation.replay."""

import sys
from diffledger.evaluation import replay

sys.modules[__name__] = replay
