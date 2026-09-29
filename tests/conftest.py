import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# REPORTS_KEY has no default in the app (unset = /api/reports/* answers 503). Tests use their own key.
os.environ["REPORTS_KEY"] = os.environ.get("REPORTS_KEY") or "pytest-reports-key"
