"""Convenience launcher usable by absolute path from any current directory."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.workbench.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
