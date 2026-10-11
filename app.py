"""Launch with: uv run streamlit run app.py"""

import sys
from pathlib import Path

# Also support direct execution from an unpacked source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pwrbnb.ui import render  # noqa: E402

render()
