#!/usr/bin/env python3.11
"""Check S-Agent's published version; --apply installs a newer standalone copy."""
from pathlib import Path
import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))
from skill_update import check_skill_update


if __name__ == '__main__':
    print(check_skill_update('s-agent', SKILL_DIR, apply='--apply' in sys.argv))
