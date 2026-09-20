#!/usr/bin/env python3
"""Запуск симулятора из корня проекта.

Нужен только для того, чтобы не заставлять оператора выставлять PYTHONPATH:

    python run.py --check
    python run.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sim_launcher.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
