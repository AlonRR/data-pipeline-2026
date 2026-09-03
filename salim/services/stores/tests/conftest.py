import sys
from pathlib import Path

# The service's own modules import as top-level names (`from enrichers.base
# import ...`), matching how the Dockerfile runs it, so the service root has to
# be importable rather than the repo root.
_SERVICE_ROOT = Path(__file__).resolve().parents[1]

# `shared/` is a sibling of the service files inside the image (the Dockerfile
# copies it to /app/shared next to them), but lives one level up in the repo,
# so `salim/` has to be on the path too for `from shared.models import ...`.
_SALIM_ROOT = _SERVICE_ROOT.parents[1]

for path in (_SERVICE_ROOT, _SALIM_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
