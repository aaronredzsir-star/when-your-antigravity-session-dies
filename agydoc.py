#!/usr/bin/env python3
"""
Antigravity Doctor (Single-file runner)
Run directly: python agydoc.py scan
"""

import sys
import os

# Ensure local package import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agy_doctor.cli import main

if __name__ == "__main__":
    main()
