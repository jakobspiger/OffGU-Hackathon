"""Shared pytest fixtures / path setup for the T02 knowledge tests.

The suite is designed to run WITHOUT the production libraries (PyMuPDF,
python-docx, openpyxl, pydantic, PyYAML) installed, by exercising the
pure-logic ingestion paths on small fixture inputs and guarding the
library-dependent paths with ``pytest.importorskip``.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MATERIALS_DIR = os.path.join(_ROOT, "materials")
S02_NOTES_PATH = os.path.join(_ROOT, "data", "source_notes", "s02_notes.yaml")
H_SCENARIOS_PATH = os.path.join(
    _ROOT, "materials", "customer_scenarios_for_final_evaluation.txt"
)
