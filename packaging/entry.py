"""PyInstaller entry point (multiprocessing-safe, no relative imports)."""
import multiprocessing
import sys

from nexus.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
