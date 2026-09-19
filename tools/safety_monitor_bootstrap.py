"""Isolated absolute-path bootstrap for the repository safety-monitor CLI."""
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.safety_monitor.__main__ import main  # noqa: E402

raise SystemExit(main())
