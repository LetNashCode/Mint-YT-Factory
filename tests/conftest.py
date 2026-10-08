"""Pytest bootstrap for Mint-YT-Factory.

Force tests to import production modules from the checked-out repository.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
root_text = str(ROOT)

if root_text in sys.path:
    sys.path.remove(root_text)
sys.path.insert(0, root_text)

module = sys.modules.get("generate_script")
module_file = str(getattr(module, "__file__", "") or "") if module else ""
if module is not None and not module_file.startswith(root_text):
    del sys.modules["generate_script"]
