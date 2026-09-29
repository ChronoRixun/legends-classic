"""pytest: the unit tests import their helpers (synth) and the pipeline (tools/xml1build) by name."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1] / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
