#!/usr/bin/env python3
"""
Entry point kept at the repo root so `python3 macpower.py` keeps working.
The real code lives in the macpower/ package (also: `python3 -m macpower`).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from macpower.cli import main

if __name__ == "__main__":
    main()
