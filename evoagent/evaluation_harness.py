"""Compatibility import for diffledger.evaluation.scoring."""

import sys
from diffledger.evaluation import scoring

sys.modules[__name__] = scoring
