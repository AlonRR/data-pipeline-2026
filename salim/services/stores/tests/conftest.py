import sys
from pathlib import Path

# The service's own modules import as top-level names (`from enrichers.base
# import ...`), matching how the Dockerfile runs it, so the service root has to
# be importable rather than the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
