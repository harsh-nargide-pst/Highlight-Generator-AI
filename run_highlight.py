#!/usr/bin/env python3
"""Thin wrapper so 'python run_highlight.py' works from repo root. Prefer: poetry run highlight."""

from highlights_ai.run_highlight import main

if __name__ == "__main__":
    main()
